# VisionCraft — Product Requirements Document

**Version:** 1.0  **Status:** Ready to build  **Companion doc:** `SPEC.md` (implementation contract)

---

## 1. One-line summary

Upload a UI screenshot → a Hugging Face–hosted Qwen vision-language model (VLM) reads it → the app returns **one standalone `.html` file** (HTML + CSS + JS inline, zero external dependencies) that you can preview, copy, and download.

## 2. Problem

Turning a design/screenshot into working front-end code is slow, repetitive grunt work. Existing tools (v0, Locofy, Claude/GPT chat) are closed, paid, or give React/framework output that needs a build step. A developer who just wants a **single openable file** to start from has no lightweight, self-hostable option that uses open-weight models.

## 3. Goals

| # | Goal | Measure |
|---|------|---------|
| G1 | Screenshot in, single self-contained `.html` out, in one click | End-to-end works on ≥ 90% of the test set (§9) |
| G2 | Output opens offline with **zero network requests** | 0 external requests on 100% of outputs (enforced by sanitizer) |
| G3 | Usable feedback during a 30–120 s generation | Streaming progress visible within 3 s of submit |
| G4 | Safe to run on the developer's machine | Generated code never runs with access to the app's origin or the HF token |
| G5 | Swap models/providers by editing `.env` only | No code change to change `HF_MODEL_ID` or `HF_BASE_URL` |

## 4. Non-goals (explicitly out of scope for v1)

- Pixel-perfect reproduction. Not achievable with a single VLM pass. Do not promise it anywhere in the UI or README.
- React / Vue / Tailwind / framework output. Single vanilla HTML file only.
- Multi-page sites, routing, backend generation, auth flows, databases.
- Figma/URL import, image-asset extraction or recreation (photos become placeholders).
- Bounding-box grounding overlays, dataset loaders, QLoRA fine-tuning, local model inference, Gradio UI. **All of this exists in the current repo and gets deleted** (see SPEC §1).
- User accounts, billing, saved projects, a database.

## 5. Target user

A student/indie developer/designer running the app **locally** with their own Hugging Face token, who wants a fast first draft of a page from a screenshot and is willing to hand-edit the result.

## 6. User stories

1. As a user, I drag-drop, paste (Ctrl+V), or pick a screenshot (PNG/JPG/WebP).
2. As a user, I optionally add instructions ("make it dark mode", "keep only the hero section").
3. As a user, I click **Generate** and see live progress (elapsed time, tokens streamed), not a frozen spinner.
4. As a user, I see the result rendered in a **sandboxed preview** next to my original screenshot.
5. As a user, I switch the preview between desktop / tablet / mobile widths.
6. As a user, I view, **copy**, and **download** the single `.html` file.
7. As a user, I re-generate with tweaked instructions without re-uploading.
8. As a user, when something fails (bad token, no credits, rate limit, truncated output), I get a **specific, actionable** message — not "Something went wrong".

## 7. Functional requirements

### P0 — must ship (v1.0)

| ID | Requirement |
|----|-------------|
| F1 | Upload via file picker, drag-drop, and clipboard paste. PNG/JPG/WebP only, ≤ `MAX_UPLOAD_MB` (default 10). |
| F2 | Server-side image validation, EXIF-rotate, alpha flatten, downscale to `IMAGE_MAX_SIDE` (default 1600), re-encode under a payload cap. |
| F3 | Extract a dominant-color palette server-side and pass it to the model as hints (cheap fidelity win). |
| F4 | Call a Qwen VLM through the HF Inference Providers OpenAI-compatible endpoint with streaming. |
| F5 | Stream progress to the browser via SSE (`status`, `delta`, `result`, `error` events). |
| F6 | Post-process: extract the HTML from the model reply, strip `<think>` blocks, repair truncation, inject missing `<meta charset>`/viewport. |
| F7 | **Standalone sanitizer:** remove/neutralize every external resource (scripts, stylesheets, fonts, remote images, iframes, `@import`, network JS APIs). |
| F8 | Sandboxed preview (`iframe sandbox="allow-scripts"`, no `allow-same-origin`, injected restrictive CSP). |
| F9 | Code tab with Copy; Download button (`visioncraft-<timestamp>.html`). |
| F10 | Responsive preview toggle: Fit / 768 px / 390 px. |
| F11 | Typed error codes surfaced as clear UI messages (SPEC §9). |
| F12 | Config entirely via `.env`; **`.env` is actually loaded** (the current repo does not do this — it is a known bug). |
| F13 | Fallback model chain (`HF_FALLBACK_MODEL_IDS`) when the primary model/provider is unavailable. |
| F14 | In-memory per-IP rate limit and optional `APP_ACCESS_KEY` so a deployed instance can't burn the owner's credits. |
| F15 | `scripts/list_models.py` — lists models actually served by the router so the user picks one that is live today. |

### P1 — should ship next

| ID | Requirement |
|----|-------------|
| F20 | **Compare tab:** original vs. generated with an opacity-slider overlay. |
| F21 | **Self-refine loop:** render output in headless Chromium, screenshot it, diff against the original (SSIM), send both images + current HTML back to the VLM for a correction pass; max `REFINE_MAX_ITERATIONS` (default 2); show the similarity score. |
| F22 | In-memory history of the last 5 generations in the session. |

