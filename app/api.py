from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import AsyncIterator, Callable

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app import settings as settings_module
from app.schemas import (
    ConfigResponse,
    DeltaData,
    ErrorDetail,
    HealthResponse,
    ImageInfo,
    RefineEventData,
    RefineResultPayload,
    ResultPayload,
    SanitizeCounts,
    SimilarityInfo,
    StatusData,
    UsageInfo,
    sse,
)
from src.core.errors import VisionCraftError, error
from src.core.hf_client import StreamEvent, VLMClient
from src.core.image_prep import prepare_image
from src.core.palette import extract_palette
from src.core.prompts import build_messages
from src.generator.html_cleaner import clean_model_output
from src.generator.sanitize import make_standalone
from src.refine.service import RefineService

log = logging.getLogger("visioncraft")

APP_CSP = "default-src 'self'; frame-src 'self' about:; style-src 'self'; script-src 'self'; img-src 'self' data: blob:"
SSE_PING_SECONDS = 15
RATE_WINDOW_SECONDS = 60


def get_settings():
    return settings_module.settings


def client_ip(request: Request) -> str:
    settings = get_settings()
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request) -> float | None:
    """Sliding-window limiter. Returns retry-after seconds, or None when allowed."""
    settings = get_settings()
    hits: dict[str, deque] = request.app.state.rate_hits
    ip = client_ip(request)
    now = time.monotonic()
    dq = hits.setdefault(ip, deque())
    while dq and dq[0] <= now - RATE_WINDOW_SECONDS:
        dq.popleft()
    if len(dq) >= max(1, settings.rate_limit_per_minute):
        return max(0.0, dq[0] + RATE_WINDOW_SECONDS - now)
    dq.append(now)
    return None


class GuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        def guard_response(status: int, payload: dict, extra_headers: dict | None = None):
            headers = {"X-Request-ID": request_id, **_security_headers(), **(extra_headers or {})}
            return JSONResponse(payload, status_code=status, headers=headers)

        settings = get_settings()
        path = request.url.path

        if settings.app_access_key and path.startswith("/api/"):
            presented = request.headers.get("x-access-key", "")
            if not secrets.compare_digest(presented, settings.app_access_key):
                return guard_response(401, {"detail": error("ACCESS_DENIED", "Enter the access key.").to_dict()})

        if path in {"/api/generate", "/api/refine"} and request.method == "POST":
            retry_after = check_rate_limit(request)
            if retry_after is not None:
                return guard_response(
                    429,
                    {"detail": error("RATE_LIMITED", "Too many requests. Slow down and retry.").to_dict()},
                    {"Retry-After": str(max(1, int(retry_after + 0.5)))},
                )

        try:
            response = await call_next(request)
        except VisionCraftError as exc:
            return guard_response(exc.http_status, {"detail": exc.to_dict()})
        response.headers["X-Request-ID"] = request_id
        for key, value in _security_headers().items():
            response.headers.setdefault(key, value)
        return response


def _security_headers() -> dict:
    return {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": APP_CSP,
    }


def _redact(text: str) -> str:
    """Strip provider credentials from any string that crosses the API boundary."""
    settings = get_settings()
    for token in (settings.hf_token, settings.groq_api_key, settings.google_api_key):
        if token and len(token) >= 4 and token in text:
            text = text.replace(token, "[redacted]")
    return text


