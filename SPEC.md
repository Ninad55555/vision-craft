# VisionCraft — Technical Specification

**Version:** 1.0  **Companion:** `PRD.md`
**Audience:** a developer or AI coding agent building this end to end. Build in milestone order (PRD §11). Do **not** add scope that is not in this document.

---

## 1. Scope delta vs. the current repo (`vision-craft-main`)

The existing repo targets *grounding boxes + React/Tailwind JSX + Gradio + QLoRA*. The new product is *screenshot → single standalone HTML*. Migration:

| Path | Action | Why |
|------|--------|-----|
| `app/api.py` | **Rewrite** | New routes, SSE, rate limit, static mount |
| `app/ui.py` (Gradio) | **Delete** | Replaced by `web/` frontend |
| `src/core/hf_client.py` | **Rewrite** as OpenAI-SDK streaming client | Needs streaming, fallback chain, typed errors |
| `src/core/prompt_builder.py` | **Rewrite** | New prompt, palette hints, no grid/boxes |
| `src/generator/code_cleaner.py` | **Replace** with `html_cleaner.py` + `sanitize.py` | HTML, not JSX |
| `src/core/local_vlm.py` | **Delete** | Local inference out of scope |
| `src/grounding/*` | **Delete** | No bounding boxes |
| `src/dataset/*`, `scripts/fine_tune_qlora.py` | **Delete** | No fine-tuning |
| `configs/config.yaml` | **Delete** | Config moves to `.env` + `settings.py`; prompts move to `.md` files |
| `tests/test_core.py` | **Rewrite** | |
| `**/__pycache__/`, `*.pyc` | **Delete + gitignore** | Committed bytecode |
| `requirements.txt` | **Replace** (§3) | Drops torch/transformers/gradio/peft/trl/bitsandbytes/opencv (multi-GB for nothing) |
| `README.md` | **Rewrite** at M3 | |

**Known bug being fixed:** the current README states the app *does not parse `.env`*. New code loads `.env` via `pydantic-settings` (§4).

## 2. Architecture

```
Browser (web/)                          FastAPI (app/api.py)                    HF Router
─────────────                           ───────────────────                    ─────────
index.html / app.js / styles.css  ───►  POST /api/generate (multipart)
   upload / paste / instructions         │ validate → image_prep → palette
   SSE reader (fetch + ReadableStream)   │ build_messages
   sandboxed <iframe srcdoc>             │ VLMClient.stream()  ───────────────►  /v1/chat/completions
   Code tab · Copy · Download            │   (stream=True, data-URL image)  ◄───  token deltas
                                         │ html_cleaner → sanitize
                                    ◄─── SSE: status | delta | result | error
```

- Single process, no database, no queue, no auth service.
- FastAPI serves the static frontend at `/` and the API under `/api` → **same origin, no CORS needed** locally.
- The HF token exists **only** in server env. Never returned by any endpoint, never logged.

## 3. Tech stack

**Python 3.10+** (repo was built on 3.13; both fine).

`requirements.txt`
```
fastapi>=0.115
uvicorn[standard]>=0.34
python-multipart>=0.0.20
pydantic>=2.7
pydantic-settings>=2.4
openai>=1.50          # used purely as an OpenAI-compatible HTTP client against the HF router
pillow>=10.4
beautifulsoup4>=4.12
lxml>=5.2
python-dotenv>=1.0
sse-starlette>=2.1    # optional; or hand-roll StreamingResponse(media_type="text/event-stream")
```
`requirements-dev.txt`
```
-r requirements.txt
pytest>=8
httpx>=0.27
```
`requirements-refine.txt` (P1/P2 only)
```
-r requirements.txt
playwright>=1.47      # then: playwright install chromium
scikit-image>=0.24
numpy>=1.26
```
After the first successful run, pin exact versions with `pip freeze` into a lock file. Do not trust version pins from the old repo.

**Frontend:** vanilla HTML/CSS/JS, **no framework, no build step, no CDN**. One `index.html`, one `app.js`, one `styles.css`.

## 4. Configuration (`.env` → `app/settings.py`)

