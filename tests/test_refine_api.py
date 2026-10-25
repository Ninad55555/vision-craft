from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import api as api_module
from app.settings import Settings
from src.core.errors import VisionCraftError, error
from src.generator.sanitize import make_standalone
from src.refine.service import RefineOutcome

DOC = "<!DOCTYPE html><html><body><p>original</p></body></html>"
CORRECTED = "<!DOCTYPE html><html><body><p>corrected</p></body></html>"


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (15, 23, 42)).save(buf, format="PNG")
    return buf.getvalue()


def make_settings(**overrides) -> Settings:
    base = {
        "hf_token": "test-token",
        "hf_model_id": "test-model",
        "hf_fallback_model_ids": "",
        "groq_api_key": "",
        "google_api_key": "",
        "max_upload_mb": 10,
        "image_max_side": 1600,
        "max_image_payload_kb": 3000,
        "app_access_key": "",
        "rate_limit_per_minute": 60,
        "enable_refine_loop": True,
        "refine_target_score": 0.9,
        "refine_min_improvement": 0.01,
    }
    base.update(overrides)
    return Settings(**base)


class FakeRefineService:
    def __init__(self, *, fail: bool = False):
        self.calls = 0
        self.fail = fail

    async def refine(self, *, html, prepared, instructions, client, on_status=None, on_refine=None, is_disconnected=None):
        self.calls += 1
        if self.fail:
            raise error("REFINE_FAILED", "renderer exploded")
        if on_status:
            on_status("rendering")
            on_status("scoring")
            on_status("refining")
        data = {
            "initial": 0.42,
            "candidate": 0.78,
            "final": 0.78,
            "kept": True,
            "improvement": 0.36,
            "meaningful": True,
        }
        if on_refine:
            on_refine(data)
        _, report = make_standalone(CORRECTED)
        return RefineOutcome(
            html=CORRECTED,
            initial=0.42,
            candidate=0.78,
            final=0.78,
            kept=True,
            improvement=0.36,
            meaningful=True,
            target=0.9,
            warnings=["refine warning"],
            model="refine-model",
            provider="test",
            finish_reason="stop",
            sanitize=report,
            usage={"prompt_tokens": 3, "completion_tokens": 4},
            elapsed_ms=12,
        )


@pytest.fixture()
def settings(monkeypatch):
    s = make_settings()
    monkeypatch.setattr(api_module, "get_settings", lambda: s)
    return s


@pytest.fixture()
def fake_service():
    service = FakeRefineService()
    api_module.app.state.refine_factory = lambda: service
    yield service
    api_module.app.state.refine_factory = None


def parse_sse(text: str):
    events = []
    for block in text.strip().split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
        if name:
            events.append((name, json.loads(data) if data else None))
    return events


def post_refine(c: TestClient, **data):
    payload = {"html": DOC, "instructions": "keep the nav", "stream": "true"}
    payload.update(data)
    return c.post(
        "/api/refine",
        files={"image": ("shot.png", png_bytes(), "image/png")},
        data=payload,
    )


def test_config_exposes_refine_enabled(settings):
    with TestClient(api_module.app) as c:
        r = c.get("/api/config")
    assert r.status_code == 200
    assert r.json()["refine_enabled"] is True


def test_refine_disabled_403(monkeypatch):
    monkeypatch.setattr(api_module, "get_settings", lambda: make_settings(enable_refine_loop=False))
    with TestClient(api_module.app) as c:
        r = post_refine(c)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "REFINE_DISABLED"


def test_refine_requires_provider(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "get_settings",
        lambda: make_settings(hf_token="", groq_api_key="", google_api_key=""),
    )
    with TestClient(api_module.app) as c:
        r = post_refine(c, stream="false")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "AUTH_MISSING"


def test_refine_sse_happy_path(settings, fake_service):
    api_module.app.state.rate_hits.clear()
    with TestClient(api_module.app) as c:
        r = post_refine(c)
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    events = parse_sse(r.text)
    names = [name for name, _ in events]
    assert names.count("status") == 4
    assert "refine" in names
    assert names[-1] == "result"
    result = events[-1][1]
    assert "corrected" in result["html"]
    assert result["similarity"] == {
        "initial": 0.42,
        "candidate": 0.78,
        "final": 0.78,
        "kept": True,
        "improvement": 0.36,
        "meaningful": True,
        "target": 0.9,
    }
    assert result["usage"] == {"prompt_tokens": 3, "completion_tokens": 4}
    assert "refine warning" in result["warnings"]
    assert fake_service.calls == 1


def test_refine_non_stream_json(settings, fake_service):
    api_module.app.state.rate_hits.clear()
    with TestClient(api_module.app) as c:
        r = post_refine(c, stream="false")
    assert r.status_code == 200
    body = r.json()
    assert body["similarity"]["final"] == 0.78
    assert body["model"] == "refine-model"


def test_refine_service_failure_sse_error(settings):
    api_module.app.state.rate_hits.clear()
    failing = FakeRefineService(fail=True)
    api_module.app.state.refine_factory = lambda: failing
    try:
        with TestClient(api_module.app) as c:
            r = post_refine(c)
    finally:
        api_module.app.state.refine_factory = None
    events = parse_sse(r.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "REFINE_FAILED"


def test_refine_rate_limited(monkeypatch, fake_service):
    monkeypatch.setattr(api_module, "get_settings", lambda: make_settings(rate_limit_per_minute=1))
    api_module.app.state.rate_hits.clear()
    with TestClient(api_module.app) as c:
        assert post_refine(c, stream="false").status_code == 200
        r = post_refine(c, stream="false")
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "RATE_LIMITED"


def test_refine_missing_html_is_422(settings, fake_service):
    api_module.app.state.rate_hits.clear()
    with TestClient(api_module.app) as c:
        r = c.post(
            "/api/refine",
            files={"image": ("shot.png", png_bytes(), "image/png")},
            data={"stream": "false"},
        )
    assert r.status_code == 422
