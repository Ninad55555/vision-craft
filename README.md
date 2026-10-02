# VisionCraft

Upload a UI screenshot → a Hugging Face–hosted Qwen vision-language model reads
it → you get **one standalone `.html` file** (HTML + CSS + JS inline, zero
external dependencies) to preview, copy, and download.

Output is **a first draft, not pixel-perfect**. Expect approximated spacing,
system fonts, and placeholder graphics. You will hand-edit the result.

## Requirements

- Python 3.10+ (developed on 3.13)
- A Hugging Face token with the **“Make calls to Inference Providers”**
  permission, plus inference credits (free accounts get roughly $0.10/month;
  plan on PRO or another OpenAI-compatible provider for real use)

## Setup

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env        # then set HF_TOKEN
python scripts\list_models.py      # confirm the model is live today
```

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python scripts/list_models.py
```

## Frontend (React)

```powershell
cd frontend
npm install
npm run dev     # dev UI at http://localhost:5173 (proxies /api to :8000)
npm run build   # emits frontend/dist, served by FastAPI below
```

## Run

```powershell
uvicorn app.api:app --host 127.0.0.1 --port 8000
# UI at http://127.0.0.1:8000 (frontend/dist if built, else legacy web/)  ·  health at /health  ·  API docs at /docs
```

Pick, drag-drop, or paste (`Ctrl+V`) a screenshot, optionally add
instructions, and click **Generate**. Switch the preview between Fit / 768 /
390 px, then **Copy** or **Download** the single file.

Smoke test without the browser:

```powershell
python scripts\smoke_test.py path\to\screenshot.png --out out.html
```

## Configuration (`.env`)

Everything is configured via `.env` (loaded with pydantic-settings — the old
“does not parse `.env`” bug is gone). Any OpenAI-compatible provider works:
just change `HF_BASE_URL`. Swap models with `HF_MODEL_ID` /
`HF_FALLBACK_MODEL_IDS` — no code changes. Set `APP_ACCESS_KEY` if the server
is reachable by anyone but you, otherwise strangers spend your credits.

Model status (checked 2026-10-01 via `list_models.py`): the largest Qwen VL
actually served is `Qwen/Qwen3-VL-235B-A22B-Instruct` (default), with
`Qwen2.5-VL-72B-Instruct` and `Qwen3-VL-30B-A3B-Instruct` as fallbacks.
`Qwen3-VL-8B-Instruct` does not exist on the router. Re-run
`list_models.py` whenever quality drops — availability shifts without notice.

## Tests

```powershell
pytest -q
```

64 unit tests, all mocked (no network): image prep, palette, prompts,
streaming client (retry/fallback/typed errors), HTML cleaner, sanitizer
(hostile fixture proves zero external URLs survive), API routes (SSE ordering,
auth, rate limit, access key, token-leak, timeouts), settings.

The 15-image test set lives in `tests/eval_images/` (PNG + HTML source +
`.txt` ground truth); results go in `docs/RESULTS.md`.

## Known limitations

- Output is a first draft. Wrong spacing, approximated fonts, placeholder
  images, and occasional missing sections are normal.
- Quality depends heavily on the model; small models (≤ ~8B) struggle on dense
  pages. Prefer the largest VL model your credits allow.
- Free Hugging Face accounts have very small monthly inference credits; expect
  `CREDITS_EXHAUSTED` and plan for a paid tier or another provider.
- Very tall pages lose fidelity toward the bottom.
- Generated JavaScript is filtered and sandboxed, but treat every output as
  untrusted until you read it: preview runs in `sandbox="allow-scripts"` with
  its own restrictive CSP, downloads are sanitized the same way.

## Security notes

- `HF_TOKEN` never leaves the server (responses, errors, and logs are
  redacted; there is a test for this).
- Uploads are processed in memory and never written to disk.
- Per-IP rate limiting (`RATE_LIMIT_PER_MINUTE`) and an optional
  `APP_ACCESS_KEY` protect your credits.
- Text inside a screenshot can carry prompt-injection (“ignore previous
  instructions”); the model has no tools and its only output channel is
  sanitized, sandboxed HTML.
- Never commit `.env`. Check with `git ls-files | findstr .env` —
  only `.env.example` belongs in git.

## Layout

```
app/        FastAPI: api.py (routes/SSE/guards), settings.py, schemas.py
src/core/   errors.py, image_prep.py, palette.py, prompts(.py,/*.md), hf_client.py
src/generator/  html_cleaner.py, sanitize.py
web/        vanilla frontend: index.html, app.js, styles.css
scripts/    list_models.py, smoke_test.py
tests/      unit tests + fixtures/ + eval_images/ (15-image set)
docs/       RESULTS.md
```