```python
# app/settings.py
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    hf_token: str = ""                                   # required for generation
    hf_base_url: str = "https://router.huggingface.co/v1"
    hf_model_id: str = "Qwen/Qwen3-VL-8B-Instruct"
    hf_fallback_model_ids: str = ""                      # comma-separated
    max_output_tokens: int = 8192
    temperature: float = 0.2
    request_timeout_seconds: float = 300
    max_retries: int = 2

    image_max_side: int = 1600
    max_upload_mb: int = 10
    max_image_payload_kb: int = 3000                     # cap on encoded image sent upstream

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    cors_origins: str = "http://127.0.0.1:8000,http://localhost:8000"
    app_access_key: str = ""                             # if set, require header X-Access-Key
    rate_limit_per_minute: int = 6
    log_level: str = "INFO"

    enable_refine_loop: bool = False                     # P1
    refine_max_iterations: int = 2                       # P1

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.hf_fallback_model_ids.split(",") if m.strip()]

settings = Settings()
```
Rules:
- Startup must **not** crash if `HF_TOKEN` is empty; `/health` reports `hf_token_configured: false` and `/api/generate` returns `AUTH_MISSING`.
- Never log `hf_token`. If logging settings, redact it.
- Model IDs may carry an optional provider suffix, e.g. `Qwen/Qwen2.5-VL-72B-Instruct:ovhcloud` (HF router convention). Treat the string as opaque.
- Use **Instruct** variants. If a "Thinking" variant is configured, the cleaner must strip `<think>…</think>` (§5.5) but warn in `/health` that it will be slow and costly.

## 5. Backend modules

Target layout:
```
app/
  __init__.py
  api.py            # FastAPI app, routes, static mount, SSE, rate limit
  settings.py
  schemas.py        # pydantic response/event models
src/
  __init__.py
  core/
    __init__.py
    errors.py       # VisionCraftError + codes
    image_prep.py
    palette.py
    prompts.py
    prompts/system.md
    prompts/user.md
    prompts/refine.md        # P1
    hf_client.py    # VLMClient
  generator/
    __init__.py
    html_cleaner.py
    sanitize.py
  refine/                    # P1 only
    render.py
    similarity.py
    loop.py
web/
  index.html
  app.js
  styles.css
scripts/
  list_models.py
  smoke_test.py
  eval.py                    # P2
tests/
  fixtures/                  # small PNGs: simple.png, rgba.png, tall.png, huge.png, corrupt.bin
  test_image_prep.py
  test_palette.py
  test_html_cleaner.py
  test_sanitize.py
  test_prompts.py
  test_client.py
  test_api.py
.env.example
.env                         # gitignored
.gitignore
README.md
```

### 5.1 `errors.py`

```python
class VisionCraftError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 500, retryable: bool = False): ...
```
Codes and mapping are in §9. All route handlers convert `VisionCraftError` to the JSON error shape (non-stream) or an SSE `error` event (stream).

### 5.2 `image_prep.py`

```python
@dataclass
class PreparedImage:
    data_url: str            # "data:image/jpeg;base64,..."
    mime: str
    width: int               # after downscale
    height: int
    orig_width: int
    orig_height: int
    warnings: list[str]
    pil: Image.Image         # downscaled RGB image (used by palette + refine loop)

def prepare_image(raw: bytes, *, max_side: int, max_upload_bytes: int, max_payload_kb: int) -> PreparedImage
```
Steps, in order:
1. If `len(raw) == 0` → `IMAGE_INVALID`. If `> max_upload_bytes` → `IMAGE_TOO_LARGE` (413).
2. `Image.open(BytesIO(raw))`; `.verify()` then re-open. Format must be PNG, JPEG, or WEBP, else `IMAGE_INVALID` (415). Decompression bomb: set `Image.MAX_IMAGE_PIXELS = 50_000_000`; catch `DecompressionBombError` → `IMAGE_TOO_LARGE`.
3. `ImageOps.exif_transpose`. Animated (n_frames > 1) → use first frame, add warning.
4. Mode handling: `RGBA`/`LA`/`P` with transparency → composite onto white; convert to `RGB`.
5. If `min(w, h) < 64` → `IMAGE_INVALID` ("too small").
6. If `max(w, h) > max_side` → `thumbnail((max_side, max_side), LANCZOS)`.
7. If `height / width > 4` → warning: `"Very tall screenshot: fidelity drops lower on the page."`
8. Encode JPEG quality 92. While encoded size > `max_payload_kb`: reduce quality by 6 (floor 70), then scale dimensions by 0.85. Stop at ≤ cap. (Provider payload limits are undocumented; this keeps requests safe.)
9. Return `PreparedImage`.

