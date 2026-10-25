from __future__ import annotations

import asyncio
import io

import pytest
from PIL import Image

from app.settings import Settings
from src.core.errors import VisionCraftError, error
from src.core.hf_client import StreamEvent
from src.core.image_prep import PreparedImage
from src.refine.render import RenderResult
from src.refine.service import RefineService

ORIGINAL = "<!DOCTYPE html><html><body><p>original</p></body></html>"
CORRECTED = "<!DOCTYPE html><html><body><p>corrected</p></body></html>"


def png_bytes(color=(20, 30, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color).save(buf, format="PNG")
    return buf.getvalue()


def prepared() -> PreparedImage:
    image = Image.new("RGB", (100, 100), (255, 255, 255))
    return PreparedImage(
        data_url="data:image/png;base64,AAA",
        mime="image/png",
        width=100,
        height=100,
        orig_width=100,
        orig_height=100,
        pil=image,
    )


def make_settings(**overrides) -> Settings:
    base = {
        "enable_refine_loop": True,
        "refine_target_score": 0.9,
        "refine_min_improvement": 0.01,
        "refine_render_timeout_seconds": 5,
        "refine_timeout_seconds": 30,
        "hf_token": "test-token",
    }
    base.update(overrides)
    return Settings(**base)


class FakeRenderer:
    def __init__(self, images: list[bytes], blocked: list[int] | None = None):
        self.images = list(images)
        self.blocked = list(blocked or [])
        self.htmls: list[str] = []
        self.closed = False

    async def render(self, html: str, width: int, height: int) -> RenderResult:
        self.htmls.append(html)
        blocked = self.blocked.pop(0) if self.blocked else 0
        return RenderResult(png=self.images.pop(0), width=width, height=height, blocked_requests=blocked)

    async def aclose(self) -> None:
        self.closed = True


class StubClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def stream(self, messages):
        self.calls += 1
        for item in self.script:
            if isinstance(item, BaseException):
                raise item
            yield item


def pass_script(html: str = CORRECTED, finish_reason: str = "stop"):
    return [
        StreamEvent(kind="status", text="calling_model", model="refine-model", provider="test"),
        StreamEvent(kind="delta", text="```html\n", model="refine-model"),
        StreamEvent(kind="delta", text=html + "\n```", model="refine-model"),
        StreamEvent(
            kind="done",
            model="refine-model",
            provider="test",
            finish_reason=finish_reason,
            usage={"prompt_tokens": 10, "completion_tokens": 20},
        ),
    ]


def run(
    service: RefineService,
    client: StubClient,
    *,
    html: str = ORIGINAL,
    on_status=None,
    on_refine=None,
):
    return asyncio.run(
        service.refine(
            html=html,
            prepared=prepared(),
            instructions="keep it clean",
            client=client,
            on_status=on_status,
            on_refine=on_refine,
        )
    )


def test_keeps_better_candidate_and_emits_one_pass():
    renderer = FakeRenderer([png_bytes((0, 0, 0)), png_bytes((255, 255, 255))])
    scores = iter([0.4, 0.82])
    service = RefineService(
        settings_obj=make_settings(),
        renderer=renderer,
        scorer=lambda target, candidate: next(scores),
    )
    client = StubClient(pass_script())
    statuses: list[str] = []
    events: list[dict] = []

    out = run(service, client, on_status=statuses.append, on_refine=events.append)

    assert client.calls == 1
    assert len(renderer.htmls) == 2
    assert out.kept is True
    assert out.initial == pytest.approx(0.4)
    assert out.candidate == pytest.approx(0.82)
    assert out.final == pytest.approx(0.82)
    assert out.improvement == pytest.approx(0.42)
    assert out.meaningful is True
    assert "corrected" in out.html
    assert out.model == "refine-model"
    assert out.usage == {"prompt_tokens": 10, "completion_tokens": 20}
    assert statuses == ["rendering", "scoring", "refining", "scoring"]
    assert len(events) == 1
    assert events[0]["initial"] == pytest.approx(0.4)
    assert events[0]["candidate"] == pytest.approx(0.82)
    assert events[0]["final"] == pytest.approx(0.82)
    assert events[0]["kept"] is True
    assert events[0]["improvement"] == pytest.approx(0.42)
    assert events[0]["meaningful"] is True


def test_keeps_original_when_pass_is_worse():
    renderer = FakeRenderer([png_bytes((0, 0, 0)), png_bytes((255, 0, 0))])
    scores = iter([0.6, 0.5])
    service = RefineService(
        settings_obj=make_settings(),
        renderer=renderer,
        scorer=lambda target, candidate: next(scores),
    )
    client = StubClient(pass_script())
    events: list[dict] = []

    out = run(service, client, on_refine=events.append)

    assert client.calls == 1
    assert out.kept is False
    assert out.candidate == pytest.approx(0.5)
    assert out.final == pytest.approx(0.6)
    assert out.improvement == 0
    assert out.meaningful is False
    assert "original" in out.html
    assert any("did not improve" in warning for warning in out.warnings)
    assert events[0]["kept"] is False


def test_skips_vlm_when_target_already_met():
    renderer = FakeRenderer([png_bytes()])
    service = RefineService(
        settings_obj=make_settings(),
        renderer=renderer,
        scorer=lambda target, candidate: 0.95,
    )
    client = StubClient(pass_script())

    out = run(service, client)

    assert client.calls == 0
    assert len(renderer.htmls) == 1
    assert out.kept is False
    assert out.initial == pytest.approx(0.95)
    assert out.final == pytest.approx(0.95)
    assert any("already" in warning.lower() for warning in out.warnings)


def test_vlm_failure_keeps_original():
    renderer = FakeRenderer([png_bytes()])
    service = RefineService(
        settings_obj=make_settings(),
        renderer=renderer,
        scorer=lambda target, candidate: 0.5,
    )
    client = StubClient([error("UPSTREAM_ERROR", "provider down")])

    out = run(service, client)

    assert client.calls == 1
    assert len(renderer.htmls) == 1
    assert out.kept is False
    assert out.final == pytest.approx(0.5)
    assert "original" in out.html
    assert any("REFINE_PASS_FAILED" in warning for warning in out.warnings)


def test_bad_correction_output_keeps_original():
    renderer = FakeRenderer([png_bytes()])
    service = RefineService(
        settings_obj=make_settings(),
        renderer=renderer,
        scorer=lambda target, candidate: 0.5,
    )
    client = StubClient(
        [
            StreamEvent(kind="delta", text="this is not html"),
            StreamEvent(kind="done", finish_reason="stop"),
        ]
    )

    out = run(service, client)

    assert out.kept is False
    assert "original" in out.html
    assert any("REFINE_PASS_FAILED" in warning for warning in out.warnings)


def test_blocked_requests_are_reported():
    renderer = FakeRenderer([png_bytes(), png_bytes()], blocked=[2, 1])
    scores = iter([0.4, 0.8])
    service = RefineService(
        settings_obj=make_settings(),
        renderer=renderer,
        scorer=lambda target, candidate: next(scores),
    )

    out = run(service, StubClient(pass_script()))

    assert any("Blocked 2" in warning for warning in out.warnings)
    assert any("Blocked 1" in warning for warning in out.warnings)


def test_invalid_current_html_is_rejected():
    service = RefineService(
        settings_obj=make_settings(),
        renderer=FakeRenderer([png_bytes()]),
        scorer=lambda target, candidate: 0.5,
    )
    with pytest.raises(VisionCraftError) as caught:
        run(service, StubClient(pass_script()), html="")
    assert caught.value.code == "INVALID_HTML"


def test_truncated_correction_is_flagged():
    renderer = FakeRenderer([png_bytes(), png_bytes()])
    scores = iter([0.4, 0.8])
    service = RefineService(
        settings_obj=make_settings(),
        renderer=renderer,
        scorer=lambda target, candidate: next(scores),
    )

    out = run(service, StubClient(pass_script(finish_reason="length")))

    assert out.kept is True
    assert out.truncated is True
    assert out.finish_reason == "length"