### P2 — only if time remains

| ID | Requirement |
|----|-------------|
| F30 | `scripts/eval.py`: run the 15-image test set, compute SSIM + text-recall + external-request count, write a CSV/Markdown report. |
| F31 | Tall-screenshot slicing (> 4:1) with stitch prompt. |

## 8. UX flow

```
[Drop / paste / pick screenshot]  → thumbnail + dimensions shown
        │  (optional) instructions textarea
        ▼
   [Generate]  → status: Preparing → Calling model → Generating (timer + token count) → Post-processing
        │
        ▼
 ┌─────────────────────────────┬──────────────────────────────┐
 │ Original screenshot         │ Tabs: Preview | Code | Compare│
 │                             │ Device: Fit | 768 | 390       │
 │                             │ [Copy] [Download] [Regenerate]│
 └─────────────────────────────┴──────────────────────────────┘
   Warnings banner (truncated, sanitized N items, tall image, fallback model used)
```

States: empty, image-ready, generating, success, error (with retry), cancelled (user can abort the in-flight request).

## 9. Success metrics & test set

**Test set (build before claiming anything works):** 15 screenshots — 3 landing pages, 2 dashboards, 2 login/signup, 2 pricing, 2 blog/article, 2 mobile app screens, 2 e-commerce product pages.

| Metric | Initial target* |
|--------|-----------------|
| Valid, openable single-file HTML | ≥ 90% (14/15) |
| External network requests in output | 0 (100%) |
| Visible-text recall (manual spot check, 5 images) | ≥ 85% |
| SSIM vs. original at original width (simple pages) | median ≥ 0.55 |
| p50 time to first streamed token | < 8 s |
| p50 total generation time | < 60 s (small model) / < 150 s (large model) |

\*These are starting guesses. Run the set once, then **re-baseline** the targets from real data. Do not leave invented numbers in the final README.

## 10. Constraints, risks, and honest limitations

| Risk | Reality | Mitigation |
|------|---------|-----------|
| **Model quality** | A 3B VLM (the current repo default) produces weak, often broken full-page HTML. Quality scales hard with model size. | Default to the largest Qwen-VL actually served; Milestone 0 tests this *before* any code. |
| **HF free tier is tiny** | Hugging Face Inference Providers gives free accounts about **$0.10/month** in credits and stops at the limit; PRO ($9/mo) gets $2 and pay-as-you-go. A large VLM call with an image plus ~6–8k output tokens can eat a meaningful fraction of that. | Plan on PRO or another OpenAI-compatible provider (just change `HF_BASE_URL`). Surface `CREDITS_EXHAUSTED` clearly. Keep image/output caps. |
| **Model/provider availability changes** | Which VLMs are live on which provider shifts without notice. | `list_models.py`, fallback chain, configurable IDs. Never hardcode a model in code. |
| **Output truncation** | The current repo's `max_new_tokens: 900` will cut every full page mid-tag. A full page needs ~4–8k+ tokens. | `MAX_OUTPUT_TOKENS` default 8192; detect `finish_reason=length`; repair + warn. |
| **Untrusted generated code** | The model emits HTML+JS. Prompt injection via text in the screenshot is possible. | Sandboxed iframe, CSP, sanitizer, no "open in new tab" via Blob URL (SPEC §8). |
| **Images/fonts/icons can't be recovered** | VLM cannot reproduce photos or brand fonts. | Placeholders, system font stacks, inline SVG icons. Set expectations in UI copy. |
| **Latency** | Large VLMs are slow; non-streaming UX feels broken. | SSE streaming is P0, not optional. |
| **Commodity risk** | "Screenshot → code" is a crowded space; a thin API wrapper is not differentiated. | The differentiator is P1: the self-refine loop + measured evals. Ship P0 fast, then invest there. |

## 11. Milestones (solo dev + AI coding agent; estimates, not promises)

| M | Deliverable | Est. |
|---|-------------|------|
| **M0** | **Reality check, no app code:** run `list_models.py`, then 5 screenshots by hand through the model with the SPEC §5.3 prompt (curl/Python). Pick the model. If output is unusable on 4/5, stop and change model/provider before building anything. | 0.5 day |
| **M1** | Backend P0: settings, image prep, palette, client (stream + retries + fallback), cleaner, sanitizer, `/api/generate`, tests. | 1–2 days |
| **M2** | Frontend P0: upload/paste, SSE progress, preview/code tabs, device toggle, copy/download, errors. | 1–2 days |
| **M3** | Hardening: rate limit, access key, security checklist, README with real limitations, run the 15-image set once. | 1 day |
| **M4** | P1: Compare overlay, self-refine loop, history. | 3–4 days |
| **M5** | P2: eval harness + results table in README. | 1–2 days |

## 12. Definition of done (v1.0)

See `SPEC.md` §13. In short: all P0 requirements pass their tests, the 15-image set has been run once with results recorded honestly, `.env` loads, no secret is ever sent to the browser, and the README states real limitations.