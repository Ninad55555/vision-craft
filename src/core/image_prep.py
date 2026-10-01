from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field

from PIL import Image, ImageOps, UnidentifiedImageError

from src.core.errors import error

Image.MAX_IMAGE_PIXELS = 50_000_000

# GIF is accepted for its first frame (SPEC section 11 unit case); it is
# still re-encoded to JPEG like every other input.
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}
MIN_SIDE = 64
TALL_RATIO = 4.0


@dataclass
class PreparedImage:
    data_url: str
    mime: str
    width: int
    height: int
    orig_width: int
    orig_height: int
    warnings: list[str] = field(default_factory=list)
    pil: Image.Image | None = None


def prepare_image(raw: bytes, *, max_side: int, max_upload_bytes: int, max_payload_kb: int) -> PreparedImage:
    if len(raw) == 0:
        raise error("IMAGE_INVALID", "The uploaded file is empty.")
    if len(raw) > max_upload_bytes:
        raise error(
            "IMAGE_TOO_LARGE",
            f"File is {len(raw) // 1_048_576} MB; the limit is {max_upload_bytes // 1_048_576} MB.",
        )

    warnings: list[str] = []
    try:
        probe = Image.open(io.BytesIO(raw))
        fmt = (probe.format or "").upper()
        probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise error("IMAGE_INVALID", "Not a valid PNG, JPEG, or WebP image.") from None
    except Image.DecompressionBombError:
        raise error("IMAGE_TOO_LARGE", "Image has too many pixels.") from None

    if fmt not in ALLOWED_FORMATS:
        raise error("IMAGE_INVALID", f"Unsupported image type '{fmt or 'unknown'}'. Use PNG, JPEG, or WebP.", http_status=415)

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Image.DecompressionBombError:
        raise error("IMAGE_TOO_LARGE", "Image has too many pixels.") from None
    except (UnidentifiedImageError, OSError):
        raise error("IMAGE_INVALID", "Not a valid PNG, JPEG, or WebP image.") from None

    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
        warnings.append("Animated image: only the first frame was used.")

    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        flat = Image.new("RGB", img.size, (255, 255, 255))
        flat.paste(img, mask=img.split()[-1])
        img = flat
    else:
        img = img.convert("RGB")

    orig_width, orig_height = img.size
    if min(img.size) < MIN_SIDE:
        raise error("IMAGE_INVALID", f"Image is too small ({orig_width}x{orig_height}); minimum is {MIN_SIDE}px on each side.")

    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)

    if img.height / img.width > TALL_RATIO:
        warnings.append("Very tall screenshot: fidelity drops lower on the page.")

    data_url, actual_w, actual_h = _encode_within_cap(img, max_payload_kb)

    return PreparedImage(
        data_url=data_url,
        mime="image/jpeg",
        width=actual_w,
        height=actual_h,
        orig_width=orig_width,
        orig_height=orig_height,
        warnings=warnings,
        pil=img,
    )


def _encode_within_cap(img: Image.Image, max_payload_kb: int) -> tuple[str, int, int]:
    cap_bytes = max_payload_kb * 1024
    quality = 92
    current = img
    for _ in range(60):
        buf = io.BytesIO()
        current.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= cap_bytes:
            encoded = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}", current.size[0], current.size[1]
        if quality > 70:
            quality -= 6
            continue
        new_size = (max(1, int(current.size[0] * 0.85)), max(1, int(current.size[1] * 0.85)))
        current = current.resize(new_size, Image.LANCZOS)
    raise error("IMAGE_TOO_LARGE", "Image could not be compressed under the payload limit.")
