"""Gradio side-by-side demo for grounding and generated React UI code."""

from __future__ import annotations

import html
import os
import re
import sys
from pathlib import Path
from typing import Any

import gradio as gr
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api import _get_client, _get_config
from src.core.hf_client import InferenceError
from src.core.prompt_builder import build_messages
from src.generator.code_cleaner import clean_react_code, validate_react_code
from src.grounding.box_parser import parse_boxes
from src.grounding.visualizer import draw_boxes


def run_demo(image: Image.Image | None, prompt: str) -> tuple[Any, str, str, str]:
    """Run inference and return annotated image, isolated preview, code, status."""
    if image is None:
        return None, "<div style='padding:1rem;color:#555'>Upload a screenshot to preview generated UI.</div>", "", "Upload a screenshot to begin."
    config = _get_config()
    system_prompt, user_prompt = build_messages(prompt, config)
    inference_image = image.convert("RGB")
    max_side = int(config.get("grounding", {}).get("max_image_side", 1600))
    inference_image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    try:
        raw = _get_client().generate(inference_image, system_prompt, user_prompt)
    except InferenceError as exc:
        return image, "<div style='padding:1rem'>Preview unavailable.</div>", "", f"Inference error: {exc}"

    ground_config = config.get("grounding", {})
    boxes = parse_boxes(raw, int(ground_config.get("grid_size", 1000)))
    overlay = draw_boxes(
        image.convert("RGB"),
        boxes,
        color=tuple(ground_config.get("box_color", [20, 210, 170])),
        width=int(ground_config.get("box_width", 3)),
    )
    code = clean_react_code(raw)
    valid, warning = validate_react_code(code)
    status = f"Found {len(boxes)} grounded element(s)."
    if warning:
        status += f" JSX check: {warning}"
    return overlay, _preview_iframe(code) if valid else "<div style='padding:1rem'>No JSX component to render.</div>", code, status


def _preview_iframe(code: str) -> str:
    """Create an opaque-origin sandbox for a best-effort JSX preview."""
    code = re.sub(r"^\s*import\s+.*?;?\s*$", "", code, flags=re.MULTILINE)
    code = re.sub(r"\bexport\s+default\s+", "", code)
    code = re.sub(r"\bexport\s+(?=(?:function|const|let|class)\b)", "", code)
    match = re.search(r"\b(?:function|const|let|class)\s+([A-Z][A-Za-z0-9_]*)", code)
    component_name = match.group(1) if match else "App"
    safe_code = code.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    document = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><script src="https://cdn.tailwindcss.com"></script><script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script><script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script><script src="https://unpkg.com/@babel/standalone/babel.min.js"></script></head><body><div id="root"></div><script>
const source = {safe_code!r};
try {{ const compiled = Babel.transform(source, {{presets:['react']}}).code; const factory = new Function('React', compiled + '; return typeof {component_name} !== "undefined" ? {component_name} : null;'); const Component = factory(React); if (!Component) throw new Error('No component export found'); ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Component)); }} catch (error) {{ document.getElementById('root').innerText = 'Preview could not render: ' + error.message; }}
</script></body></html>"""
    return f'<iframe title="Generated React preview" sandbox="allow-scripts" referrerpolicy="no-referrer" style="width:100%;height:440px;border:0;background:#fff" srcdoc="{html.escape(document, quote=True)}"></iframe>'


with gr.Blocks(title="VisionCraft", theme=gr.themes.Soft(primary_hue="teal", neutral_hue="slate")) as demo:
    gr.Markdown("# VisionCraft\nScreenshot grounding and React/Tailwind reconstruction")
    with gr.Row():
        with gr.Column(scale=1):
            input_image = gr.Image(type="pil", label="Screenshot")
            prompt_box = gr.Textbox(label="Target or instruction", value="Identify the visible UI elements and recreate the interface.", lines=2)
            analyze_button = gr.Button("Analyze screenshot", variant="primary")
            status = gr.Textbox(label="Result", interactive=False)
        with gr.Column(scale=1):
            grounded_image = gr.Image(label="Grounded screenshot", type="pil")
            preview = gr.HTML(label="Generated preview")
    code_box = gr.Code(label="React / Tailwind JSX", language="jsx", interactive=False)
    analyze_button.click(run_demo, inputs=[input_image, prompt_box], outputs=[grounded_image, preview, code_box, status])


if __name__ == "__main__":
    demo.launch(server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"), server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")))
