from __future__ import annotations

from PIL import Image

from src.core.image_prep import PreparedImage
from src.core.prompts import build_messages, build_refine_messages


def _img(w: int = 1440, h: int = 900) -> PreparedImage:
    return PreparedImage(
        data_url="data:image/jpeg;base64,AAA",
        mime="image/jpeg",
        width=w,
        height=h,
        orig_width=w,
        orig_height=h,
        pil=Image.new("RGB", (w, h)),
    )


def test_message_structure():
    messages = build_messages(_img(), ["#0f172a", "#ffffff"], "dark mode please")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "```html" in messages[0]["content"]
    user = messages[1]
    assert user["role"] == "user"
    image_parts = [p for p in user["content"] if p.get("type") == "image_url"]
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "1440x900" in user["content"][0]["text"]
    assert "#0f172a" in user["content"][0]["text"]


def test_instructions_truncated_and_cleaned():
    long_text = "x" * 2000 + "\x00\x01control"
    messages = build_messages(_img(), [], long_text)
    text = messages[1]["content"][0]["text"]
    assert "\x00" not in text
    assert len(text) < 2000 + len(messages[1]["content"][0]["text"])
    tail = text.split("Additional instructions from the user (may be empty):")[1]
    assert len(tail.strip().splitlines()[0]) <= 1000


def test_empty_palette_allowed():
    messages = build_messages(_img(), [], "")
    assert "none" in messages[1]["content"][0]["text"].lower()


def test_refine_message_has_target_and_render():
    html = "<!DOCTYPE html><html><body><p>current</p></body></html>"
    messages = build_refine_messages(_img(), "data:image/png;base64,BBB", html, "keep the nav")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    user = messages[1]
    image_parts = [p for p in user["content"] if p.get("type") == "image_url"]
    assert [p["image_url"]["url"] for p in image_parts] == [
        "data:image/jpeg;base64,AAA",
        "data:image/png;base64,BBB",
    ]
    text = user["content"][0]["text"]
    assert "1440x900" in text
    assert "keep the nav" in text
    assert "current" in text
    assert "Image 1" in text and "Image 2" in text


def test_refine_instructions_are_sanitized():
    messages = build_refine_messages(_img(), "data:image/png;base64,BBB", "<p>x</p>", "x" * 2000 + "\x00")
    text = messages[1]["content"][0]["text"]
    assert "\x00" not in text
    section = text.split("Additional instructions from the user (may be empty):")[1].split("Current HTML:")[0]
    assert len(section.strip()) <= 1000
