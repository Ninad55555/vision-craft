from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
)

from app.settings import Settings
from src.core.errors import VisionCraftError
from src.core.hf_client import StreamEvent, VLMClient


class FakeHTTPResponse:
    def __init__(self, status: int, headers: dict | None = None):
        self.status_code = status
        self.headers = headers or {}
        self.request = SimpleNamespace()


def status_error(cls, status: int, message: str, headers: dict | None = None):
    return cls(message, response=FakeHTTPResponse(status, headers), body=None)


class FakeChunk:
    def __init__(self, content: str | None = None, finish: str | None = None, usage: dict | None = None):
        delta = SimpleNamespace(content=content) if content is not None or finish else None
        self.choices = [SimpleNamespace(delta=delta, finish_reason=finish)] if (content is not None or finish) else []
        self.usage = usage


class FakeStream:
    def __init__(self, script: list):
        self._script = list(script)
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        while self._script:
            item = self._script.pop(0)
            if isinstance(item, BaseException):
                raise item
            if isinstance(item, tuple) and item[0] == "usage":
                return FakeChunk(usage=item[1])
            content, finish = item
            return FakeChunk(content=content, finish=finish)
        raise StopAsyncIteration

    async def aclose(self):
        self.closed = True


class FakeCompletions:
    def __init__(self, behaviors: list):
        self._behaviors = list(behaviors)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        behavior = self._behaviors.pop(0)
        if isinstance(behavior, BaseException):
            raise behavior
        return FakeStream(behavior)


class FakeClient:
    def __init__(self, behaviors: list):
        self.chat = SimpleNamespace(completions=FakeCompletions(behaviors))

    async def close(self):
        pass


def make_settings(**overrides) -> Settings:
    base = {
        "hf_token": "test-token",
        "hf_base_url": "http://localhost:9/v1",
        "hf_model_id": "primary-model",
        "hf_fallback_model_ids": "fallback-a,fallback-b",
        "max_retries": 2,
        "max_output_tokens": 100,
        "request_timeout_seconds": 5,
    }
    base.update(overrides)
    return Settings(**base)


def collect(client: VLMClient, messages=None):
    async def _run():
        events = []
        try:
            async for event in client.stream(messages or [{"role": "user", "content": "hi"}]):
                events.append(event)
        except VisionCraftError as exc:
            return events, exc
        return events, None

    return asyncio.run(_run())


def done_event(events: list[StreamEvent]) -> StreamEvent:
    return next(e for e in events if e.kind == "done")


def test_success_path():
    fake = FakeClient([[("Hello", None), (" world", "stop"), ("usage", {"prompt_tokens": 10, "completion_tokens": 20})]])
    events, err = collect(VLMClient(settings_obj=make_settings(), client=fake))
    assert err is None
    assert [e.kind for e in events] == ["status", "delta", "delta", "done"]
    assert events[0].model == "primary-model"
    done = events[-1]
    assert done.finish_reason == "stop"
    assert done.usage == {"prompt_tokens": 10, "completion_tokens": 20}


def test_retry_on_429_then_success(monkeypatch):
    sleeps: list[float] = []

    async def _fake_sleep(s: float):
        sleeps.append(s)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    fake = FakeClient([
        status_error(RateLimitError, 429, "rate limited"),
        [(("ok", "stop"))],
    ])
    events, err = collect(VLMClient(settings_obj=make_settings(max_retries=1), client=fake))
    assert err is None
    assert done_event(events).finish_reason == "stop"
    assert len(fake.chat.completions.calls) == 2
    assert sleeps and sleeps[0] == pytest.approx(1.5)


def test_retry_after_header_respected(monkeypatch):
    seen: list[float] = []

    async def _fake_sleep(s: float):
        seen.append(s)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    fake = FakeClient([
        status_error(RateLimitError, 429, "slow down", {"retry-after": "7"}),
        [(("ok", "stop"))],
    ])
    events, err = collect(VLMClient(settings_obj=make_settings(max_retries=1), client=fake))
    assert err is None
    assert seen == [7.0]


def test_404_falls_back_to_next_model():
    fake = FakeClient([
        status_error(NotFoundError, 404, "model not found"),
        [(("ok", "stop"))],
        [(("unused", "stop"))],
    ])
    events, err = collect(VLMClient(settings_obj=make_settings(max_retries=0), client=fake))
    assert err is None
    statuses = [e for e in events if e.kind == "status"]
    assert [s.model for s in statuses] == ["primary-model", "fallback-a"]
    assert statuses[1].note == "Falling back to fallback-a"
    assert done_event(events).model == "fallback-a"
    assert done_event(events).note == "Falling back to fallback-a"


def test_401_fails_without_fallback():
    fake = FakeClient([status_error(AuthenticationError, 401, "bad key"), [(("x", "stop"))]])
    events, err = collect(VLMClient(settings_obj=make_settings(), client=fake))
    assert err is not None and err.code == "AUTH_FAILED"
    assert len(fake.chat.completions.calls) == 1


def test_402_is_credits_exhausted():
    fake = FakeClient([status_error(APIStatusError, 402, "payment required")])
    _, err = collect(VLMClient(settings_obj=make_settings(), client=fake))
    assert err is not None and err.code == "CREDITS_EXHAUSTED"


def test_credit_text_on_400_is_credits_exhausted():
    fake = FakeClient([status_error(BadRequestError, 400, "you have exceeded your monthly credits")])
    _, err = collect(VLMClient(settings_obj=make_settings(), client=fake))
    assert err is not None and err.code == "CREDITS_EXHAUSTED"


def test_error_after_first_delta_never_retries():
    fake = FakeClient([
        [("partial", None), status_error(APIStatusError, 500, "boom")],
        [(("second", "stop"))],
    ])
    events, err = collect(VLMClient(settings_obj=make_settings(max_retries=3), client=fake))
    assert err is not None and err.code == "UPSTREAM_ERROR"
    assert [e.text for e in events if e.kind == "delta"] == ["partial"]
    assert len(fake.chat.completions.calls) == 1


def test_stream_options_rejection_retries_without_them():
    fake = FakeClient([
        status_error(BadRequestError, 400, "unrecognized stream_options param"),
        [(("ok", "stop"))],
    ])
    events, err = collect(VLMClient(settings_obj=make_settings(max_retries=0), client=fake))
    assert err is None
    assert "stream_options" in fake.chat.completions.calls[0]
    assert "stream_options" not in fake.chat.completions.calls[1]
    assert done_event(events).finish_reason == "stop"


def test_all_models_fail_gives_model_unavailable():
    fake = FakeClient([
        status_error(NotFoundError, 404, "nope"),
        status_error(NotFoundError, 404, "nope"),
        status_error(NotFoundError, 404, "nope"),
    ])
    _, err = collect(VLMClient(settings_obj=make_settings(max_retries=0), client=fake))
    assert err is not None and err.code == "MODEL_UNAVAILABLE"
    assert "primary-model" in err.message and "fallback-b" in err.message


def test_missing_token_short_circuits():
    events, err = collect(VLMClient(settings_obj=make_settings(hf_token=""), client=FakeClient([])))
    assert err is not None and err.code == "AUTH_MISSING"
    assert events == []


def test_connection_error_retries_then_falls_back(monkeypatch):
    async def _fake_sleep(s: float):
        pass

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    conn_err = APIConnectionError(request=SimpleNamespace())
    fake = FakeClient([conn_err, conn_err, [(("ok", "stop"))]])
    events, err = collect(VLMClient(settings_obj=make_settings(max_retries=1), client=fake))
    assert err is None
    assert done_event(events).model == "fallback-a"
