from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from src.core.errors import VisionCraftError
from src.core.image_prep import prepare_image

FIX = Path(__file__).resolve().parent / "fixtures"


def read(name: str) -> bytes:
    return (FIX / name).read_bytes()


def prep(raw: bytes, **kwargs):
    defaults = {"max_side": 1600, "max_upload_bytes": 10 * 1024 * 1024, "max_payload_kb": 3000}
    defaults.update(kwargs)
    return prepare_image(raw, **defaults)


def test_simple_png_passthrough():
    img = prep(read("simple.png"))
    assert img.mime == "image/jpeg"
    assert img.data_url.startswith("data:image/jpeg;base64,")
    assert (img.width, img.height) == (200, 150)
    assert (img.orig_width, img.orig_height) == (200, 150)
    assert img.warnings == []
    assert img.pil is not None and img.pil.mode == "RGB"


def test_rgba_flattened_onto_white():
    img = prep(read("rgba.png"))
    assert img.pil is not None
    assert img.pil.mode == "RGB"


def test_tall_image_warns():
    img = prep(read("tall.png"))
    assert any("tall" in w.lower() for w in img.warnings)


def test_huge_image_downscaled():
    img = prep(read("huge.png"))
    assert max(img.width, img.height) <= 1600
    assert (img.orig_width, img.orig_height) == (2000, 1500)


def test_corrupt_bytes_rejected():
    with pytest.raises(VisionCraftError) as exc:
        prep(read("corrupt.bin"))
    assert exc.value.code == "IMAGE_INVALID"


def test_empty_bytes_rejected():
    with pytest.raises(VisionCraftError) as exc:
        prep(b"")
    assert exc.value.code == "IMAGE_INVALID"


def test_oversize_upload_rejected():
    big = Image.new("RGB", (200, 150), "red")
    assert len(_encode_png(big)) > 100
    with pytest.raises(VisionCraftError) as exc:
        prep(read("simple.png"), max_upload_bytes=10)
    assert exc.value.code == "IMAGE_TOO_LARGE"
    assert exc.value.http_status == 413


def test_too_small_rejected():
    tiny = Image.new("RGB", (40, 40), "red")
    with pytest.raises(VisionCraftError) as exc:
        prep(_encode_png(tiny))
    assert exc.value.code == "IMAGE_INVALID"


def test_animated_gif_first_frame_and_warning():
    img = prep(read("animated.gif"))
    assert img.pil is not None
    assert any("first frame" in w.lower() for w in img.warnings)


def test_payload_cap_loop_terminates():
    noisy = Image.effect_noise((1800, 1800), 64).convert("RGB")
    img = prep(_encode_png(noisy), max_payload_kb=50)
    import base64

    payload = base64.b64decode(img.data_url.split(",", 1)[1])
    assert len(payload) <= 50 * 1024


def test_exif_rotation_applied(tmp_path):
    img = Image.new("RGB", (200, 120), "green")
    path = tmp_path / "exif.jpg"
    exif = img.getexif()
    exif[0x0112] = 6  # rotate 90 CW
    img.save(path, exif=exif)
    out = prep(path.read_bytes())
    assert (out.width, out.height) == (120, 200)


def _encode_png(img: Image.Image) -> bytes:
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
