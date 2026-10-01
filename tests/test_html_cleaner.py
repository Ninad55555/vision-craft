from __future__ import annotations

import pytest

from src.core.errors import VisionCraftError
from src.generator.html_cleaner import clean_model_output

DOC = """<!DOCTYPE html>
<html><head><title>T</title></head><body><h1>Hello world</h1><p>Text here.</p></body></html>"""


def test_fenced_html_extracted():
    out, warnings = clean_model_output(f"Some intro\n```html\n{DOC}\n```\ntrailing", finish_reason="stop")
    assert out.startswith("<!DOCTYPE html>")
    assert "Hello world" in out
    assert warnings == []


def test_largest_fence_wins():
    small = "<!DOCTYPE html><html><body><p>small</p></body></html>"
    out, _ = clean_model_output(f"```html\n{small}\n```\n```html\n{DOC}\n```", finish_reason="stop")
    assert "Hello world" in out


def test_unfenced_html_extracted():
    out, _ = clean_model_output(f"Here it is:\n{DOC}\nDone.", finish_reason="stop")
    assert "Hello world" in out


def test_unterminated_fence_recovered_with_warning():
    partial = "<!DOCTYPE html><html><head><title>T</title></head><body><h1>Hello world</h1><p>cut"
    out, warnings = clean_model_output(f"```html\n{partial}", finish_reason="length")
    assert "Hello world" in out
    assert out.rstrip().lower().endswith("</html>")
    assert any("TRUNCATED" in w for w in warnings)


def test_truncated_mid_tag_repaired():
    partial = "<!DOCTYPE html><html><body><div><p>Hello world<span>oops"
    out, warnings = clean_model_output(partial, finish_reason="length")
    assert "Hello world" in out
    assert warnings


def test_think_blocks_stripped():
    text = "```thinking\nI should analyze the layout carefully...\n```\n```html\n" + DOC + "\n```"
    out, _ = clean_model_output(text, finish_reason="stop")
    assert "analyze the layout" not in out
    assert "Hello world" in out


def test_unterminated_think_stripped():
    text = "```thinking\nendless reasoning without close"
    with pytest.raises(VisionCraftError) as exc:
        clean_model_output(text, finish_reason="stop")
    assert exc.value.code == "OUTPUT_NOT_HTML"


def test_missing_doctype_and_meta_injected():
    bare = "<html><head><title>T</title></head><body><p>Hello world</p></body></html>"
    out, _ = clean_model_output(bare, finish_reason="stop")
    assert out.lower().startswith("<!doctype html>")
    assert 'charset="utf-8"' in out.lower()
    assert 'name="viewport"' in out.lower()


def test_non_html_rejected():
    with pytest.raises(VisionCraftError) as exc:
        clean_model_output("The image shows a cat sitting on a mat.", finish_reason="stop")
    assert exc.value.code == "OUTPUT_NOT_HTML"


def test_empty_body_rejected():
    with pytest.raises(VisionCraftError) as exc:
        clean_model_output("<!DOCTYPE html><html><head></head><body>   </body></html>", finish_reason="stop")
    assert exc.value.code == "OUTPUT_NOT_HTML"


def test_oversize_truncated_with_warning():
    big = "<!DOCTYPE html><html><body><p>Hello world</p>" + ("x" * 2_000_000) + "</body></html>"
    out, warnings = clean_model_output(big, finish_reason="stop")
    assert len(out.encode("utf-8")) <= 1_000_000 + 100
    assert any("TRUNCATED" in w for w in warnings)
