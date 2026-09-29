"""Render normalized grounding boxes over UI screenshots."""

from __future__ import annotations

from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageFont

from src.dataset.normalizer import denormalize_box


def draw_boxes(
    image: Image.Image,
    boxes: Sequence[dict[str, Any]],
    color: tuple[int, int, int] = (20, 210, 170),
    width: int = 3,
) -> Image.Image:
    """Return an RGBA screenshot with translucent fills, outlines, and labels."""
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()
    for index, item in enumerate(boxes, start=1):
        coords = item.get("box", item.get("bbox"))
        if not isinstance(coords, (list, tuple)) or len(coords) != 4:
            continue
        x1, y1, x2, y2 = denormalize_box(coords, base.width, base.height)
        if x2 <= x1 or y2 <= y1:
            continue
        label = str(item.get("label") or f"element {index}")
        draw.rectangle((x1, y1, x2, y2), fill=(*color, 48), outline=(*color, 255), width=max(1, width))
        text_bounds = draw.textbbox((0, 0), label, font=font)
        label_width = text_bounds[2] - text_bounds[0] + 10
        label_height = text_bounds[3] - text_bounds[1] + 6
        label_top = max(0, y1 - label_height)
        draw.rectangle((x1, label_top, min(base.width, x1 + label_width), label_top + label_height), fill=(*color, 235))
        draw.text((x1 + 5, label_top + 2), label, fill=(8, 25, 28, 255), font=font)
    return Image.alpha_composite(base, overlay).convert("RGB")
