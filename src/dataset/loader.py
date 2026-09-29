"""Small adapters for turning RICO/ScreenSpot annotations into ChatML records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from .normalizer import normalize_box


def load_annotations(path: str | Path) -> list[dict[str, Any]]:
    """Load JSON/JSONL annotations from a RICO- or ScreenSpot-style export."""
    annotation_path = Path(path)
    if not annotation_path.is_file():
        raise FileNotFoundError(f"Annotation file not found: {annotation_path}")
    text = annotation_path.read_text(encoding="utf-8")
    if annotation_path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        payload = json.loads(text)
        rows = payload if isinstance(payload, list) else payload.get("data", [payload])
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Expected a JSON object or list of annotation objects")
    return rows


def to_chatml(
    records: list[dict[str, Any]],
    image_root: str | Path,
    grid_size: int = 1000,
) -> Iterator[dict[str, Any]]:
    """Yield image-grounding examples in a ChatML-like messages structure.

    Common RICO keys (``image``, ``bounds``) and ScreenSpot keys (``img_filename``,
    ``bbox``/``target``/``instruction``) are accepted. Coordinates in source data
    are treated as pixels unless ``bbox_normalized`` is true.
    """
    root = Path(image_root)
    for record in records:
        image_name = _first(record, "image", "img_filename", "image_path", "file_name")
        instruction = _first(record, "instruction", "query", "target", "text", default="Locate the target UI element")
        if not image_name:
            continue
        image_path = root / str(image_name)
        boxes = _extract_boxes(record)
        if boxes and not record.get("bbox_normalized", False):
            from PIL import Image

            with Image.open(image_path) as image:
                boxes = [normalize_box(box, image.width, image.height, grid_size) for box in boxes]
        elif boxes:
            boxes = [[round(float(value)) for value in box] for box in boxes]
        response = " ".join(
            f"<grounding><box>[{box[0]}, {box[1]}, {box[2]}, {box[3]}]</box></grounding>"
            for box in boxes
        ) or "No annotated target box."
        yield {
            "messages": [
                {"role": "system", "content": "Locate UI elements precisely on a 0-1000 coordinate grid."},
                {"role": "user", "content": [{"type": "image", "path": str(image_path)}, {"type": "text", "text": str(instruction)}]},
                {"role": "assistant", "content": response},
            ]
        }


def _first(record: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return default


def _extract_boxes(record: dict[str, Any]) -> list[list[float]]:
    candidates = _first(record, "bbox", "box", "bounds", "bounding_box")
    if candidates is None and isinstance(record.get("target"), dict):
        candidates = _first(record["target"], "bbox", "box", "bounds")
    if candidates is None:
        return []
    if isinstance(candidates, dict):
        candidates = [candidates]
    if isinstance(candidates, (list, tuple)) and len(candidates) == 4 and all(
        isinstance(value, (int, float)) for value in candidates
    ):
        candidates = [candidates]
    result: list[list[float]] = []
    for candidate in candidates:
        if isinstance(candidate, dict):
            if all(key in candidate for key in ("x1", "y1", "x2", "y2")):
                result.append([candidate[key] for key in ("x1", "y1", "x2", "y2")])
            elif all(key in candidate for key in ("x", "y", "width", "height")):
                result.append([candidate["x"], candidate["y"], candidate["x"] + candidate["width"], candidate["y"] + candidate["height"]])
        elif isinstance(candidate, (list, tuple)) and len(candidate) == 4:
            result.append([float(value) for value in candidate])
    return result
