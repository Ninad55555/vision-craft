"""FastAPI endpoint for screenshot grounding and React/Tailwind generation."""

from __future__ import annotations

import base64
import io
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

from src.core.hf_client import InferenceError, VisionCraftClient
from src.core.prompt_builder import build_messages, load_config
from src.dataset.normalizer import GRID_SIZE
from src.generator.code_cleaner import clean_react_code, validate_react_code
from src.grounding.box_parser import parse_boxes
from src.grounding.visualizer import draw_boxes


ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="VisionCraft", version="0.1.0", description="Lightweight screenshot grounding and UI code generation")


class PredictResponse(BaseModel):
    """Structured inference result returned by ``POST /predict``."""

    boxes: list[dict[str, Any]]
    grid_size: int
    image_width: int
    image_height: int
    overlay_png_base64: str
    react_code: str
    code_valid: bool
    code_warning: str | None = None
    raw_response: str


@lru_cache(maxsize=1)
def _get_config() -> dict[str, Any]:
    config_path = Path(os.getenv("VISIONCRAFT_CONFIG", ROOT / "configs" / "config.yaml"))
    return load_config(config_path)


@lru_cache(maxsize=1)
def _get_client() -> VisionCraftClient:
    return VisionCraftClient(_get_config())


@app.get("/health")
def health() -> dict[str, str]:
    """Report service availability without triggering model loading."""
    return {"status": "ok"}


@app.post("/predict", response_model=PredictResponse)
async def predict(
    image: UploadFile = File(...),
    prompt: str = Form(default="Identify the visible UI elements and recreate the interface."),
) -> PredictResponse:
    """Accept an image and prompt; return grid boxes, an overlay, and React code."""
    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")
    if len(payload) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be 20 MB or smaller.")
    try:
        with Image.open(io.BytesIO(payload)) as uploaded:
            original = uploaded.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="Uploaded file is not a supported image.") from exc

    config = _get_config()
    grounding_config = config.get("grounding", {})
    inference_image = original.copy()
    max_side = int(grounding_config.get("max_image_side", 1600))
    inference_image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    system_prompt, user_prompt = build_messages(prompt, config)
    try:
        raw_response = _get_client().generate(inference_image, system_prompt, user_prompt)
    except InferenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    grid_size = int(grounding_config.get("grid_size", GRID_SIZE))
    boxes = parse_boxes(raw_response, grid_size)
    code = clean_react_code(raw_response)
    code_valid, code_warning = validate_react_code(code)
    color_values = grounding_config.get("box_color", [20, 210, 170])
    overlay = draw_boxes(
        original,
        boxes,
        color=tuple(int(channel) for channel in color_values),
        width=int(grounding_config.get("box_width", 3)),
    )
    output = io.BytesIO()
    overlay.save(output, format="PNG")
    return PredictResponse(
        boxes=boxes,
        grid_size=grid_size,
        image_width=original.width,
        image_height=original.height,
        overlay_png_base64=base64.b64encode(output.getvalue()).decode("ascii"),
        react_code=code,
        code_valid=code_valid,
        code_warning=code_warning,
        raw_response=raw_response,
    )


@app.exception_handler(InferenceError)
async def inference_error_handler(_request: Any, exc: InferenceError) -> JSONResponse:
    """Normalize inference failures raised outside the route's main call."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})
