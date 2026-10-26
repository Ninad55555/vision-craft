from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from bs4 import BeautifulSoup
from PIL import Image

from app.settings import Settings, settings as default_settings
from src.core.errors import VisionCraftError, error
from src.core.hf_client import VLMClient
from src.core.image_prep import PreparedImage
from src.core.prompts import build_refine_messages
from src.generator.html_cleaner import clean_model_output
from src.generator.sanitize import SanitizeReport, make_standalone
from src.refine.render import RenderResult
from src.refine.similarity import compute_ssim

log = logging.getLogger(__name__)

MAX_REFINE_HTML_BYTES = 150_000


class Renderer(Protocol):
    async def render(self, html: str, width: int, height: int) -> RenderResult: ...
    async def aclose(self) -> None: ...


@dataclass
class RefineOutcome:
    html: str
    initial: float
    candidate: float
    final: float
    kept: bool
    improvement: float
    meaningful: bool
    target: float
    warnings: list[str] = field(default_factory=list)
    model: str | None = None
    provider: str | None = None
    finish_reason: str | None = None
    truncated: bool = False
    sanitize: SanitizeReport = field(default_factory=SanitizeReport)
    usage: dict | None = None
    elapsed_ms: int = 0


@dataclass
class _PassOutput:
    text: str
    model: str | None = None
    provider: str | None = None
    finish_reason: str | None = None
    usage: dict | None = None


def _sanitize_input(raw: str) -> tuple[str, SanitizeReport]:
    if not raw or not raw.strip():
        raise error("INVALID_HTML", "No HTML was supplied for refinement.")
    if len(raw.encode("utf-8")) > MAX_REFINE_HTML_BYTES:
        raise error(
            "INVALID_HTML",
            f"HTML is too large to refine ({len(raw.encode('utf-8')) // 1024} KB; "
            f"limit {MAX_REFINE_HTML_BYTES // 1024} KB).",
        )
    try:
        sanitized, report = make_standalone(raw)
    except Exception as exc:  # noqa: BLE001 - parser failures become a clean 400
        raise error("INVALID_HTML", "Could not parse the supplied HTML.") from exc

    try:
        soup = BeautifulSoup(sanitized, "lxml")
    except Exception as exc:  # noqa: BLE001
        raise error("INVALID_HTML", "Could not parse the supplied HTML.") from exc
    body = soup.body
    if body is None or (not body.get_text(strip=True) and not body.find_all(True)):
        raise error("INVALID_HTML", "The supplied HTML has no visible content to refine.")
    return sanitized, report


def _image_from_png(png: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(png))
        image.load()
        return image.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise error("REFINE_FAILED", "The rendered screenshot could not be read.") from exc


def _png_data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _pct(value: float) -> str:
    return f"{value:.0%}"


