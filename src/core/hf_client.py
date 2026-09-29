"""Hugging Face Inference API adapter with optional local fallback."""

from __future__ import annotations

import base64
import io
import os
import time
from typing import Any

from PIL import Image

from src.core.local_vlm import LocalVLM


class InferenceError(RuntimeError):
    """Raised when remote and configured local inference both fail."""


class VisionCraftClient:
    """Run multimodal chat against HF Serverless Inference or local Transformers."""

    def __init__(self, config: dict[str, Any], token: str | None = None) -> None:
        model_config = config.get("model", {})
        self.model_id = os.getenv("HF_MODEL_ID", model_config.get("hf_model_id", "Qwen/Qwen2.5-VL-3B-Instruct"))
        self.token = token or os.getenv("HF_TOKEN")
        self.timeout = float(os.getenv("VISIONCRAFT_TIMEOUT", model_config.get("timeout_seconds", 90)))
        self.max_new_tokens = int(model_config.get("max_new_tokens", 900))
        self.temperature = float(model_config.get("temperature", 0.1))
        self.enable_local_fallback = _env_bool(
            "VISIONCRAFT_ENABLE_LOCAL_FALLBACK", model_config.get("enable_local_fallback", False)
        )
        self.local_model_id = os.getenv("VISIONCRAFT_LOCAL_MODEL_ID", model_config.get("local_model_id", "HuggingFaceTB/SmolVLM-500M-Instruct"))
        self.local_load_in_4bit = _env_bool("VISIONCRAFT_LOCAL_4BIT", model_config.get("local_load_in_4bit", False))
        self._client: Any = None
        self._local: LocalVLM | None = None

    def generate(self, image: Image.Image, system_prompt: str, user_prompt: str) -> str:
        """Generate a single response using an image and text prompt."""
        if not self.token:
            if self.enable_local_fallback:
                return self._run_local(image, system_prompt, user_prompt)
            raise InferenceError("HF_TOKEN is required for remote inference; configure local fallback to run offline.")

        image_data_url = _image_data_url(image)
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ]
        try:
            return self._generate_remote(messages)
        except Exception as exc:
            if self.enable_local_fallback:
                try:
                    return self._run_local(image, system_prompt, user_prompt)
                except Exception as local_exc:
                    raise InferenceError(f"Hugging Face inference failed ({exc}); local fallback failed ({local_exc}).") from local_exc
            raise InferenceError(f"Hugging Face inference failed: {exc}") from exc

    def _generate_remote(self, messages: list[dict[str, Any]]) -> str:
        """Call the serverless endpoint with a small retry budget for transient failures."""
        if self._client is None:
            try:
                from huggingface_hub import InferenceClient
            except ImportError as exc:
                raise InferenceError("Install requirements.txt to use Hugging Face inference.") from exc
            self._client = InferenceClient(model=self.model_id, token=self.token, timeout=self.timeout)

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self._client.chat_completion(
                    messages=messages,
                    max_tokens=self.max_new_tokens,
                    temperature=self.temperature,
                )
                content = response.choices[0].message.content
                if isinstance(content, list):
                    return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
                if not isinstance(content, str) or not content.strip():
                    raise InferenceError("The inference endpoint returned an empty response.")
                return content
            except Exception as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt == 2 or status not in {None, 408, 429, 500, 502, 503, 504}:
                    raise
                time.sleep(0.75 * (attempt + 1))
        raise InferenceError(f"Inference retries exhausted: {last_error}")

    def _run_local(self, image: Image.Image, system_prompt: str, user_prompt: str) -> str:
        if self._local is None:
            self._local = LocalVLM(self.local_model_id, load_in_4bit=self.local_load_in_4bit)
        return self._local.generate(image, system_prompt, user_prompt, self.max_new_tokens, self.temperature)


def _image_data_url(image: Image.Image) -> str:
    image_buffer = io.BytesIO()
    image.convert("RGB").save(image_buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(image_buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}
