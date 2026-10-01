from __future__ import annotations

from PIL import Image


def extract_palette(img: Image.Image, k: int = 8) -> list[str]:
    thumb = img.convert("RGB").copy()
    thumb.thumbnail((200, 200), Image.LANCZOS)
    quantized = thumb.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    rgb = quantized.convert("RGB")
    counts = rgb.getcolors(200 * 200) or []
    counts.sort(key=lambda item: -item[0])
    return ["#%02x%02x%02x" % color for _, color in counts[:k]]
