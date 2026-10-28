# VisionCraft

Upload a UI screenshot -> a Hugging Face-hosted Qwen vision-language model reads
it -> you get **one standalone `.html` file** (HTML + CSS + JS inline, zero
external dependencies) to preview, refine, copy, and download.

Output is **a first draft, not pixel-perfect**. Expect approximated spacing,
system fonts, and placeholder graphics. You will hand-edit the result.

## What it does

- Screenshot -> single-file HTML with copy/download and a live sandboxed preview.
- Tabbed workflow: Preview / Compare / Code (Monaco or plain editor).
- Compare tab with an original-vs-generated opacity overlay.
- Quick instruction presets (dark mode, mobile-first, minimal, accessible,
  hero-only, system fonts) that add to or clear from your directions.
- Recent drafts saved in your browser (last five generations, reopen or remove
  them without spending model credits).
- Optional **one-pass visual refinement**: render the current HTML, compare it
  with the screenshot using SSIM, and ask the model for one correction pass.
  Refinement only runs when you click the button; one click = one pass.
- Provider failover across Hugging Face, Groq, and Google Gemini, with typed
  errors and server-side token redaction.

## Requirements

- Python 3.10+ (developed on 3.13)
- A Hugging Face token with the **"Make calls to Inference Providers"**
  permission, plus inference credits (free accounts get roughly $0.10/month;
  plan on PRO or another OpenAI-compatible provider for real use)
- Optional for refinement: Playwright, scikit-image, numpy, and a browser.
  Microsoft Edge is already available on most Windows machines.

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

### Optional visual-refinement dependencies

```powershell
pip install -r requirements-refine.txt
# Either install Playwright's Chromium:
playwright install chromium
# ...or use the Edge/Chrome already installed:
$env:REFINE_BROWSER_CHANNEL = "msedge"
```

```bash
pip install -r requirements-refine.txt
python -m playwright install chromium
```

The base app and its tests do not import Playwright, scikit-image, or numpy
until refinement is requested. `POST /api/refine` returns
`REFINE_UNAVAILABLE` when those dependencies are missing.

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
# UI at http://127.0.0.1:8000
# health at /health, API docs at /docs
```

Pick, drag-drop, or paste (`Ctrl+V`) a screenshot, optionally add
instructions, and click **Generate**. Switch the preview between Fit / 768 /
390 px, then **Copy** or **Download** the single file.

After a generation, click **Refine match** to run one render -> compare ->
correct pass. The result re-renders in the Compare tab with an opacity slider
and an SSIM score. Click again to run another single pass from the current HTML.

Smoke test without the browser:

```powershell
python scripts\smoke_test.py path\to\screenshot.png --out out.html
```

## Configuration (`.env`)

Everything is configured via `.env` (loaded with pydantic-settings). Any
OpenAI-compatible provider works: just change `HF_BASE_URL`. Swap models with
`HF_MODEL_ID` / `HF_FALLBACK_MODEL_IDS` - no code changes. Set
`APP_ACCESS_KEY` if the server is reachable by anyone but you, otherwise
strangers spend your credits.

Model status (checked 2026-10-01 via `list_models.py`): the largest Qwen VL
actually served is `Qwen/Qwen3-VL-235B-A22B-Instruct` (default), with
`Qwen2.5-VL-72B-Instruct` and `Qwen3-VL-30B-A3B-Instruct` as fallbacks.
`Qwen3-VL-8B-Instruct` does not exist on the router. Re-run
`list_models.py` whenever quality drops - availability shifts without notice.

### Refinement settings

| Variable | Default | Meaning |
|---|---|---|
| `ENABLE_REFINE_LOOP` | `false` | Exposes the Refine button and `/api/refine`. |
| `REFINE_TARGET_SCORE` | `0.90` | If the initial SSIM is at or above this, no model call is made. |
| `REFINE_MIN_IMPROVEMENT` | `0.01` | Labels a gain as meaningful; a real smaller gain is still kept. |
| `REFINE_RENDER_TIMEOUT_SECONDS` | `20` | Per-render browser timeout. |
| `REFINE_TIMEOUT_SECONDS` | `360` | Whole one-pass request timeout. |
| `REFINE_BROWSER_CHANNEL` | empty | Empty auto-detects Chromium, then Edge, then Chrome. Use `msedge` or `chrome` to skip detection. |

Refinement is deliberately manual. There is no multi-iteration setting and no
automatic second model call.

## Tests

```powershell
pytest -q
```

82 unit/API tests, all mocked (no network): image prep, palette, prompts,
streaming client, HTML cleaner, sanitizer, API routes, settings, and the
one-pass refinement service/endpoint. The 15-image test set lives in
`tests/eval_images/` (PNG + HTML source + `.txt` ground truth); results go in
`docs/RESULTS.md`.

Known issue on this checkout: 10 provider-client retry/fallback tests in
`tests/test_client.py` are red because the tests expect model-level retries and
HF model fallbacks that are not implemented in the current
`src/core/hf_client.py`. They are independent of the refinement work.

## Known limitations

- Output is a first draft. Wrong spacing, approximated fonts, placeholder
  images, and occasional missing sections are normal.
- Quality depends heavily on the model; small models (~8B) struggle on dense
  pages. Prefer the largest VL model your credits allow.
- Free Hugging Face accounts have very small monthly inference credits; expect
  `CREDITS_EXHAUSTED` and plan for a paid tier or another provider.
- Very tall pages lose fidelity toward the bottom.
- Refinement is one pass. If the corrected render scores lower, the previous
  HTML is kept; a second click starts a fresh pass.
- Generated JavaScript is filtered and sandboxed, but treat every output as
  untrusted until you read it: preview runs in `sandbox="allow-scripts"` with
  its own restrictive CSP, downloads are sanitized the same way.

## Security notes

- `HF_TOKEN` never leaves the server (responses, errors, and logs are
  redacted; there is a test for this).
- Uploads are processed in memory and never written to disk.
- Refinement renders with JavaScript enabled but blocks every external request
  (only `data:`, `about:`, and `blob:` URLs are allowed) and reports blocked
  requests in the response warnings.
- Per-IP rate limiting (`RATE_LIMIT_PER_MINUTE`) covers both `/api/generate` and
  `/api/refine`; `APP_ACCESS_KEY` protects all `/api/*` routes.
- Text inside a screenshot can carry prompt-injection ("ignore previous
  instructions"); the model has no tools and its only output channel is
  sanitized, sandboxed HTML.
- Never commit `.env`. Check with `git ls-files | findstr .env` - only
  `.env.example` belongs in git.

## Layout

```
app/        FastAPI: api.py (routes/SSE/guards), settings.py, schemas.py
src/core/   errors.py, image_prep.py, palette.py, prompts(.py,/*.md), hf_client.py
src/generator/  html_cleaner.py, sanitize.py
src/refine/ render.py (Playwright), similarity.py (SSIM), service.py (one pass)
frontend/   React 19 + Vite + TypeScript UI
web/        legacy vanilla frontend
scripts/    list_models.py, smoke_test.py, eval.py
tests/      unit tests + fixtures/ + eval_images/ (15-image set)
docs/       RESULTS.md
```