### 5.3 `palette.py` and `prompts.py`

```python
def extract_palette(img: Image.Image, k: int = 8) -> list[str]
```
Thumbnail copy to 200 px longest side → `quantize(colors=k, method=MEDIANCUT)` → count pixels per palette index → return hex strings sorted by frequency (`"#0f172a"`). First entry is treated as the page background hint.

```python
def build_messages(img: PreparedImage, palette: list[str], instructions: str) -> list[dict]
```
Returns OpenAI-format messages:
```python
[
  {"role": "system", "content": SYSTEM},
  {"role": "user", "content": [
      {"type": "text", "text": USER_RENDERED},
      {"type": "image_url", "image_url": {"url": img.data_url}},
  ]},
]
```
Prompt files are loaded once at import and rendered with `str.format`-style placeholders `{width} {height} {palette} {instructions}`. `instructions` is truncated to 1000 chars and stripped of control characters.

**`prompts/system.md`** (use verbatim as the starting point; tune only after the M0/eval runs):
```
You are a senior front-end engineer. You convert a UI screenshot into ONE self-contained HTML file.

OUTPUT FORMAT
- Reply with a single ```html code fence containing the complete document, and nothing else. No explanation before or after.
- The document must start with <!DOCTYPE html> and end with </html>. It must be COMPLETE. Never write placeholders such as "...", "rest of content here", or "repeat for other items". Write every element out.

HARD CONSTRAINTS (the file must work offline, double-clicked from disk)
- Inline <style> and inline <script> only. NO external URLs of any kind: no CDN, no Google Fonts, no remote images, no iframes, no @import.
- Fonts: use a system font stack that matches the look (sans-serif, serif, or monospace). Do not reference font files.
- Photos, avatars, logos, illustrations: replace with inline SVG or CSS gradient/solid blocks of the same size and aspect ratio. Icons: simple inline SVG.
- JavaScript: vanilla only, and only for behaviour that is visible or implied in the screenshot (menu/dropdown toggles, tabs, accordions, modals, form state). No network calls, no storage, no eval.

FIDELITY RULES
- Transcribe ALL visible text exactly (case, punctuation, numbers). Do not paraphrase, summarize, or invent content that is not visible.
- Reproduce layout, spacing, alignment, border radius, shadows, and font sizes/weights as faithfully as you can estimate. Match the screenshot's width at desktop size.
- Use the provided color palette hints; define colors as CSS variables on :root.
- Match the screenshot's theme (light/dark). Do not add theme toggles.
- Use semantic HTML (header, nav, main, section, footer, button, label) and basic accessibility (alt text, labels, focus styles).
- Use flexbox/grid. Add at least one @media (max-width: 768px) rule so the layout degrades sensibly on small screens, without changing the desktop appearance.
```

**`prompts/user.md`**:
```
Recreate this screenshot as a single standalone HTML file.

Screenshot size: {width}x{height} px.
Dominant colors (most frequent first; the first is the page background): {palette}.

Additional instructions from the user (may be empty):
{instructions}

Remember: one ```html fence, complete document, no external resources.
```

### 5.4 `hf_client.py` — `VLMClient`

Uses `openai.OpenAI(base_url=settings.hf_base_url, api_key=settings.hf_token, timeout=settings.request_timeout_seconds, max_retries=0)` (retries are handled manually below so they can be reported).

