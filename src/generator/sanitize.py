from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

DOCTYPES = re.compile(r"<!doctype\s+html[^>]*>", re.IGNORECASE)
LINK_RESOURCE_RELS = {
    "stylesheet", "preload", "prefetch", "preconnect", "dns-prefetch", "icon", "modulepreload",
}
BLOCKED_JS_PATTERNS = [
    "fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon",
    "importScripts", "eval(", "new Function", "document.cookie",
    "localStorage", "sessionStorage", "indexedDB", "window.open",
    "location.href=", "location.assign(", "location.replace(",
]
IMPORT_RE = re.compile(r"""@import\s+(?:url\([^)]*\)|"[^"]*"|'[^']*'|[^;]+);?""", re.IGNORECASE)
URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
FONT_FACE_RE = re.compile(r"@font-face\s*\{[^}]*\}", re.IGNORECASE | re.DOTALL)


@dataclass
class SanitizeReport:
    removed_scripts: int = 0
    removed_links: int = 0
    neutralized_css_urls: int = 0
    replaced_images: int = 0
    removed_embeds: int = 0
    removed_js_blocks: int = 0
    notes: list[str] = field(default_factory=list)


def _is_external(url: str) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    low = url.lower()
    if low.startswith(("data:", "#", "blob:")) or low.startswith("mailto:") or low.startswith("tel:"):
        return False
    return True


def placeholder_data_uri(alt: str, width: int, height: int) -> str:
    w = width if width > 0 else 400
    h = height if height > 0 else 300
    label = (alt or "image").strip()[:60].replace("<", "").replace(">", "")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
        f'<rect width="100%" height="100%" fill="#cbd5e1"/>'
        f'<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
        f'font-family="sans-serif" font-size="16" fill="#475569">{label}</text></svg>'
    )
    return "data:image/svg+xml;utf8," + urllib.parse.quote(svg)


def _neutralize_css(css: str, report: SanitizeReport) -> str:
    def strip_font_face(text: str) -> str:
        def repl(m: "re.Match") -> str:
            block = m.group(0)
            inner = block[block.index("{") + 1 :]
            if URL_RE.search(inner) and any(_is_external(u) for _, u in URL_RE.findall(inner)):
                report.notes.append("Removed external @font-face rule.")
                return ""
            return block

        return FONT_FACE_RE.sub(repl, text)

    before = css
    css = strip_font_face(css)
    new_css, n_import = IMPORT_RE.subn("", css)
    if new_css != before or n_import:
        report.notes.append(f"Removed {n_import} @import rule(s).")

    def repl_url(m: "re.Match") -> str:
        url = m.group(2)
        if _is_external(url):
            report.neutralized_css_urls += 1
            return 'url("")'
        return m.group(0)

    return URL_RE.sub(repl_url, new_css)


def _dim(tag, attr: str) -> int:
    try:
        return max(0, int(str(tag.get(attr, "") or "").replace("px", "").strip() or 0))
    except (ValueError, TypeError):
        return 0


def make_standalone(html: str) -> tuple[str, SanitizeReport]:
    report = SanitizeReport()
    soup = BeautifulSoup(html, "lxml")

    for script in list(soup.find_all("script")):
        src = script.get("src", "")
        if src and _is_external(str(src)):
            script.decompose()
            report.removed_scripts += 1
            report.notes.append(f"Removed external script: {str(src)[:80]}")
            continue
        body = script.string or ""
        if body and any(p in body for p in BLOCKED_JS_PATTERNS):
            script.decompose()
            report.removed_js_blocks += 1
            report.notes.append("Removed inline script using network/storage/eval APIs.")

    for link in list(soup.find_all("link")):
        rels = {str(r).lower() for r in (link.get("rel") or [])}
        href = str(link.get("href", "") or "")
        if rels & LINK_RESOURCE_RELS and _is_external(href):
            link.decompose()
            report.removed_links += 1

    for img in list(soup.find_all(["img", "source"])):
        srcset = str(img.get("srcset", "") or "")
        if srcset:
            del img["srcset"]
        src = str(img.get("src", "") or "")
        if _is_external(src):
            img["src"] = placeholder_data_uri(str(img.get("alt", "") or ""), _dim(img, "width"), _dim(img, "height"))
            report.replaced_images += 1

    for video in soup.find_all("video"):
        poster = str(video.get("poster", "") or "")
        if _is_external(poster):
            video["poster"] = placeholder_data_uri("video", 0, 0)
            report.replaced_images += 1

    for tag in soup.find_all("input"):
        if str(tag.get("type", "")).lower() == "image":
            src = str(tag.get("src", "") or "")
            if _is_external(src):
                tag["src"] = placeholder_data_uri(str(tag.get("alt", "") or ""), 0, 0)
                report.replaced_images += 1

    for tag in list(soup.find_all(["iframe", "object", "embed", "base"])):
        tag.decompose()
        report.removed_embeds += 1
    for meta in list(soup.find_all("meta")):
        if str(meta.get("http-equiv", "")).lower() == "refresh":
            meta.decompose()
            report.removed_embeds += 1

    for form in soup.find_all("form"):
        action = str(form.get("action", "") or "")
        if action and _is_external(action) and not action.startswith("#"):
            form["action"] = "#"
            existing = str(form.get("onsubmit", "") or "")
            if "return false" not in existing and "preventDefault" not in existing:
                form["onsubmit"] = "return false"
            report.notes.append("Pointed form action at '#' and blocked submit.")

    for style in soup.find_all("style"):
        css = style.string or ""
        if css:
            style.string = _neutralize_css(css, report)

    for tag in soup.find_all(style=True):
        tag["style"] = _neutralize_css(str(tag["style"]), report)

    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.lower().startswith("on"):
                value = str(tag[attr] or "")
                if any(p in value for p in BLOCKED_JS_PATTERNS):
                    del tag[attr]
                    report.notes.append(f"Stripped {attr} handler using blocked APIs.")

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"] or "")
        if href.lower().lstrip().startswith("javascript:"):
            anchor["href"] = "#"
        elif href.lower().startswith(("http://", "https://")):
            anchor["target"] = "_blank"
            anchor["rel"] = "noopener noreferrer"

    body = str(soup)
    m = DOCTYPES.search(html)
    if not DOCTYPES.search(body):
        prefix = m.group(0) if m else "<!DOCTYPE html>"
        body = f"{prefix}\n{body.lstrip()}"
    return body, report