class RefineService:
    """Runs exactly one visual correction pass per call."""

    def __init__(
        self,
        *,
        settings_obj: Settings | None = None,
        renderer: Renderer | None = None,
        scorer: Callable[[Image.Image, Image.Image], float] | None = None,
    ):
        self.settings = settings_obj or default_settings
        self._renderer = renderer
        self._owns_renderer = renderer is None
        self._scorer = scorer or compute_ssim
        self._start_lock = asyncio.Lock()

    async def _get_renderer(self) -> Renderer:
        if self._renderer is not None:
            return self._renderer
        async with self._start_lock:
            if self._renderer is None:
                from src.refine.render import HtmlRenderer

                self._renderer = HtmlRenderer(
                    channel=self.settings.refine_browser_channel,
                    timeout=self.settings.refine_render_timeout_seconds,
                )
                self._owns_renderer = True
        return self._renderer

    async def aclose(self) -> None:
        renderer = self._renderer
        self._renderer = None
        if renderer is not None and self._owns_renderer:
            try:
                await renderer.aclose()
            except Exception:  # noqa: BLE001 - shutdown must not fail
                pass

    async def refine(
        self,
        *,
        html: str,
        prepared: PreparedImage,
        instructions: str,
        client: VLMClient,
        on_status: Callable[[str], None] | None = None,
        on_refine: Callable[[dict], None] | None = None,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> RefineOutcome:
        started = time.monotonic()
        target_image = prepared.pil
        if target_image is None:
            raise error("REFINE_FAILED", "The prepared screenshot is unavailable.")

        sanitized, initial_report = _sanitize_input(html)
        warnings = list(initial_report.notes)
        target = max(0.0, min(1.0, float(self.settings.refine_target_score)))

        async def ensure_connected() -> None:
            if is_disconnected is not None and await is_disconnected():
                raise error("INTERNAL", "Client disconnected; refinement cancelled.")

        await ensure_connected()
        renderer = await self._get_renderer()

        self._emit_status(on_status, "rendering")
        try:
            initial_render = await renderer.render(sanitized, prepared.width, prepared.height)
        except VisionCraftError as exc:
            if exc.code == "REFINE_UNAVAILABLE":
                raise
            raise error("REFINE_FAILED", f"Could not render the current HTML: {exc.message}") from exc
        if initial_render.blocked_requests:
            warnings.append(
                f"Blocked {initial_render.blocked_requests} external request(s) while rendering the current HTML."
            )

        self._emit_status(on_status, "scoring")
        try:
            initial_score = await asyncio.to_thread(
                self._scorer, target_image, _image_from_png(initial_render.png)
            )
        except VisionCraftError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise error("REFINE_FAILED", f"Could not compare the current render: {exc}") from exc
        initial_score = max(0.0, min(1.0, float(initial_score)))

        outcome = RefineOutcome(
            html=sanitized,
            initial=initial_score,
            candidate=initial_score,
            final=initial_score,
            kept=False,
            improvement=0.0,
            meaningful=False,
            target=target,
            warnings=warnings,
            sanitize=initial_report,
        )

        if initial_score >= target:
            warnings.append(
                f"Visual similarity is already {_pct(initial_score)} (target {_pct(target)}); "
                "no correction pass was run."
            )
            return self._finish(outcome, started)

        await ensure_connected()
        self._emit_status(on_status, "refining")
        messages = build_refine_messages(
            prepared,
            _png_data_url(initial_render.png),
            sanitized,
            instructions,
        )
        try:
            pass_output = await self._call_vlm(client, messages)
        except VisionCraftError as exc:
            warnings.append(f"REFINE_PASS_FAILED: {exc.message}; the previous version was kept.")
            return self._finish(outcome, started)

        try:
            cleaned, cleaner_warnings = clean_model_output(
                pass_output.text, finish_reason=pass_output.finish_reason
            )
            new_html, new_report = make_standalone(cleaned)
            _sanitize_input(new_html)
        except VisionCraftError as exc:
            warnings.append(f"REFINE_PASS_FAILED: {exc.message}; the previous version was kept.")
            return self._finish(outcome, started)

        self._emit_status(on_status, "scoring")
        try:
            new_render = await renderer.render(new_html, prepared.width, prepared.height)
            candidate_score = await asyncio.to_thread(
                self._scorer, target_image, _image_from_png(new_render.png)
            )
        except VisionCraftError as exc:
            warnings.append(f"REFINE_PASS_FAILED: {exc.message}; the previous version was kept.")
            return self._finish(outcome, started)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"REFINE_PASS_FAILED: could not score the correction: {exc}; the previous version was kept.")
            return self._finish(outcome, started)

        candidate_score = max(0.0, min(1.0, float(candidate_score)))
        kept = candidate_score > initial_score
        output_html = new_html if kept else sanitized
        output_report = new_report if kept else initial_report
        final_score = candidate_score if kept else initial_score
        improvement = max(0.0, final_score - initial_score)
        meaningful = kept and improvement >= self.settings.refine_min_improvement

        if kept:
            pass_warnings = list(cleaner_warnings)
            if new_render.blocked_requests:
                pass_warnings.append(
                    f"Blocked {new_render.blocked_requests} external request(s) while rendering the correction."
                )
            pass_warnings.extend(new_report.notes)
            warnings.extend(pass_warnings)
        else:
            warnings.append(
                "The correction pass did not improve visual similarity; the previous version was kept."
            )

        outcome.html = output_html
        outcome.candidate = candidate_score
        outcome.final = final_score
        outcome.kept = kept
        outcome.improvement = improvement
        outcome.meaningful = meaningful
        outcome.warnings = warnings
        outcome.sanitize = output_report
        outcome.model = pass_output.model
        outcome.provider = pass_output.provider
        outcome.finish_reason = pass_output.finish_reason if kept else None
        outcome.truncated = bool(kept and (
            pass_output.finish_reason == "length"
            or any("OUTPUT_TRUNCATED" in warning for warning in cleaner_warnings)
        ))
        outcome.usage = pass_output.usage

        if on_refine:
            on_refine(
                {
                    "initial": outcome.initial,
                    "candidate": outcome.candidate,
                    "final": outcome.final,
                    "kept": outcome.kept,
                    "improvement": outcome.improvement,
                    "meaningful": outcome.meaningful,
                }
            )
        return self._finish(outcome, started)

    async def _call_vlm(self, client: VLMClient, messages: list[dict]) -> _PassOutput:
        chunks: list[str] = []
        model: str | None = None
        provider: str | None = None
        finish_reason: str | None = None
        usage: dict | None = None
        async for event in client.stream(messages):
            if event.kind == "status":
                model = event.model or model
                provider = event.provider or provider
            elif event.kind == "delta":
                chunks.append(event.text)
            elif event.kind == "done":
                finish_reason = event.finish_reason
                usage = event.usage
                model = event.model or model
                provider = event.provider or provider
        return _PassOutput(
            text="".join(chunks),
            model=model,
            provider=provider,
            finish_reason=finish_reason,
            usage=usage,
        )

    @staticmethod
    def _emit_status(on_status: Callable[[str], None] | None, stage: str) -> None:
        if on_status is not None:
            on_status(stage)

    @staticmethod
    def _finish(outcome: RefineOutcome, started: float) -> RefineOutcome:
        outcome.elapsed_ms = int((time.monotonic() - started) * 1000)
        return outcome