```python
@dataclass
class StreamEvent:
    kind: Literal["status", "delta", "done"]
    text: str = ""                 # for delta
    model: str = ""                # for status/done
    finish_reason: str | None = None
    usage: dict | None = None      # {"prompt_tokens": int, "completion_tokens": int} if provided
    note: str = ""                 # e.g. "fell back to <model>"

class VLMClient:
    def stream(self, messages: list[dict]) -> Iterator[StreamEvent]: ...
```
Behavior:
1. Model order = `[hf_model_id] + fallback_models`.
2. For each model: call `chat.completions.create(model=..., messages=..., max_tokens=settings.max_output_tokens, temperature=settings.temperature, stream=True, stream_options={"include_usage": True})`. If the provider rejects `stream_options` (HTTP 400 mentioning it), retry once without it.
3. Yield `status` (`calling_model`) before the call; yield `delta` per non-empty `choices[0].delta.content`; on the last chunk capture `finish_reason`; capture `usage` if present; yield `done`.
4. Retry policy per model: up to `max_retries` retries with backoff `1.5s * 2**attempt` **only** for 429 (respect `Retry-After` if present), 500, 502, 503, 504, connection errors, and read timeouts **that occur before the first delta**. Never retry after deltas have been emitted (would duplicate output) — instead raise `UPSTREAM_ERROR` with partial text discarded.
5. Move to the next model when: HTTP 404, "model not supported"/"not found" style 400, or retries exhausted on 5xx/429. Emit a `status` event with `note="Falling back to <model>"` and record it in the result warnings.
6. Do **not** fall back (fail immediately) on 401/403 (`AUTH_FAILED`) or 402 (`CREDITS_EXHAUSTED`). Insufficient-credit detection: status 402, or error text containing "credit"/"depleted"/"exceeded your monthly".
7. Total failure → `MODEL_UNAVAILABLE` (503) listing models tried.
8. Never include the token or full request body (it contains the image) in logs or error messages.
9. Client must stop streaming promptly if the downstream HTTP client disconnects (check `await request.is_disconnected()` in the route; close the upstream stream).

### 5.5 `html_cleaner.py`

```python
def clean_model_output(text: str, *, finish_reason: str | None) -> tuple[str, list[str]]
```
Order of operations:
1. Remove `<think>…</think>` blocks (non-greedy, DOTALL), and an unterminated leading `<think>…` through end if no closing tag.
2. Extraction priority: (a) the **largest** ```html fenced block (also accept bare ``` fences containing `<html`/`<!doctype`); (b) text from the first `<!doctype`/`<html` (case-insensitive) to the last `</html>`; (c) if the text starts with `<` treat whole text as HTML; else raise `OUTPUT_NOT_HTML`.
3. If a fence opened but never closed (typical on truncation) take everything after the opening fence.
4. Truncation handling: truncated if `finish_reason == "length"` **or** no `</html>` present. Then: parse with `lxml` (forgiving), re-serialize so tags are closed, append `</body></html>` if needed, add warning `OUTPUT_TRUNCATED`: "The model hit its output limit; the page may be incomplete."
5. Ensure `<!DOCTYPE html>`, `<meta charset="utf-8">`, and `<meta name="viewport" content="width=device-width, initial-scale=1">` exist (insert into `<head>`; create `<head>` if missing).
6. Reject if the final document has no visible text and no elements inside `<body>` → `OUTPUT_NOT_HTML`.
7. Reject (or truncate with warning) if the final size > 1,000,000 bytes.

### 5.6 `sanitize.py` — make it truly standalone

```python
@dataclass
class SanitizeReport:
    removed_scripts: int; removed_links: int; neutralized_css_urls: int
    replaced_images: int; removed_embeds: int; removed_js_blocks: int
    notes: list[str]

def make_standalone(html: str) -> tuple[str, SanitizeReport]
```
Parse with BeautifulSoup + `lxml`. Rules:
- `<script src=…>` where src is `http(s):`, `//`, or any non-`data:` URL → remove.
- `<link>` with `rel` in `stylesheet|preload|prefetch|preconnect|dns-prefetch|icon|modulepreload` and a non-`data:` href → remove.
- `<img>`, `<source>`, `<video poster>`, `<input type=image>` with a non-`data:` src/srcset → replace `src` with an inline SVG placeholder data URI (neutral gray rectangle with the alt text) sized from `width`/`height` attributes, else 400×300. Remove `srcset`. Count in `replaced_images`.
- `<iframe>`, `<object>`, `<embed>`, `<base>`, `<meta http-equiv="refresh">` → remove.
- `<form action>` pointing to non-fragment URL → set `action="#"`, add `onsubmit="return false"` unless already prevented.
- In every `<style>` block and `style=""` attribute: regex-neutralize `@import …;` (remove) and `url(<non-data>)` → `url("")`; remove `@font-face` rules whose `src` is non-data.
- Inline `<script>` blocks containing any of: `fetch(`, `XMLHttpRequest`, `WebSocket`, `EventSource`, `sendBeacon`, `importScripts`, `eval(`, `new Function`, `document.cookie`, `localStorage`, `sessionStorage`, `indexedDB`, `window.open`, `location.href=`/`location.assign(`/`location.replace(` → **remove the whole block**, `removed_js_blocks += 1`, add a note. (Blunt on purpose; a false positive costs one interaction, a false negative costs trust.)
- Inline event-handler attributes (`onclick=` etc.) containing the same patterns → strip that attribute.
- Anchor `href` with `javascript:` → replace with `#`. Keep `http(s)` anchors but add `target="_blank" rel="noopener noreferrer"` (navigation is not a resource load).
- Return serialized HTML with the doctype preserved.

