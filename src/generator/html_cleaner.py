from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.core.errors import error

THINK_FENCE = re.compile(r"```(?:think|thinking)\b.*?```", re.DOTALL | re.IGNORECASE)
THINK_FENCE_UNTERMINATED = re.compile(r"```(?:think|thinking)\b.*", re.DOTALL | re.IGNORECASE)
THINK_TAG = re.compile(r"<(?:think|thinking)>.*?</(?:think|thinking)>", re.DOTALL | re.IGNORECASE)
THINK_TAG_UNTERMINATED = re.compile(r"<(?:think|thinking)>.*", re.DOTALL | re.IGNORECASE)
FENCE_HTML = re.compile(r"```html\s*(.*?)```", re.DOTALL | re.IGNORECASE)
FENCE_ANY = re.compile(r"```\s*(.*?)```", re.DOTALL)
DOCTYPES = re.compile(r"<!doctype\s+html[^>]*>", re.IGNORECASE)

MAX_HTML_BYTES = 1_000_000


def clean_model_output(text: str, *, finish_reason: str | None) -> tuple[str, list[str]]:
    warnings: list[str] = []
    working = THINK_FENCE.sub("", text or "")
    working = THINK_TAG.sub("", working)
    if re.search(r"```(?:think|thinking)\b", working, re.IGNORECASE):
        working = THINK_FENCE_UNTERMINATED.sub("", working)
    if re.search(r"<(?:think|thinking)>", working, re.IGNORECASE):
        working = THINK_TAG_UNTERMINATED.sub("", working)

    html = _extract(working)

    truncated = finish_reason == "length" or "</html>" not in html.lower()
    if truncated:
        html = _repair(html)
        warnings.append("OUTPUT_TRUNCATED: The model hit its output limit; the page may be incomplete.")

    html = _ensure_document(html)

    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        html = _truncate_bytes(html, MAX_HTML_BYTES)
        warnings.append("OUTPUT_TRUNCATED: Output exceeded 1 MB and was truncated.")

    if _looks_empty(html):
        raise error("OUTPUT_NOT_HTML", "The model did not return a usable HTML document.")

    return html, warnings


def _extract(text: str) -> str:
    fences = FENCE_HTML.findall(text)
    if not fences:
        fences = [b for b in FENCE_ANY.findall(text) if "<html" in b.lower() or "<!doctype" in b.lower()]
    if fences:
        return max(fences, key=len).strip()

    low = text.lower()
    start = low.find("<!doctype")
    if start < 0:
        start = low.find("<html")
    if start >= 0:
        end = low.rfind("</html>")
        return text[start : end + 7] if end >= 0 else text[start:].strip()

    if text.lstrip().startswith("<"):
        return text.strip()

    raise error("OUTPUT_NOT_HTML", "The model did not return an HTML document.")


def _repair(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return html
    if soup.html is None:
        # lxml may have dropped a partial root; fall back to manual completion
        out = html
        if "<body" not in out.lower():
            out += "</body></html>"
        return out
    out = str(soup)
    low = out.lower()
    if "</body>" not in low:
        out += "</body>"
    if "</html>" not in low:
        out += "</html>"
    return out


def _ensure_document(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return html

    if not DOCTYPES.search(html):
        html = "<!DOCTYPE html>\n" + html.lstrip()
        soup = BeautifulSoup(html, "lxml")

    head = soup.head
    if head is None:
        head = soup.new_tag("head")
        if soup.html is not None:
            soup.html.insert(0, head)
        else:
            return html

    if head.find("meta", attrs={"charset": True}) is None and not re.search(r"<meta[^>]+charset", str(head), re.I):
        meta = soup.new_tag("meta", charset="utf-8")
        head.insert(0, meta)

    has_viewport = head.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)}) is not None
    if not has_viewport:
        meta = soup.new_tag("meta")
        meta["name"] = "viewport"
        meta["content"] = "width=device-width, initial-scale=1"
        head.append(meta)

    doctype = DOCTYPES.search(str(soup))
    prefix = doctype.group(0) if doctype else "<!DOCTYPE html>"
    body = str(soup)
    if doctype:
        # BeautifulSoup keeps the doctype in output; avoid duplicating it
        return body
    return f"{prefix}\n{body}"


def _truncate_bytes(html: str, cap: int) -> str:
    raw = html.encode("utf-8")
    clipped = raw[:cap].decode("utf-8", errors="ignore")
    clipped = _repair(clipped)
    if "</html>" not in clipped.lower():
        clipped += "</body></html>"
    return clipped


def _looks_empty(html: str) -> bool:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return True
    body = soup.body
    if body is None:
        return True
    if body.get_text(strip=True):
        return False
    return len(body.find_all(True)) == 0