def _public_detail(exc: VisionCraftError) -> dict:
    detail = exc.to_dict()
    detail["message"] = _redact(detail["message"])
    return detail


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.vlm_client = VLMClient()
        app.state.refine_service = RefineService()
        yield
        if app.state.refine_service is not None:
            await app.state.refine_service.aclose()
        await app.state.vlm_client.aclose()

    app = FastAPI(title="VisionCraft", version="1.0.0", lifespan=lifespan)
    app.state.rate_hits = {}
    app.state.client_factory = None
    app.state.refine_factory = None
    app.state.vlm_client = None
    app.state.refine_service = None

    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(GuardMiddleware)

    @app.get("/health", response_model=HealthResponse)
    async def health():
        s = get_settings()
        return HealthResponse(
            hf_token_configured=bool(s.hf_token),
            model=s.hf_model_id,
            fallback_models=s.fallback_models,
            refine_enabled=s.enable_refine_loop,
        )

    @app.get("/api/config", response_model=ConfigResponse)
    async def config():
        s = get_settings()
        return ConfigResponse(
            max_upload_mb=s.max_upload_mb,
            image_max_side=s.image_max_side,
            accepted_types=["image/png", "image/jpeg", "image/webp"],
            requires_access_key=bool(s.app_access_key),
            model=s.hf_model_id,
            refine_enabled=s.enable_refine_loop,
        )

    @app.post("/api/generate")
    async def generate(
        request: Request,
        image: UploadFile = File(...),
        instructions: str = Form(default=""),
        stream: bool = Form(default=True),
        model: str | None = Form(default=None),  # accepted and ignored in v1
    ):
        _ = model
        raw = await image.read()
        settings = get_settings()
        if stream:
            return _streaming_response(request, raw, instructions, timeout_seconds=settings.request_timeout_seconds)
        try:
            result = await asyncio.wait_for(
                _run_pipeline(request, raw, instructions, on_event=None),
                timeout=settings.request_timeout_seconds,
            )
        except (asyncio.TimeoutError, TimeoutError):
            exc = error("UPSTREAM_TIMEOUT", "The model took too long. Try a smaller model or screenshot.")
            return JSONResponse({"detail": _public_detail(exc)}, status_code=exc.http_status)
        except VisionCraftError as exc:
            return JSONResponse({"detail": _public_detail(exc)}, status_code=exc.http_status)
        return JSONResponse(result.model_dump(mode="json", exclude_none=True))

    @app.post("/api/refine")
    async def refine(
        request: Request,
        image: UploadFile = File(...),
        html: str = Form(...),
        instructions: str = Form(default=""),
        stream: bool = Form(default=True),
    ):
        settings = get_settings()
        if not settings.enable_refine_loop:
            exc = error("REFINE_DISABLED", "Visual refinement is disabled. Set ENABLE_REFINE_LOOP=true.")
            return JSONResponse({"detail": _public_detail(exc)}, status_code=exc.http_status)
        raw = await image.read()
        if stream:
            return _refine_streaming_response(
                request,
                raw,
                html,
                instructions,
                timeout_seconds=settings.refine_timeout_seconds,
            )
        try:
            result = await asyncio.wait_for(
                _run_refine(request, raw, html, instructions, on_event=None),
                timeout=settings.refine_timeout_seconds,
            )
        except (asyncio.TimeoutError, TimeoutError):
            exc = error("REFINE_FAILED", "Refinement took too long. Try again or simplify the page.")
            return JSONResponse({"detail": _public_detail(exc)}, status_code=exc.http_status)
        except VisionCraftError as exc:
            return JSONResponse({"detail": _public_detail(exc)}, status_code=exc.http_status)
        return JSONResponse(result.model_dump(mode="json", exclude_none=True))

    # React frontend (frontend/dist) takes precedence; legacy vanilla web/ is the fallback.
    dist_dir = settings_module.ROOT / "frontend" / "dist"
    web_dir = settings_module.ROOT / "web"
    if dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
    elif web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    else:
        log.warning("No frontend found (frontend/dist or web/); serving API only.")

    return app


app = create_app()


def _get_client(request: Request) -> VLMClient:
    factory = request.app.state.client_factory
    if factory is not None:
        return factory()
    return request.app.state.vlm_client


def _get_refine_service(request: Request) -> RefineService:
    factory = request.app.state.refine_factory
    if factory is not None:
        return factory()
    service = request.app.state.refine_service
    if service is None:
        raise error("REFINE_UNAVAILABLE", "The refinement service is not running.")
    return service


