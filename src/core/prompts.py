from __future__ import annotations

import re
from pathlib import Path

from src.core.image_prep import PreparedImage

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

SYSTEM: str = (PROMPT_DIR / "system.md").read_text(encoding="utf-8")
USER_TEMPLATE: str = (PROMPT_DIR / "user.md").read_text(encoding="utf-8")

MAX_INSTRUCTIONS = 1000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_instructions(instructions: str) -> str:
    text = _CONTROL.sub("", instructions or "")
    return text[:MAX_INSTRUCTIONS]


def build_messages(img: PreparedImage, palette: list[str], instructions: str) -> list[dict]:
    user_text = USER_TEMPLATE.format(
        width=img.width,
        height=img.height,
        palette=", ".join(palette) if palette else "none",
        instructions=sanitize_instructions(instructions),
    )
    return [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": img.data_url}},
            ],
        },
    ]