Unit tests must prove, for a hostile fixture, that no `http`/`//` URL remains in any resource-loading attribute or CSS `url()`.

### 5.7 `api.py` — routes

```python
app = FastAPI(title="VisionCraft", version="1.0.0")
# middleware: CORS (settings.cors_origins), request-id, rate limit, access key
# mount: app.mount("/", StaticFiles(directory=ROOT/"web", html=True), name="web")  # AFTER api routes
```
Rate limit: in-memory sliding window per client IP (`settings.rate_limit_per_minute`) on `POST /api/generate` only; exceed → 429 `RATE_LIMITED` with `Retry-After`. Use `X-Forwarded-For` only if an env `TRUST_PROXY=true` is added; default off.
Access key: if `APP_ACCESS_KEY` set, require `X-Access-Key` on `/api/*` except `/health`; compare with `secrets.compare_digest`; failure → 401 `ACCESS_DENIED`.

Concurrency: the generator runs the (blocking) OpenAI stream in a worker thread and bridges to the async SSE generator via `asyncio.Queue`, or uses `AsyncOpenAI` directly. Prefer **`AsyncOpenAI`** to avoid thread bridging; make `VLMClient.stream` an async generator accordingly.

## 6. API contract

### `GET /health`
```json
{ "status": "ok", "hf_token_configured": true, "model": "Qwen/Qwen3-VL-8B-Instruct",
  "fallback_models": [], "refine_enabled": false }
```
Does not call HF.

### `GET /api/config`
Non-secret limits for the frontend:
```json
{ "max_upload_mb": 10, "image_max_side": 1600, "accepted_types": ["image/png","image/jpeg","image/webp"],
  "requires_access_key": false, "model": "Qwen/Qwen3-VL-8B-Instruct" }
```

### `POST /api/generate` — `multipart/form-data`
| Field | Type | Notes |
|-------|------|-------|
| `image` | file | required |
| `instructions` | string | optional, ≤ 1000 chars |
| `stream` | bool | default `true`. `false` returns the final JSON in one response (for curl/tests). |
| `model` | string | **not accepted** from clients in v1 (prevents spending on arbitrary models). Ignore if sent. |

**Streaming response** (`Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`). Send a comment line `: ping` every 15 s. Events:

```
event: status
data: {"stage":"preparing"}          # preparing | calling_model | generating | postprocessing
                                     # may include {"note":"Falling back to <model>"}
event: delta
data: {"text":"<!DOCTYPE html>..."}  # raw model text chunk (may be partial tags)

event: result
data: {
  "html": "<!DOCTYPE html>...",
  "model": "Qwen/Qwen3-VL-8B-Instruct",
  "finish_reason": "stop",
  "truncated": false,
  "warnings": ["Very tall screenshot: ..."],
  "sanitize": {"removed_scripts":0,"removed_links":1,"neutralized_css_urls":2,"replaced_images":3,"removed_embeds":0,"removed_js_blocks":0},
  "palette": ["#0f172a","#1e293b","#38bdf8"],
  "image": {"width":1600,"height":900,"orig_width":2880,"orig_height":1620},
  "usage": {"prompt_tokens":1834,"completion_tokens":5120},   // null if provider omits it
  "elapsed_ms": 48211
}

event: error
data: {"code":"CREDITS_EXHAUSTED","message":"...","retryable":false}
```
Exactly one of `result` or `error` terminates the stream. If the client disconnects, cancel the upstream call.

