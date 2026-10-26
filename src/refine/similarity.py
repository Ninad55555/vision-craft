from __future__ import annotations

from PIL import Image


def compute_ssim(target: Image.Image, candidate: Image.Image) -> float:
    """Grayscale structural similarity in [0, 1], resized to the target."""
    try:
        import numpy as np
        from skimage.metrics import structural_similarity
    except ImportError as exc:
        from src.core.errors import error

        raise error(
            "REFINE_UNAVAILABLE",
            "Visual refinement needs scikit-image and numpy. Install requirements-refine.txt.",
        ) from exc

    size = target.size
    left = target.convert("RGB").resize(size, Image.LANCZOS)
    right = candidate.convert("RGB").resize(size, Image.LANCZOS)
    a = np.asarray(left.convert("L"), dtype=np.float64)
    b = np.asarray(right.convert("L"), dtype=np.float64)
    score = float(structural_similarity(a, b, data_range=255))
    return max(0.0, min(1.0, score))
