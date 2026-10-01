from __future__ import annotations

import re

from PIL import Image

from src.core.palette import extract_palette

HEX = re.compile(r"^#[0-9a-f]{6}$")


def test_solid_color_comes_first():
    img = Image.new("RGB", (300, 200), (15, 23, 42))
    palette = extract_palette(img, k=8)
    assert palette[0] == "#0f172a"
    assert all(HEX.match(c) for c in palette)


def test_deterministic_ordering():
    img = Image.new("RGB", (300, 200), (255, 255, 255))
    px = img.load()
    for x in range(300):
        for y in range(100):
            px[x, y] = (79, 70, 229)
    first = extract_palette(img)
    second = extract_palette(img)
    assert first == second
    assert first[0] == "#ffffff"


def test_caps_at_k():
    img = Image.effect_noise((200, 200), 32).convert("RGB")
    assert len(extract_palette(img, k=5)) <= 5