**Non-streaming** (`stream=false`): `200` with the `result` JSON; errors as `{"detail":{"code":"...","message":"...","retryable":false}}` with the mapped HTTP status.

## 7. Frontend specification (`web/`)

**Files:** `index.html`, `app.js` (ES module, no dependencies), `styles.css`. Served by FastAPI.

**Layout (desktop ≥ 1000 px):** two columns. Left: upload zone → thumbnail + dimensions → instructions textarea → Generate/Cancel. Right: tab bar (`Preview | Code | Compare`*), device toggle, action buttons, content area. Below 1000 px stack vertically. (*Compare is P1; render the tab disabled with a "soon" tooltip until implemented.)

**Behavior:**
1. **Input:** drag-drop onto the zone, click to open the file picker, and a document-level `paste` handler that accepts `image/*` clipboard items. Client-side checks mirror server limits (type, size from `/api/config`) and show inline errors without a network call.
2. **Generate:** `fetch('/api/generate', {method:'POST', body: FormData, signal})` and read `response.body` with a stream reader, parsing SSE manually (split on blank lines; handle `event:`/`data:` fields; ignore `:` comments). Native `EventSource` cannot POST — do not use it.
3. **Progress UI:** stage label from `status`, elapsed timer (updates every 250 ms), approximate token counter = total delta characters / 4 labelled "≈ tokens". Disable Generate, enable Cancel (`AbortController.abort()`).
4. **On `result`:** store `html`; render Preview; fill Code tab; show warnings as a dismissible banner list; show `model`, `elapsed`, and token usage in a small footer.
5. **Preview iframe** (§8): width presets `Fit` (100%), `768`, `390`; centered, scales via CSS container, scrolls inside.
6. **Code tab:** read-only `<pre><code>` (escape HTML; no syntax-highlighting library), line count and byte size. **Copy** uses `navigator.clipboard.writeText` with a textarea fallback.
7. **Download:** `Blob` → object URL → hidden `<a download="visioncraft-YYYYMMDD-HHMMSS.html">` click → revoke URL. 
8. **Regenerate:** reuses the held `File`/Blob and current instructions.
9. **Errors:** map `code` → human message (§9). `retryable: true` shows a Retry button.
10. **Persistence:** none, except `sessionStorage` for `X-Access-Key` if the server requires one. Do not use `localStorage`. History (P1) is an in-memory array.
11. **A11y:** visible focus rings, `aria-live="polite"` on the status line, buttons not divs, labels on all inputs, `prefers-color-scheme` light/dark, `prefers-reduced-motion` respected.
12. **Copy text:** UI must say outputs are "a first draft, not pixel-perfect". No marketing claims.

**Explicitly forbidden in the frontend:** third-party scripts/fonts/CDNs; "Open in new tab" using a Blob/object URL (it would execute generated code **same-origin** with the app); `innerHTML` with model output anywhere except via `srcdoc` of the sandboxed iframe.

## 8. Security requirements

1. **Token isolation:** `HF_TOKEN` never leaves the server; not in `/api/config`, not in errors, not in logs. Add a unit test that greps API responses for the token value.
2. **Preview sandbox:** `<iframe sandbox="allow-scripts" referrerpolicy="no-referrer" srcdoc="…">`. **No** `allow-same-origin`, `allow-top-navigation`, `allow-popups`, `allow-modals`, `allow-forms`.
3. **Preview-only CSP** injected into the `srcdoc` head (not into the downloadable file):
   `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src data:; media-src data:; base-uri 'none'; form-action 'none'">`
