# VisionCraft — Test-set results (PRD §9)

## Test set (15 screenshots, synthetic but realistic)

Generated from the HTML sources in `tests/eval_images/*.html`
(text ground truth in the sibling `*.txt` files) via headless Edge.

| # | File | Category | Size | Ground-truth text |
|---|------|----------|------|-------------------|
| 1 | `01_landing.png` | landing | 1440×900 | `01_landing.txt` |
| 2 | `02_dashboard.png` | dashboard | 1440×900 | `02_dashboard.txt` |
| 3 | `03_login.png` | login | 1440×900 | `03_login.txt` |
| 4 | `04_pricing.png` | pricing | 1440×1000 | `04_pricing.txt` |
| 5 | `05_blog.png` | blog/article | 1440×1000 | `05_blog.txt` |
| 6 | `06_landing_dark.png` | landing (dark) | 1440×900 | `06_landing_dark.txt` |
| 7 | `07_landing_features.png` | landing (features) | 1440×1050 | `07_landing_features.txt` |
| 8 | `08_dashboard_dark.png` | dashboard (dark) | 1440×900 | `08_dashboard_dark.txt` |
| 9 | `09_signup.png` | signup | 1440×900 | `09_signup.txt` |
| 10 | `10_pricing_simple.png` | pricing (2-tier) | 1440×900 | `10_pricing_simple.txt` |
| 11 | `11_blog_list.png` | blog (index) | 1440×1000 | `11_blog_list.txt` |
| 12 | `12_mobile_chat.png` | mobile app | 390×844 | `12_mobile_chat.txt` |
| 13 | `13_mobile_fitness.png` | mobile app | 390×844 | `13_mobile_fitness.txt` |
| 14 | `14_ecommerce_product.png` | e-commerce | 1440×1000 | `14_ecommerce_product.txt` |
| 15 | `15_ecommerce_cart.png` | e-commerce | 1440×900 | `15_ecommerce_cart.txt` |

Distribution matches PRD §9: 3 landing, 2 dashboards, 2 login/signup,
2 pricing, 2 blog/article, 2 mobile, 2 e-commerce.

## M0 model check (2026-10-01, no app code)

`python scripts/list_models.py` against `https://router.huggingface.co/v1/models`:

- Router reachable, 134 models listed.
- **`Qwen/Qwen3-VL-8B-Instruct` does not exist** (it was a guess in early drafts).
  Live Qwen VL instruct models: `Qwen3-VL-235B-A22B-Instruct`,
  `Qwen2.5-VL-72B-Instruct`, `Qwen3-VL-30B-A3B-Instruct`.
- Default chosen: `Qwen/Qwen3-VL-235B-A22B-Instruct` (largest Qwen VL served),
  fallbacks `Qwen2.5-VL-72B-Instruct`, `Qwen3-VL-30B-A3B-Instruct`
  (see `.env.example` comments).
- **Blocked:** the configured `HF_TOKEN` lists models (HTTP 200) but every
  `POST /v1/chat/completions` returns
  `401 {"error":"Invalid username or password."}` across 4 models and 2 HTTP
  clients. The token needs the “Make calls to Inference Providers” permission
  and/or inference credits. Real generation runs are pending a working token.

## Generation results (pending — fill in after the token is fixed)

How to run (server must be up with a working `HF_TOKEN`):

```powershell
uvicorn app.api:app --host 127.0.0.1 --port 8000
foreach ($i in Get-ChildItem tests\eval_images\*.png) {
  python scripts\smoke_test.py $i.FullName --out "out-$($i.BaseName).html"
}
```

For each image record: valid single-file HTML? / visible-text recall vs the
`.txt` ground truth / external requests (DevTools Network on the preview, must
be 0) / TTFT + total time / token usage / warnings.

| Image | Valid HTML | Text recall | Ext. reqs | TTFT | Total | Tokens | Notes |
|-------|-----------|-------------|-----------|------|-------|--------|-------|
| 01_landing | — | — | — | — | — | — | |
| 02_dashboard | — | — | — | — | — | — | |
| 03_login | — | — | — | — | — | — | |
| 04_pricing | — | — | — | — | — | — | |
| 05_blog | — | — | — | — | — | — | |
| 06_landing_dark | — | — | — | — | — | — | |
| 07_landing_features | — | — | — | — | — | — | |
| 08_dashboard_dark | — | — | — | — | — | — | |
| 09_signup | — | — | — | — | — | — | |
| 10_pricing_simple | — | — | — | — | — | — | |
| 11_blog_list | — | — | — | — | — | — | |
| 12_mobile_chat | — | — | — | — | — | — | |
| 13_mobile_fitness | — | — | — | — | — | — | |
| 14_ecommerce_product | — | — | — | — | — | — | |
| 15_ecommerce_cart | — | — | — | — | — | — | |

Targets (initial guesses from PRD §9 — re-baseline from real data):
valid HTML ≥ 90% · external requests 0 · text recall ≥ 85% (5-image spot check) ·
SSIM median ≥ 0.55 (simple pages) · p50 TTFT < 8 s.
