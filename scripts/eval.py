"""Run the 15-image set through generation and optional one-pass refinement.

Usage:
    python scripts/eval.py                 # generate + refine
    python scripts/eval.py --no-refine     # generation only
    python scripts/eval.py --limit 3       # quick smoke

Requires a running server and a working provider. The script writes
docs/refine_results.json and prints a markdown table.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGES = ROOT / "tests" / "eval_images"
DEFAULT_JSON = ROOT / "docs" / "refine_results.json"
WORD = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)
BLOCKED = re.compile(r"Blocked\s+(\d+)\s+external request", re.IGNORECASE)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def visible_text(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return ""
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def text_tokens(text: str) -> set[str]:
    return {word.lower() for word in WORD.findall(text)}


def text_recall(html: str, ground_truth: str) -> float | None:
    expected = text_tokens(ground_truth)
    if not expected:
        return None
    actual = text_tokens(visible_text(html))
    return round(len(expected & actual) / len(expected), 3)


def valid_html(html: str) -> bool:
    low = html.lower()
    if "<html" not in low or "</html>" not in low:
        return False
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return False
    return soup.body is not None and bool(visible_text(html))


def blocked_requests(payload: dict) -> int:
    counts = [int(m.group(1)) for m in (BLOCKED.search(w) for w in payload.get("warnings", [])) if m]
    return sum(counts)


def error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        detail = body.get("detail")
        if isinstance(detail, dict):
            return f"{detail.get('code', 'ERROR')}: {detail.get('message', '')}"[:300]
        return str(detail)[:300]
    except Exception:
        return response.text[:300]


def post_generate(client: httpx.Client, base_url: str, image: Path, instructions: str, headers: dict) -> dict:
    with image.open("rb") as handle:
        response = client.post(
            f"{base_url}/api/generate",
            files={"image": (image.name, handle, "image/png")},
            data={"instructions": instructions, "stream": "false"},
            headers=headers,
        )
    if response.status_code != 200:
        raise RuntimeError(f"generate HTTP {response.status_code}: {error_detail(response)}")
    return response.json()


def post_refine(client: httpx.Client, base_url: str, image: Path, html: str, instructions: str, headers: dict) -> dict:
    with image.open("rb") as handle:
        response = client.post(
            f"{base_url}/api/refine",
            files={"image": (image.name, handle, "image/png")},
            data={"html": html, "instructions": instructions, "stream": "false"},
            headers=headers,
        )
    if response.status_code != 200:
        raise RuntimeError(f"refine HTTP {response.status_code}: {error_detail(response)}")
    return response.json()


def markdown(rows: list[dict]) -> str:
    lines = [
        "| Image | Valid HTML | Text recall | Initial SSIM | Final SSIM | Kept | Meaningful | Blocked reqs | Refine ms | Tokens | Notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {image} | {valid} | {recall} | {initial} | {final} | {kept} | {meaningful} | {blocked} | {elapsed} | {tokens} | {notes} |".format(
                image=row["image"],
                valid="yes" if row["valid_html"] else "no",
                recall=row["text_recall"] if row["text_recall"] is not None else "-",
                initial=row.get("initial", "-"),
                final=row.get("final", "-"),
                kept=row.get("kept", "-"),
                meaningful=row.get("meaningful", "-"),
                blocked=row.get("blocked", "-"),
                elapsed=row.get("elapsed_ms", "-"),
                tokens=row.get("tokens", "-"),
                notes=(row.get("error") or "").replace("|", "/")[:80] or "",
            )
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--images-dir", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--instructions", default="")
    parser.add_argument("--access-key", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=0.0, help="Seconds between images (raise for rate limits).")
    parser.add_argument("--refine", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    load_env(ROOT / ".env")
    images = sorted(args.images_dir.glob("*.png"))
    if args.limit:
        images = images[: args.limit]
    if not images:
        print(f"No PNGs found in {args.images_dir}", file=sys.stderr)
        return 2

    key = args.access_key or os.environ.get("APP_ACCESS_KEY", "")
    headers = {"X-Access-Key": key} if key else {}
    rows: list[dict] = []

    with httpx.Client(timeout=args.timeout) as client:
        for index, image in enumerate(images, start=1):
            print(f"[{index}/{len(images)}] {image.name}", file=sys.stderr)
            row: dict = {"image": image.name, "valid_html": False, "text_recall": None}
            try:
                generated = post_generate(client, args.base_url, image, args.instructions, headers)
                html = generated["html"]
                gt_path = image.with_suffix(".txt")
                gt = gt_path.read_text(encoding="utf-8", errors="replace") if gt_path.exists() else ""
                row["valid_html"] = valid_html(html)
                row["text_recall"] = text_recall(html, gt)
                row["generate_ms"] = generated.get("elapsed_ms")
                row["generate_usage"] = generated.get("usage")

                if args.refine:
                    refined = post_refine(client, args.base_url, image, html, args.instructions, headers)
                    similarity = refined["similarity"]
                    usage = refined.get("usage") or {}
                    row.update(
                        {
                            "valid_html": valid_html(refined["html"]),
                            "text_recall": text_recall(refined["html"], gt),
                            "initial": similarity["initial"],
                            "candidate": similarity["candidate"],
                            "final": similarity["final"],
                            "kept": similarity["kept"],
                            "meaningful": similarity["meaningful"],
                            "target": similarity["target"],
                            "improvement": similarity["improvement"],
                            "blocked": blocked_requests(refined),
                            "elapsed_ms": refined.get("elapsed_ms"),
                            "tokens": (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0),
                            "warnings": refined.get("warnings", []),
                        }
                    )
            except Exception as exc:  # noqa: BLE001 - batch evaluation continues
                row["error"] = str(exc)

            rows.append(row)
            if args.delay and index < len(images):
                time.sleep(args.delay)

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(markdown(rows))
    print(f"\nWrote {args.out_json}")
    return 0 if not any(row.get("error") for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
