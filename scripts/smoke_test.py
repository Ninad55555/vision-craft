"""Smoke test: POST an image to a running server (stream=false), save the HTML.

Usage:
    python scripts/smoke_test.py path\\to\\screenshot.png [--instructions "..."] [--out out.html]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def encode_multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    boundary = "visioncraft-smoke-boundary"
    body = b""
    for name, value in fields.items():
        body += (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n"
        ).encode()
    for name, (filename, content, content_type) in files.items():
        body += (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="screenshot to convert")
    parser.add_argument("--instructions", default="")
    parser.add_argument("--out", default="out.html")
    parser.add_argument("--access-key", default="")
    args = parser.parse_args()

    load_env(ROOT / ".env")
    port = os.environ.get("APP_PORT", "8000")
    url = f"http://127.0.0.1:{port}/api/generate"

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"ERROR: {image_path} not found", file=sys.stderr)
        return 2

    body, content_type = encode_multipart(
        {"instructions": args.instructions, "stream": "false"},
        {"image": (image_path.name, image_path.read_bytes(), "image/png")},
    )
    headers = {"Content-Type": content_type}
    if args.access_key or os.environ.get("APP_ACCESS_KEY"):
        headers["X-Access-Key"] = args.access_key or os.environ["APP_ACCESS_KEY"]

    t0 = time.time()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            status = resp.status
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:1000]}", file=sys.stderr)
        return 1
    elapsed = time.time() - t0

    Path(args.out).write_text(payload["html"], encoding="utf-8")
    print(f"HTTP {status} in {elapsed:.1f}s -> {args.out} ({len(payload['html'])} bytes)")
    print(f"model={payload.get('model')} finish={payload.get('finish_reason')} "
          f"truncated={payload.get('truncated')}")
    print(f"usage={payload.get('usage')} warnings={payload.get('warnings')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