4. **Sanitizer (§5.6) runs before the HTML is ever returned**, so downloads are also stripped of external loads.
5. **Upload hardening:** size cap, pixel cap, type allowlist by decoding (not by filename/Content-Type), no persistence to disk (process in memory; never write uploads).
6. **Prompt-injection awareness:** text inside a screenshot can say "ignore previous instructions". The only capability the model has is emitting HTML that is then sanitized and sandboxed; it has no tools. Document this in the README.
7. **Abuse/cost protection:** per-IP rate limit, optional access key, hard `MAX_OUTPUT_TOKENS`, image payload cap, request timeout. Document that deploying publicly without `APP_ACCESS_KEY` lets strangers spend your credits.
8. **Headers:** add `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and a CSP for the app shell itself (`default-src 'self'; frame-src 'self' about:; style-src 'self'; script-src 'self'; img-src 'self' data: blob:`). The srcdoc iframe inherits no network permissions thanks to its own CSP; verify in a manual test that the shell CSP does not break the preview (adjust `frame-src` as needed).
9. **Secrets hygiene:** `.env` in `.gitignore`; only `.env.example` is committed. Ship a pre-commit-style check in README ("run `git ls-files | findstr .env`").

## 9. Error codes

| Code | HTTP | Retryable | UI message (summary) |
|------|------|-----------|----------------------|
| `ACCESS_DENIED` | 401 | no | Enter the access key. |
| `AUTH_MISSING` | 503 | no | Server has no `HF_TOKEN` set. Add it to `.env` and restart. |
| `AUTH_FAILED` | 502 | no | Hugging Face rejected the token. Needs a fine-grained token with the "Make calls to Inference Providers" permission. |
| `CREDITS_EXHAUSTED` | 402 | no | Monthly Hugging Face inference credits are used up. Upgrade, wait for reset, or point `HF_BASE_URL` at another provider. |
| `RATE_LIMITED` | 429 | yes | Too many requests (local limiter or upstream). Show `Retry-After`. |
| `IMAGE_INVALID` | 400/415 | no | Not a valid PNG/JPG/WebP, or too small. |
| `IMAGE_TOO_LARGE` | 413 | no | Over the size/pixel limit. |
| `MODEL_UNAVAILABLE` | 503 | yes | Configured model/provider not available; list tried models. Suggest `scripts/list_models.py`. |
| `UPSTREAM_TIMEOUT` | 504 | yes | Model took too long. Try a smaller model or screenshot. |
| `UPSTREAM_ERROR` | 502 | yes | Provider error (sanitized message). |
| `OUTPUT_NOT_HTML` | 502 | yes | Model did not return an HTML document. |
| `OUTPUT_TRUNCATED` | — | — | **Warning only** (not an error): page repaired and may be incomplete. |
| `INTERNAL` | 500 | no | Unexpected error; request id shown. |

## 10. Scripts

**`scripts/list_models.py`** — `GET {HF_BASE_URL}/models` with the bearer token; print model IDs (and providers if present in the response); filter case-insensitively on `qwen` and `vl`; mark the currently configured `HF_MODEL_ID` as ✓ present / ✗ missing. Exit non-zero if the configured model is missing. This is the **first thing to run** (M0). If the endpoint's response shape differs from expectation, print the raw JSON keys and degrade gracefully.

**`scripts/smoke_test.py <image> [--instructions ...] [--out out.html]`** — `POST /api/generate` with `stream=false` against `http://127.0.0.1:{APP_PORT}`, write the HTML, print model, elapsed, tokens, warnings.

## 11. Testing

Unit (no network; mock the OpenAI client with a fake async stream):
- `image_prep`: RGBA→white composite; EXIF rotate; oversize downscale; tall warning; corrupt bytes → `IMAGE_INVALID`; payload cap loop terminates; GIF animated → first frame + warning.
- `palette`: solid-color image → that color first; deterministic ordering.
- `prompts`: placeholders all filled; instructions truncated/sanitized; message structure has exactly one `image_url`.
- `html_cleaner`: fenced; unfenced; unterminated fence; with `<think>`; truncated mid-tag; no HTML → `OUTPUT_NOT_HTML`; missing doctype/meta get injected.
- `sanitize`: hostile fixture containing CDN script, Google Fonts `<link>`, `@import`, `url(http…)`, remote `<img>`, `<iframe>`, `fetch()` script, `onclick="fetch(...)"`, `javascript:` href, meta refresh → assert none survive and the report counts are right.
- `client`: success path; 429 then success; 404 → fallback model; 401 → `AUTH_FAILED` with no fallback; 402 → `CREDITS_EXHAUSTED`; error after first delta → no retry.
- `api` (FastAPI `TestClient`, monkeypatched client): happy path SSE ordering (`status…delta…result`); `stream=false`; missing token; access key; rate limit; oversize upload; token never appears in any response body.

