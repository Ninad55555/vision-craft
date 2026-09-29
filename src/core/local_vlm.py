"""Lazy local Transformers pipeline for lightweight CPU or low-VRAM inference."""

from __future__ import annotations

from typing import Any

from PIL import Image


class LocalVLM:
    """Load a compact image-text model only when local inference is requested."""

    def __init__(self, model_id: str, load_in_4bit: bool = False) -> None:
        self.model_id = model_id
        self.load_in_4bit = load_in_4bit
        self._pipeline: Any = None

    def _load(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError("Install the optional Transformers and PyTorch dependencies for local inference.") from exc

        model_kwargs: dict[str, Any] = {"device_map": "auto", "torch_dtype": "auto"}
        if self.load_in_4bit:
            try:
                from transformers import BitsAndBytesConfig
            except ImportError as exc:
                raise RuntimeError("4-bit loading requires a compatible Transformers/bitsandbytes installation.") from exc
            model_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True)
        try:
            self._pipeline = pipeline(
                task="image-text-to-text",
                model=self.model_id,
                model_kwargs=model_kwargs,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Could not load local model '{self.model_id}'. Use a compatible lightweight VLM and available RAM/VRAM: {exc}"
            ) from exc
        return self._pipeline

    def generate(
        self,
        image: Image.Image,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 900,
        temperature: float = 0.5,
    ) -> str:
        """Generate a response from a local image-text pipeline."""
        model_pipeline = self._load()
        messages = [
            {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image.convert("RGB")},
                    {"type": "text", "text": user_prompt},
                ],
            },
        ]
        output = model_pipeline(
            text=messages,
            max_new_tokens=max_new_tokens,
            do_sample=temperature > 0,
            temperature=max(temperature, 0.01),
        )
        return _extract_generated_text(output)


def _extract_generated_text(output: Any) -> str:
    """Handle common Transformers image-text pipeline output shapes."""
    try:
        generated: Any = output[0]["generated_text"]
    except (IndexError, KeyError, TypeError) as exc:
        raise RuntimeError(f"Unexpected local model output: {type(output).__name__}") from exc
    if isinstance(generated, str):
        return generated
    if isinstance(generated, list):
        for message in reversed(generated):
            if isinstance(message, dict) and message.get("role") == "assistant":
                content = message.get("content", "")
                if isinstance(content, list):
                    return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
                return str(content)
    return str(generated)
