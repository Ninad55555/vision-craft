"""CLI smoke test for screenshot grounding and JSX generation."""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image

from src.core.hf_client import VisionCraftClient
from src.core.prompt_builder import build_messages, load_config
from src.generator.code_cleaner import clean_react_code, validate_react_code
from src.grounding.box_parser import parse_boxes
from src.grounding.visualizer import draw_boxes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Path to a screenshot image")
    parser.add_argument("--prompt", default="Identify the main UI controls and recreate this screen.")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "config.yaml")
    parser.add_argument("--output", type=Path, default=Path("visioncraft-overlay.png"))
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"Image not found: {args.image}")

    config = load_config(args.config)
    system_prompt, user_prompt = build_messages(args.prompt, config)
    with Image.open(args.image) as source:
        image = source.convert("RGB")
    response = VisionCraftClient(config).generate(image, system_prompt, user_prompt)
    grid_size = int(config.get("grounding", {}).get("grid_size", 1000))
    boxes = parse_boxes(response, grid_size)
    code = clean_react_code(response)
    valid, warning = validate_react_code(code)
    overlay = draw_boxes(image, boxes)
    overlay.save(args.output)
    print(f"Grounding boxes ({grid_size} grid): {boxes}")
    print(f"Overlay written to: {args.output}")
    print(f"React JSX valid: {valid}" + (f" ({warning})" if warning else ""))
    print("\n--- React JSX ---\n" + code)
    if not valid:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
