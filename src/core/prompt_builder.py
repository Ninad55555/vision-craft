"""Build concise multimodal instructions for grounding and UI reconstruction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load YAML configuration, falling back to the repository default."""
    config_path = Path(path or "configs/config.yaml")
    if not config_path.is_file():
        raise FileNotFoundError(f"VisionCraft config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


def build_messages(instruction: str, config: dict[str, Any]) -> tuple[str, str]:
    """Return system/user text; the caller attaches the screenshot as image input."""
    grid_size = int(config.get("grounding", {}).get("grid_size", 1000))
    templates = config.get("prompts", {})
    system = str(templates.get("system", "You are a visual grounding assistant."))
    user_template = str(templates.get("user", "Inspect the screenshot. Request: {instruction}. Grid: {grid_size}."))
    user = user_template.format(instruction=instruction.strip() or "Describe and recreate this interface", grid_size=grid_size)
    return system, user