async def _run_refine(
    request: Request,
    raw: bytes,
    html: str,
    instructions: str,
    on_event: Callable[[StreamEvent], None] | None,
    on_refine: Callable[[dict], None] | None = None,
) -> RefineResultPayload:
    settings = get_settings()
    if not settings.enable_refine_loop:
        raise error("REFINE_DISABLED", "Visual refinement is disabled. Set ENABLE_REFINE_LOOP=true.")
    if not (settings.hf_token or settings.groq_api_key or settings.google_api_key):
        raise error("AUTH_MISSING", "Configure at least one provider: HF_TOKEN, GROQ_API_KEY, or GOOGLE_API_KEY.")

    if on_event:
        on_event(StreamEvent(kind="status", text="preparing"))
    prepared = prepare_image(
        raw,
        max_side=settings.image_max_side,
        max_upload_bytes=settings.max_upload_mb * 1024 * 1024,
        max_payload_kb=settings.max_image_payload_kb,
    )
    client = _get_client(request)
    service = _get_refine_service(request)

    def status(stage: str) -> None:
        if on_event:
            on_event(StreamEvent(kind="status", text=stage))

    def refined(data: dict) -> None:
        if on_refine:
            on_refine(data)

    try:
        outcome = await service.refine(
            html=html,
            prepared=prepared,
            instructions=instructions,
            client=client,
            on_status=status,
            on_refine=refined,
            is_disconnected=request.is_disconnected,
        )
    except VisionCraftError:
        raise
    except Exception as exc:  # noqa: BLE001 - typed API failure for an unexpected refine error
        log.error(
            "Unhandled refine error (request %s): %s",
            getattr(request.state, "request_id", "?"),
            _redact(str(exc))[:200],
        )
        raise error("REFINE_FAILED", "Refinement failed unexpectedly.") from exc

    warnings = list(prepared.warnings) + list(outcome.warnings)
    return RefineResultPayload(
        html=outcome.html,
        similarity=SimilarityInfo(
            initial=outcome.initial,
            candidate=outcome.candidate,
            final=outcome.final,
            kept=outcome.kept,
            improvement=outcome.improvement,
            meaningful=outcome.meaningful,
            target=outcome.target,
        ),
        warnings=warnings,
        model=outcome.model,
        provider=outcome.provider,
        finish_reason=outcome.finish_reason,
        truncated=outcome.truncated,
        sanitize=SanitizeCounts(**{k: v for k, v in asdict(outcome.sanitize).items() if k != "notes"}),
        usage=UsageInfo(**outcome.usage) if outcome.usage else None,
        elapsed_ms=outcome.elapsed_ms,
    )


async def _run_pipeline(
    request: Request,
    raw: bytes,
    instructions: str,
    on_event: Callable[[StreamEvent], None] | None,
) -> ResultPayload:
    settings = get_settings()
    started = time.monotonic()
    if not (settings.hf_token or settings.groq_api_key or settings.google_api_key):
        raise error("AUTH_MISSING", "Configure at least one provider: HF_TOKEN, GROQ_API_KEY, or GOOGLE_API_KEY.")

    if on_event:
        on_event(StreamEvent(kind="status", text="preparing"))
    prepared = prepare_image(
        raw,
        max_side=settings.image_max_side,
        max_upload_bytes=settings.max_upload_mb * 1024 * 1024,
        max_payload_kb=settings.max_image_payload_kb,
    )
    palette = extract_palette(prepared.pil)
    messages = build_messages(prepared, palette, instructions)
    warnings = list(prepared.warnings)

    client = _get_client(request)
    if await request.is_disconnected():
        raise error("INTERNAL", "Client disconnected before generation started.")
    finish_reason: str | None = None
    usage: dict | None = None
    model_used = settings.hf_model_id
    provider_used: str | None = None
    chunks: list[str] = []
    generating_announced = False

    async for event in client.stream(messages):
        if await request.is_disconnected():
            raise error("INTERNAL", "Client disconnected; generation cancelled.")
        if event.kind == "status":
            if event.note:
                if on_event:
                    on_event(StreamEvent(kind="status", text="calling_model", model=event.model, note=event.note, provider=event.provider))
            elif on_event:
                on_event(StreamEvent(kind="status", text="calling_model", model=event.model, provider=event.provider))
        elif event.kind == "delta":
            if not generating_announced and on_event:
                on_event(StreamEvent(kind="status", text="generating", model=event.model, provider=event.provider))
                generating_announced = True
            chunks.append(event.text)
            if on_event:
                on_event(event)
        elif event.kind == "done":
            finish_reason = event.finish_reason
            usage = event.usage
            model_used = event.model or model_used
            provider_used = event.provider or provider_used

    if on_event:
        on_event(StreamEvent(kind="status", text="postprocessing"))
    cleaned, cleaner_warnings = clean_model_output("".join(chunks), finish_reason=finish_reason)
    warnings.extend(cleaner_warnings)
    standalone, report = make_standalone(cleaned)

    truncated = finish_reason == "length" or any("OUTPUT_TRUNCATED" in w for w in warnings)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return ResultPayload(
        html=standalone,
        model=model_used,
        provider=provider_used,
        finish_reason=finish_reason,
        truncated=bool(truncated),
        warnings=warnings,
        sanitize=SanitizeCounts(**{k: v for k, v in asdict(report).items() if k != "notes"}),
        palette=palette,
        image=ImageInfo(
            width=prepared.width,
            height=prepared.height,
            orig_width=prepared.orig_width,
            orig_height=prepared.orig_height,
        ),
        usage=UsageInfo(**usage) if usage else None,
        elapsed_ms=elapsed_ms,
    )


