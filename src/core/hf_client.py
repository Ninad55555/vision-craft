from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)

from src.core.errors import VisionCraftError, error

StreamKind = Literal["status", "delta", "done"]

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


@dataclass
class StreamEvent:
    kind: StreamKind
    text: str = ""
    model: str = ""
    finish_reason: str | None = None
    usage: dict | None = None
    note: str = ""


class _Fallback(Exception):
    """Move on to the next model (or retry same model without stream_options)."""

    def __init__(self, retry_same_model: bool = False):
        super().__init__()
        self.retry_same_model = retry_same_model


class _Retry(Exception):
    def __init__(self, delay_seconds: float):
        super().__init__()
        self.delay_seconds = delay_seconds


def _exc_message(exc: BaseException) -> str:
    return str(exc)[:500]


def _exc_status(exc: BaseException) -> int | None:
    return getattr(exc, "status_code", None)


def _retry_after_seconds(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        value = headers.get("retry-after")
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _usage_dict(usage: Any) -> dict | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        return {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        }
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if prompt is None and completion is None:
        return None
    return {"prompt_tokens": prompt, "completion_tokens": completion}


def _is_credit_error(status: int | None, message: str) -> bool:
    if status == 402:
        return True
    low = message.lower()
    return ("credit" in low and ("exhaust" in low or "deplet" in low or "insufficient" in low)) or (
        "exceeded your monthly" in low
    )


def _is_unsupported_model(status: int | None, message: str) -> bool:
    if status == 404:
        return True
    if status != 400:
        return False
    low = message.lower()
    return "model" in low and ("not supported" in low or "not found" in low)


def _is_stream_options_rejection(status: int | None, message: str) -> bool:
    return status == 400 and "stream_option" in message.lower()


def _backoff(attempt: int) -> float:
    return 1.5 * (2**attempt)


class VLMClient:
    def __init__(self, *, settings_obj=None, client: AsyncOpenAI | None = None):
        from app.settings import settings as default_settings

        self.settings = settings_obj or default_settings
        self._client = client or AsyncOpenAI(
            base_url=self.settings.hf_base_url,
            api_key=self.settings.hf_token,
            timeout=self.settings.request_timeout_seconds,
            max_retries=0,
        )

    async def aclose(self) -> None:
        await self._client.close()

    async def stream(self, messages: list[dict]) -> AsyncIterator[StreamEvent]:
        """Yield status/delta/done events across the primary + fallback models."""
        if not self.settings.hf_token:
            raise error("AUTH_MISSING", "Server has no HF_TOKEN set. Add it to .env and restart.")

        models = [self.settings.hf_model_id, *self.settings.fallback_models]
        tried: list[str] = []

        for index, model in enumerate(models):
            tried.append(model)
            note = f"Falling back to {model}" if index > 0 else ""
            yield StreamEvent(kind="status", text="calling_model", model=model, note=note)

            attempt = 0
            use_stream_options = True
            while True:
                try:
                    async for event in self._stream_once(model, messages, use_stream_options, attempt):
                        if event.kind == "done" and note:
                            event.note = note
                        yield event
                    return
                except _Fallback as hop:
                    if hop.retry_same_model:
                        use_stream_options = False
                        continue
                    break  # next model
                except _Retry as later:
                    attempt += 1
                    await asyncio.sleep(later.delay_seconds)
                    continue

        raise error(
            "MODEL_UNAVAILABLE",
            "None of the configured models is available: "
            + ", ".join(tried)
            + ". Run scripts/list_models.py to pick one that is live today.",
        )

    async def _stream_once(
        self, model: str, messages: list[dict], use_stream_options: bool, attempt: int
    ) -> AsyncIterator[StreamEvent]:
        """One attempt against one model. Raises _Retry, _Fallback, or VisionCraftError."""
        max_retries = max(0, self.settings.max_retries)
        request: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": self.settings.max_output_tokens,
            "temperature": self.settings.temperature,
            "stream": True,
        }
        if use_stream_options:
            request["stream_options"] = {"include_usage": True}

        emitted_delta = False
        try:
            response = await self._client.chat.completions.create(**request)
            finish_reason: str | None = None
            usage: dict | None = None
            try:
                async for chunk in response:
                    chunk_usage = getattr(chunk, "usage", None)
                    if chunk_usage:
                        usage = _usage_dict(chunk_usage)
                    choices = getattr(chunk, "choices", None) or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = getattr(choice.delta, "content", None) if choice.delta else None
                    if delta:
                        emitted_delta = True
                        yield StreamEvent(kind="delta", text=delta, model=model)
                    if getattr(choice, "finish_reason", None):
                        finish_reason = choice.finish_reason
            finally:
                try:
                    await response.close()
                except Exception:
                    pass
            yield StreamEvent(kind="done", model=model, finish_reason=finish_reason, usage=usage)
            return
        except (VisionCraftError, _Fallback, _Retry):
            raise
        except (APIConnectionError, APITimeoutError) as exc:
            if emitted_delta:
                raise error("UPSTREAM_ERROR", "The provider connection dropped mid-stream.") from exc
            if attempt >= max_retries:
                raise _Fallback() from exc
            raise _Retry(_backoff(attempt)) from exc
        except APIStatusError as exc:
            status = _exc_status(exc)
            message = _exc_message(exc)
            if _is_stream_options_rejection(status, message):
                if not use_stream_options:
                    raise error("UPSTREAM_ERROR", "The provider rejected the request (HTTP 400).") from exc
                raise _Fallback(retry_same_model=True) from exc
            if status in (401, 403):
                raise error(
                    "AUTH_FAILED",
                    "Hugging Face rejected the token. It needs a fine-grained token with the "
                    "'Make calls to Inference Providers' permission.",
                ) from exc
            if _is_credit_error(status, message):
                raise error(
                    "CREDITS_EXHAUSTED",
                    "Monthly Hugging Face inference credits are used up. Upgrade, wait for the reset, "
                    "or point HF_BASE_URL at another provider.",
                ) from exc
            if _is_unsupported_model(status, message):
                raise _Fallback() from exc
            if status in RETRYABLE_STATUSES and not emitted_delta:
                if attempt >= max_retries:
                    raise _Fallback() from exc
                override = _retry_after_seconds(exc)
                raise _Retry(override if override is not None else _backoff(attempt)) from exc
            if emitted_delta:
                raise error("UPSTREAM_ERROR", "The provider errored mid-stream.") from exc
            if status is not None and status >= 500:
                raise _Fallback() from exc
            raise error(
                "UPSTREAM_ERROR",
                f"The provider returned an error (HTTP {status})." if status else "The provider returned an error.",
            ) from exc
        except Exception as exc:  # noqa: BLE001 - unknown SDK failure
            if emitted_delta:
                raise error("UPSTREAM_ERROR", "The provider errored mid-stream.") from exc
            raise error("UPSTREAM_ERROR", "The provider request failed.") from exc
