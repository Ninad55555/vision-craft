"""Parse grounding tags and normalize model-produced boxes to the common grid."""

from __future__ import annotations

import re
from typing import Any


BOX_PATTERN = re.compile(r"<box>\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]\s*</box>", re.IGNORECASE)
LABEL_PATTERN = re.compile(r"<label>\s*(.*?)\s*</label>", re.IGNORECASE | re.DOTALL)


def parse_boxes(text: str, grid_size: int = 1000) -> list[dict[str, Any]]:
    """Extract integer-grid boxes, pairing optional labels in response order."""
    labels = [re.sub(r"\s+", " ", match).strip() for match in LABEL_PATTERN.findall(text)]
    boxes: list[dict[str, Any]] = []
    for index, match in enumerate(BOX_PATTERN.finditer(text)):
        coords = [max(0, min(grid_size, round(float(value)))) for value in match.groups()]
        x1, y1, x2, y2 = coords
        if x2 <= x1 or y2 <= y1:
            continue
        boxes.append({"box": coords, "label": labels[index] if index < len(labels) and labels[index] else f"element {len(boxes) + 1}"})
    return boxes
