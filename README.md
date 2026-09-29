# VisionCraft

VisionCraft is a lightweight multimodal assistant for screenshot UI grounding and React/Tailwind reconstruction. It requests normalized bounding boxes on a shared integer grid from 0 to 1000, draws those boxes over the screenshot, and extracts generated JSX.

## Requirements

- Python 3.10 or newer
- A Hugging Face token with access to Inference Providers for hosted inference
- Optional local inference: a compatible CPU or CUDA PyTorch setup. The default local model is SmolVLM-500M; Qwen2.5-VL-3B can also be configured, but needs substantially more memory.

Hosted inference is the default and does not download model weights. Local fallback is opt-in. 4-bit BitsAndBytes is optional and is only listed for Linux; Windows users can use the HF API or a compatible local PyTorch setup without this flag.

## Setup

```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `HF_TOKEN` in the current shell or add it to `.env` and load it with your preferred environment-variable tool. VisionCraft reads environment variables directly and does not automatically parse `.env` files. Never commit a real token.

For a lean server install, you can omit the training-only dependencies (`datasets`, `peft`, `trl`, and `bitsandbytes`) and keep the packages needed for the API/demo/inference. Hosted inference needs a token and a model supported by the selected Hugging Face provider. Model/provider availability and free-tier limits can change; transient throttles are retried, but are not bypassed.

## Run

Start the API from the repository root:

```powershell
uvicorn app.api:app --reload
```

Open `http://127.0.0.1:8000/docs` to submit a screenshot to `POST /predict`. The response includes grid boxes, a base64-encoded PNG overlay, the cleaned React code, and a lightweight JSX validity warning. `GET /health` does not load a model.

Launch the interactive Gradio demo in a second terminal:

```powershell
python -m app.ui
```

The dashboard shows the annotated screenshot, extracted JSX, and a best-effort preview inside a sandboxed iframe. Its preview uses browser CDN scripts and generated code; treat model output as untrusted and do not paste secrets into prompts.

## CLI

```powershell
python scripts/test_inference.py path\to\screenshot.png --prompt "Find the search field"
```

The CLI saves `visioncraft-overlay.png` by default. Pass `--output` to choose a different path.

## Local inference

Set `VISIONCRAFT_ENABLE_LOCAL_FALLBACK=true` and optionally `VISIONCRAFT_LOCAL_MODEL_ID=HuggingFaceTB/SmolVLM-500M-Instruct`. Weights load lazily on the first request. To request low-VRAM 4-bit loading, set `VISIONCRAFT_LOCAL_4BIT=true` on a supported Linux/CUDA environment with a compatible BitsAndBytes build. Local model compatibility depends on your Transformers, PyTorch, hardware, and model card; failures are returned with a clear inference error.

## Dataset and fine-tuning

`src/dataset/loader.py` adapts common JSON/JSONL RICO and ScreenSpot annotation keys to a ChatML-like record. Dataset exports vary, so verify image paths and annotation units against the source before training. Pixel boxes are normalized independently by width and height; set `bbox_normalized: true` when input boxes already use the 0-1000 grid.

The QLoRA script is a training starter, not a universal VLM trainer. Multimodal collators, supported auto-model classes, and LoRA target modules vary by model. Validate against the selected model card and run a tiny dataset first:

```powershell
python scripts/fine_tune_qlora.py --dataset data\train.jsonl --model HuggingFaceTB/SmolVLM-500M-Instruct --steps 10
```

## Configuration

Defaults live in `configs/config.yaml`. `HF_TOKEN`, `HF_MODEL_ID`, `VISIONCRAFT_BACKEND`, `VISIONCRAFT_ENABLE_LOCAL_FALLBACK`, `VISIONCRAFT_LOCAL_MODEL_ID`, `VISIONCRAFT_LOCAL_4BIT`, `VISIONCRAFT_TIMEOUT`, and `VISIONCRAFT_CONFIG` can be set as environment variables. HF is the primary backend; local execution is used only when explicitly enabled (including as fallback).