def _streaming_response(request: Request, raw: bytes, instructions: str, timeout_seconds: float) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue()

    async def produce():
        def emit(client_event: StreamEvent):
            if client_event.kind == "status":
                stage = {"calling_model", "generating", "postprocessing"}
                text = client_event.text if client_event.text in stage else "preparing"
                queue.put_nowait(
                    sse("status", StatusData(stage=text, note=client_event.note or None, model=client_event.model or None, provider=client_event.provider or None))
                )
            elif client_event.kind == "delta":
                queue.put_nowait(sse("delta", DeltaData(text=client_event.text)))

        try:
            result = await asyncio.wait_for(
                _run_pipeline(request, raw, instructions, on_event=emit),
                timeout=timeout_seconds,
            )
            queue.put_nowait(sse("result", result))
        except VisionCraftError as exc:
            queue.put_nowait(sse("error", ErrorDetail(**_public_detail(exc))))
        except (asyncio.TimeoutError, TimeoutError):
            exc = error("UPSTREAM_TIMEOUT", "The model took too long. Try a smaller model or screenshot.")
            queue.put_nowait(sse("error", ErrorDetail(**_public_detail(exc))))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - never leave an SSE stream hanging
            log.error("Unhandled error in /api/generate (request %s): %s",
                      getattr(request.state, "request_id", "?"), _redact(str(exc))[:200])
            queue.put_nowait(sse("error", ErrorDetail(**error("INTERNAL", "Unexpected error; request id shown.").to_dict())))
        finally:
            queue.put_nowait(None)

    async def consume() -> AsyncIterator[str]:
        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=SSE_PING_SECONDS)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if item is None:
                    return
                yield item
        finally:
            if not producer.done():
                producer.cancel()

    return StreamingResponse(
        consume(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _refine_streaming_response(
    request: Request,
    raw: bytes,
    html: str,
    instructions: str,
    timeout_seconds: float,
) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue()

    async def produce():
        allowed_stages = {
            "preparing",
            "rendering",
            "scoring",
            "refining",
            "calling_model",
            "generating",
            "postprocessing",
        }

        def emit(client_event: StreamEvent):
            if client_event.kind == "status":
                text = client_event.text if client_event.text in allowed_stages else "preparing"
                queue.put_nowait(
                    sse(
                        "status",
                        StatusData(
                            stage=text,
                            note=client_event.note or None,
                            model=client_event.model or None,
                            provider=client_event.provider or None,
                        ),
                    )
                )

        def emit_refine(data: dict):
            queue.put_nowait(sse("refine", RefineEventData(**data)))

        try:
            result = await asyncio.wait_for(
                _run_refine(request, raw, html, instructions, on_event=emit, on_refine=emit_refine),
                timeout=timeout_seconds,
            )
            queue.put_nowait(sse("result", result))
        except VisionCraftError as exc:
            queue.put_nowait(sse("error", ErrorDetail(**_public_detail(exc))))
        except (asyncio.TimeoutError, TimeoutError):
            exc = error("REFINE_FAILED", "Refinement took too long. Try again or simplify the page.")
            queue.put_nowait(sse("error", ErrorDetail(**_public_detail(exc))))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - never leave an SSE stream hanging
            log.error(
                "Unhandled error in /api/refine (request %s): %s",
                getattr(request.state, "request_id", "?"),
                _redact(str(exc))[:200],
            )
            queue.put_nowait(sse("error", ErrorDetail(**error("INTERNAL", "Unexpected error; request id shown.").to_dict())))
        finally:
            queue.put_nowait(None)

    async def consume() -> AsyncIterator[str]:
        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=SSE_PING_SECONDS)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if item is None:
                    return
                yield item
        finally:
            if not producer.done():
                producer.cancel()

    return StreamingResponse(
        consume(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