Manual checklist (M2/M3), on the 15-image set (PRD §9): record per image — valid HTML? text recall? external requests (open DevTools Network on the preview)? time? cost estimate? Save results in `docs/RESULTS.md` and quote them honestly in the README.

## 12. P1 / P2 specifications

### P1 — Compare tab (F20)
Original and preview stacked in one container; range input sets the preview layer's opacity 0–100%; same sandbox rules; both scaled to the original's aspect ratio.

### P1 — Self-refine loop (F21), `src/refine/`
Enabled by `ENABLE_REFINE_LOOP=true`; requires `requirements-refine.txt` + `playwright install chromium`.
1. `render.py`: Playwright Chromium, viewport = prepared image width × height, `javascript_enabled=True`, **route-block all network** (`page.route("**/*", abort)` except `data:`), `set_content(html)`, wait for `load` + 300 ms, full-page screenshot → PIL. Count blocked requests (should be 0).
2. `similarity.py`: resize the render to the original's size; compute SSIM on grayscale (`skimage.metrics.structural_similarity`); return `score` ∈ [0,1].
3. `loop.py`: if `score < 0.9` and iterations < `REFINE_MAX_ITERATIONS`: send **three** inputs — original screenshot, current render, current HTML — with `prompts/refine.md` ("Image 1 is the target, image 2 is your current render. List the most visible differences (layout, spacing, colors, missing elements, text), then output the full corrected HTML in one ```html fence. Do not remove content to simplify."). Keep the best-scoring version; stop if the score does not improve by ≥ 0.01. Always run the sanitizer on each iteration's output.
4. SSE adds `event: refine` `{iteration, score, kept: bool}`; `result` gains `"similarity": {"initial": 0.52, "final": 0.64, "iterations": 2}`.
5. Cost warning in UI/README: each iteration roughly doubles the prompt (two images + HTML) and repeats a full output. Do not enable on a free-tier account.

### P2 — Eval harness (F30)
`scripts/eval.py --dir tests/eval_images --out docs/RESULTS.md`: for each image call the pipeline in-process, render with Playwright, record: valid-HTML flag, SSIM, blocked-request count, visible-text token recall (tokens from DOM `innerText` vs. a manually supplied `<image>.txt` ground-truth file), latency, token usage. Output a Markdown table plus median/p90.

## 13. Definition of Done (v1.0)

- [ ] M0 completed and the chosen model recorded in `.env.example` comments.
- [ ] `pip install -r requirements.txt` works on a clean venv; no torch/transformers/gradio installed.
- [ ] `.env` is loaded (verified by a test that sets a value only in a temp `.env`).
- [ ] `uvicorn app.api:app --host 127.0.0.1 --port 8000` serves the UI at `/` and `GET /health` returns OK without calling HF.
- [ ] Upload (pick/drag/paste) → streamed progress → Preview/Code/Download all work in Chrome and Firefox.
- [ ] Every output opens with **0 external requests** (sanitizer tests green; manual Network-tab check on ≥ 5 outputs).
- [ ] All error codes in §9 are reachable and render distinct messages (simulate via mocked client).
- [ ] Token never appears in any response, log line, or error (test + manual grep of logs).
- [ ] Rate limit and access key work.
- [ ] All unit tests pass; `pytest -q` is green.
- [ ] 15-image set run once; results in `docs/RESULTS.md`; README quotes them and lists real limitations.
- [ ] No `__pycache__`, `.env`, or uploads in git.

## 14. Dev commands

PowerShell (Windows):
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env        # then edit HF_TOKEN
python scripts\list_models.py      # M0: confirm the model is live
uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
pytest -q
python scripts\smoke_test.py path\to\screenshot.png --out out.html
```
bash:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python scripts/list_models.py
uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
```

`.gitignore` (minimum):
```
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
out*.html
```

## 15. Known limitations to publish in the README

- Output is a first draft. Expect wrong spacing, approximated fonts, placeholder images, and occasional missing sections.
- Quality depends heavily on the model; small models (≈ 8B and under) will struggle on dense pages.
- Free Hugging Face accounts have very small monthly inference credits; plan for a paid tier or another OpenAI-compatible provider.
- Very tall pages lose fidelity toward the bottom.
- Generated JavaScript is sandboxed and filtered, but treat every output as untrusted until you read it.