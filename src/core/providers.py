"""OpenAI-compatible provider adapters used by the inference cascade."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from openai import AsyncOpenAI


class BaseLLMProvider(ABC):
    """Common provider contract. `messages` preserves multimodal prompt structure."""

    name: str
    model: str

    def __init__(self, *, name: str, model: str, client: AsyncOpenAI):
        self.name = name
        self.model = model
        self.client = client

    @abstractmethod
    async def generate(self, prompt: str, image_bytes: bytes | None = None) -> str:
        """Generate text from a prompt and optional image."""

    async def stream(self, messages: list[dict[str, Any]], *, max_tokens: int, temperature: float):
        """Yield the provider's streaming response chunks."""
        return await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
        )

    async def aclose(self) -> None:
        await self.client.close()


class OpenAICompatibleProvider(BaseLLMProvider):
    async def generate(self, prompt: str, image_bytes: bytes | None = None) -> str:
        content: Any = prompt
        if image_bytes is not None:
            import base64

            content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")}},
            ]
        response = await self.client.chat.completions.create(
            model=self.model, messages=[{"role": "user", "content": content}], stream=False,
        )
        return response.choices[0].message.content or ""

