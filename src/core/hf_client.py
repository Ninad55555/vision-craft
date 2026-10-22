from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)

from src.core.errors import AllInferenceProvidersFailedError, VisionCraftError, error
from src.core.providers import OpenAICompatibleProvider

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
    provider: str = ""


class _Fallback(Exception):
    """Move on to the next model (or retry same model without stream_options)."""

    def __init__(self, retry_same_model: bool = False, reason: str = "provider request failed"):
        super().__init__()
        self.retry_same_model = retry_same_model
        self.reason = reason


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
        self.log = logging.getLogger(__name__)
        timeout = self.settings.request_timeout_seconds
        def make_client(base_url: str, api_key: str):
            return AsyncOpenAI(base_url=base_url, api_key=api_key or "unconfigured", timeout=timeout, max_retries=0)
        self.providers = []
        if self.settings.hf_token:
            self.providers.append(OpenAICompatibleProvider(name="Hugging Face", model=self.settings.hf_model_id,
                client=client or make_client(self.settings.hf_base_url, self.settings.hf_token)))
        if self.settings.groq_api_key:
            self.providers.append(OpenAICompatibleProvider(name="Groq", model=self.settings.groq_model_id,
                client=make_client(self.settings.groq_base_url, self.settings.groq_api_key)))
        if self.settings.google_api_key:
            self.log.info("Configured Google Gemini model: %s", self.settings.gemini_model_id)
            self.providers.append(OpenAICompatibleProvider(name="Google Gemini", model=self.settings.gemini_model_id,
                client=make_client("https://generativelanguage.googleapis.com/v1beta/openai/", self.settings.google_api_key)))
        # Keep the injected-client seam for existing integrations and tests.
        self._client = client or (self.providers[0].client if self.providers else None)

    async def aclose(self) -> None:
        seen = set()
        for provider in self.providers:
            if id(provider.client) not in seen:
                seen.add(id(provider.client))
                await provider.aclose()

    async def stream(self, messages: list[dict]) -> AsyncIterator[StreamEvent]:
        """Yield status/delta/done events across the primary + fallback models."""
        if not self.providers and self._client is not None:
            # Compatibility for clients constructed before provider adapters were introduced.
            self.providers = [OpenAICompatibleProvider(name="Hugging Face", model=self.settings.hf_model_id, client=self._client)]
        if not self.providers:
            raise error("AUTH_MISSING", "Configure HF_TOKEN, GROQ_API_KEY, or GOOGLE_API_KEY.")
        failures: dict[str, str] = {}
        providers = self.providers
        for index, provider in enumerate(providers):
            model = provider.model
            note = f"Falling back to {provider.name} ({model})" if index > 0 else ""
            yield StreamEvent(kind="status", text="calling_model", model=model, note=note)

            attempt = 0
            use_stream_options = True
            while True:
                try:
                    async for event in self._stream_once(model, messages, use_stream_options, attempt, provider.client):
                        event.provider = provider.name
                        if event.kind == "done" and note:
                            event.note = note
                        yield event
                    return
                except _Fallback as hop:
                    if hop.retry_same_model:
                        use_stream_options = False
                        continue
                    failures[provider.name] = hop.reason
                    self.log.warning("Inference provider %s failed; trying the next provider: %s", provider.name, hop.reason)
                    break  # next model
                except _Retry as later:
                    attempt += 1
                    await asyncio.sleep(later.delay_seconds)
                    continue

        for provider in providers:
            failures.setdefault(provider.name, "provider was not attempted")
        raise AllInferenceProvidersFailedError(failures)

    async def _stream_once(
        self, model: str, messages: list[dict], use_stream_options: bool, attempt: int, client: AsyncOpenAI
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

        buffered_events: list[StreamEvent] = []
        try:
            response = await client.chat.completions.create(**request)
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
                        buffered_events.append(StreamEvent(kind="delta", text=delta, model=model))
                    if getattr(choice, "finish_reason", None):
                        finish_reason = choice.finish_reason
            finally:
                try:
                    await response.close()
                except Exception:
                    pass
            # Do not expose partial output until the provider has completed successfully.
            # This allows a clean provider failover if a stream drops midway through.
            for event in buffered_events:
                yield event
            yield StreamEvent(kind="done", model=model, finish_reason=finish_reason, usage=usage)
            return
        except (VisionCraftError, _Fallback, _Retry):
            raise
        except (APIConnectionError, APITimeoutError) as exc:
            raise _Fallback(reason=_exc_message(exc)) from exc
        except APIStatusError as exc:
            status = _exc_status(exc)
            message = _exc_message(exc)
            if _is_stream_options_rejection(status, message):
                if not use_stream_options:
                    raise error("UPSTREAM_ERROR", "The provider rejected the request (HTTP 400).") from exc
                raise _Fallback(retry_same_model=True) from exc
            if status in (401, 403):
                raise _Fallback(reason=f"HTTP {status}: {_exc_message(exc)}") from exc
            if _is_credit_error(status, message):
                raise _Fallback(reason=f"HTTP {status}: {_exc_message(exc)}") from exc
            if _is_unsupported_model(status, message):
                raise _Fallback(reason=f"HTTP {status}: {_exc_message(exc)}") from exc
            if status in RETRYABLE_STATUSES:
                raise _Fallback(reason=f"HTTP {status}: {_exc_message(exc)}") from exc
            if status is not None and status >= 500:
                raise _Fallback(reason=f"HTTP {status}: {_exc_message(exc)}") from exc
            raise _Fallback(reason=f"HTTP {status}: {_exc_message(exc)}") from exc
        except Exception as exc:  # noqa: BLE001 - unknown SDK failure
            raise _Fallback(reason=_exc_message(exc)) from exc
