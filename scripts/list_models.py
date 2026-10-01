"""List models served by the OpenAI-compatible router (M0 reality check).

Usage:
    python scripts/list_models.py            # list all, highlight qwen/vl
    python scripts/list_models.py --all      # do not filter
    python scripts/list_models.py --json     # dump raw JSON keys/shape

Exit code is non-zero if the configured HF_MODEL_ID is not present.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE); real env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def flatten_models(payload) -> list[str]:
    """Extract model ids from whatever shape the endpoint returned."""
    ids: list[str] = []
    if isinstance(payload, dict):
        candidates = []
        for key in ("data", "models", "items", "results"):
            if isinstance(payload.get(key), list):
                candidates = payload[key]
                break
        if not candidates:
            # dict-of-dicts fallback: {"model-id": {...}, ...}
            candidates = [{"id": k} if isinstance(v, dict) else {"id": k} for k, v in payload.items()]
        for item in candidates:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict):
                mid = item.get("id") or item.get("model") or item.get("name")
                if mid:
                    ids.append(str(mid))
    elif isinstance(payload, list):
        return flatten_models({"data": payload})
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="show every model, not just qwen/vl matches")
    parser.add_argument("--json", action="store_true", help="print raw response keys instead of a table")
    args = parser.parse_args()

    load_env_file(ROOT / ".env")

    base_url = os.environ.get("HF_BASE_URL", "https://router.huggingface.co/v1").rstrip("/")
    token = os.environ.get("HF_TOKEN", "")
    configured = os.environ.get("HF_MODEL_ID", "")

    if not token:
        print("ERROR: HF_TOKEN is empty. Set it in .env first.", file=sys.stderr)
        return 2

    url = f"{base_url}/models"
    print(f"GET {url}")
    req = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        print(f"ERROR: HTTP {exc.code} from {url}\n{body}", file=sys.stderr)
        if exc.code in (401, 403):
            print("Hint: token needs the 'Make calls to Inference Providers' permission.", file=sys.stderr)
        return 2
    except URLError as exc:
        print(f"ERROR: cannot reach {url}: {exc.reason}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print(f"ERROR: non-JSON response (HTTP {status}). First 500 chars:\n{raw[:500]}", file=sys.stderr)
        return 2

    if args.json:
        if isinstance(payload, dict):
            print("Top-level keys:", list(payload.keys()))
            for key, value in payload.items():
                if isinstance(value, list) and value:
                    print(f"'{key}[0]' keys:", list(value[0].keys()) if isinstance(value[0], dict) else type(value[0]).__name__)
            print(json.dumps(payload, indent=2)[:4000])
        else:
            print(json.dumps(payload, indent=2)[:4000])
        return 0

    model_ids = flatten_models(payload)
    if not model_ids:
        print(f"WARNING: could not find a model list in the response.", file=sys.stderr)
        keys = list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
        print("Top-level keys:", keys, file=sys.stderr)
        print(json.dumps(payload, indent=2)[:2000], file=sys.stderr)
        return 2

    model_ids = sorted(set(model_ids), key=str.lower)
    matches = [m for m in model_ids if "qwen" in m.lower() or "vl" in m.lower()]
    shown = model_ids if args.all or not matches else matches

    print(f"{len(model_ids)} models total; {len(matches)} match 'qwen' or 'vl'. Showing {len(shown)}:\n")
    configured_found = False
    for mid in shown:
        mark = ""
        if configured and mid.lower() == configured.lower():
            mark = "  <-- CONFIGURED HF_MODEL_ID"
            configured_found = True
        print(f"  {mid}{mark}")

    # The configured id may carry a provider suffix or be filtered out above.
    if configured and not configured_found:
        configured_found = any(m.lower() == configured.lower() for m in model_ids)
        if configured_found:
            print(f"\n{configured} <-- CONFIGURED HF_MODEL_ID (present, not in filtered list)")
        else:
            print(f"\nMISSING: configured HF_MODEL_ID '{configured}' was NOT found.", file=sys.stderr)
            print("Pick one from the list above and update .env, or run with --all.", file=sys.stderr)
            return 1

    print("\nOK: configured model is present." if configured else "\n(No HF_MODEL_ID configured.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
