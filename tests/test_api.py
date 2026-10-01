from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import api as api_module
from app.settings import Settings
from src.core.errors import error
from src.core.hf_client import StreamEvent

FIX = Path(__file__).resolve().parent / "fixtures"

DOC = "<!DOCTYPE html><html><head><title>t</title></head><body><p>hello</p></body></html>"


class StubClient:
    def __init__(self, script):
        self.script = list(script)

    async def stream(self, messages):
        for item in self.script:
            if isinstance(item, BaseException):
                raise item
            yield item


def success_script():
    return [
        StreamEvent(kind="status", text="calling_model", model="test-model"),
        StreamEvent(kind="delta", text=DOC[:40], model="test-model"),
        StreamEvent(kind="delta", text=DOC[40:], model="test-model"),
        StreamEvent(kind="done", model="test-model", finish_reason="stop",
                    usage={"prompt_tokens": 11, "completion_tokens": 22}),
    ]


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (15, 23, 42)).save(buf, format="PNG")
    return buf.getvalue()


def make_settings(**overrides) -> Settings:
    base = {
        "hf_token": "test-token",
        "hf_model_id": "test-model",
        "hf_fallback_model_ids": "",
        "max_upload_mb": 10,
        "image_max_side": 1600,
        "max_image_payload_kb": 3000,
        "app_access_key": "",
        "rate_limit_per_minute": 60,
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def settings(monkeypatch):
    s = make_settings()
    monkeypatch.setattr(api_module, "get_settings", lambda: s)
    return s


@pytest.fixture()
def client(settings):
    api_module.app.state.rate_hits.clear()
    api_module.app.state.client_factory = lambda: StubClient(success_script())
    with TestClient(api_module.app) as c:
        yield c
    api_module.app.state.client_factory = None


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


def post_image(c: TestClient, raw: bytes | None = None, **data):
    files = {"image": ("shot.png", raw if raw is not None else png_bytes(), "image/png")}
    return c.post("/api/generate", files=files, data=data)


def test_health_ok_without_hf_call(settings):
    with TestClient(api_module.app) as c:
        r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["hf_token_configured"] is True
    assert body["model"] == "test-model"


def test_config_shape(settings):
    with TestClient(api_module.app) as c:
        r = c.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["max_upload_mb"] == 10
    assert body["accepted_types"] == ["image/png", "image/jpeg", "image/webp"]
    assert body["requires_access_key"] is False


def test_sse_happy_path_ordering(client):
    r = post_image(client, stream="true")
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    kinds = [name for name, _ in parse_sse(r.text)]
    assert kinds[0] == "status"
    assert "delta" in kinds
    assert kinds[-1] == "result"
    result = parse_sse(r.text)[-1][1]
    assert result["model"] == "test-model"
    assert "hello" in result["html"]
    assert result["usage"] == {"prompt_tokens": 11, "completion_tokens": 22}
    assert result["elapsed_ms"] >= 0
    assert result["image"]["width"] == 300


def test_non_stream_returns_json(client):
    r = post_image(client, stream="false")
    assert r.status_code == 200
    body = r.json()
    assert "hello" in body["html"]
    assert body["finish_reason"] == "stop"


def test_missing_token_sse_error(monkeypatch):
    monkeypatch.setattr(api_module, "get_settings", lambda: make_settings(hf_token=""))
    api_module.app.state.client_factory = lambda: StubClient(success_script())
    try:
        with TestClient(api_module.app) as c:
            r = post_image(c, stream="true")
        kinds = [n for n, _ in parse_sse(r.text)]
        assert kinds[-1] == "error"
        assert parse_sse(r.text)[-1][1]["code"] == "AUTH_MISSING"
    finally:
        api_module.app.state.client_factory = None


def test_missing_token_non_stream_503(monkeypatch):
    monkeypatch.setattr(api_module, "get_settings", lambda: make_settings(hf_token=""))
    api_module.app.state.client_factory = lambda: StubClient(success_script())
    try:
        with TestClient(api_module.app) as c:
            r = post_image(c, stream="false")
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "AUTH_MISSING"
    finally:
        api_module.app.state.client_factory = None


def test_access_key_required(monkeypatch):
    monkeypatch.setattr(api_module, "get_settings", lambda: make_settings(app_access_key="secret"))
    api_module.app.state.client_factory = lambda: StubClient(success_script())
    try:
        with TestClient(api_module.app) as c:
            r = post_image(c, stream="false")
            assert r.status_code == 401
            assert r.json()["detail"]["code"] == "ACCESS_DENIED"
            r2 = c.post(
                "/api/generate",
                files={"image": ("s.png", png_bytes(), "image/png")},
                data={"stream": "false"},
                headers={"X-Access-Key": "secret"},
            )
            assert r2.status_code == 200
    finally:
        api_module.app.state.client_factory = None


def test_rate_limit_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(api_module, "get_settings", lambda: make_settings(rate_limit_per_minute=1))
    api_module.app.state.rate_hits.clear()
    api_module.app.state.client_factory = lambda: StubClient(success_script())
    try:
        with TestClient(api_module.app) as c:
            assert post_image(c, stream="false").status_code == 200
            r = post_image(c, stream="false")
            assert r.status_code == 429
            assert r.json()["detail"]["code"] == "RATE_LIMITED"
            assert "Retry-After" in r.headers
    finally:
        api_module.app.state.client_factory = None


def test_oversize_upload_413(client):
    r = post_image(client, raw=png_bytes(), stream="false")
    assert r.status_code == 200  # fits
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(api_module, "get_settings", lambda: make_settings(max_upload_mb=0))
        # max_upload_mb=0 -> any non-empty file is too large
        r2 = post_image(client, raw=png_bytes(), stream="false")
        assert r2.status_code == 413
        assert r2.json()["detail"]["code"] == "IMAGE_TOO_LARGE"


def test_corrupt_upload_400(client):
    r = post_image(client, raw=b"not an image", stream="false")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "IMAGE_INVALID"


def test_upstream_error_surfaces_as_sse_error(client):
    api_module.app.state.client_factory = lambda: StubClient(
        [error("CREDITS_EXHAUSTED", "no credits left")]
    )
    try:
        r = post_image(client, stream="true")
        events = parse_sse(r.text)
        assert events[-1][0] == "error"
        assert events[-1][1]["code"] == "CREDITS_EXHAUSTED"
    finally:
        api_module.app.state.client_factory = lambda: StubClient(success_script())


def test_token_never_leaks(monkeypatch):
    secret = "SUPERSECRET-TOKEN-12345"
    monkeypatch.setattr(api_module, "get_settings", lambda: make_settings(hf_token=secret))
    api_module.app.state.rate_hits.clear()
    api_module.app.state.client_factory = lambda: StubClient(
        [error("UPSTREAM_ERROR", f"provider says {secret} is bad")]
    )
    try:
        with TestClient(api_module.app) as c:
            assert secret not in c.get("/health").text
            assert secret not in c.get("/api/config").text
            r = post_image(c, stream="true")
            assert secret not in r.text
            r2 = post_image(c, stream="false")
            assert secret not in r2.text
    finally:
        api_module.app.state.client_factory = None


def test_security_headers_present(client):
    r = post_image(client, stream="false")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "Content-Security-Policy" in r.headers
    assert "X-Request-ID" in r.headers


def test_model_field_ignored(client):
    r = post_image(client, stream="false", model="evil-model:free")
    assert r.status_code == 200
    assert r.json()["model"] == "test-model"


class SlowStub:
    async def stream(self, messages):
        await asyncio.sleep(30)
        if False:  # keep this an async generator
            yield None


def test_pipeline_timeout_non_stream(monkeypatch):
    monkeypatch.setattr(api_module, "get_settings", lambda: make_settings(request_timeout_seconds=0.05))
    api_module.app.state.rate_hits.clear()
    api_module.app.state.client_factory = SlowStub
    try:
        with TestClient(api_module.app) as c:
            r = post_image(c, stream="false")
        assert r.status_code == 504
        assert r.json()["detail"]["code"] == "UPSTREAM_TIMEOUT"
    finally:
        api_module.app.state.client_factory = None


def test_pipeline_timeout_stream(monkeypatch):
    monkeypatch.setattr(api_module, "get_settings", lambda: make_settings(request_timeout_seconds=0.05))
    api_module.app.state.rate_hits.clear()
    api_module.app.state.client_factory = SlowStub
    try:
        with TestClient(api_module.app) as c:
            r = post_image(c, stream="true")
        events = parse_sse(r.text)
        assert events[-1][0] == "error"
        assert events[-1][1]["code"] == "UPSTREAM_TIMEOUT"
    finally:
        api_module.app.state.client_factory = None
