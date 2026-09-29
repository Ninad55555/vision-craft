"""Convert screenshot coordinates to and from VisionCraft's 0-1000 grid."""

from __future__ import annotations

from typing import Sequence


GRID_SIZE = 1000


def normalize_box(
    box_pixel: Sequence[float],
    image_width: int,
    image_height: int,
    grid_size: int = GRID_SIZE,
) -> list[int]:
    """Scale an ``[x1, y1, x2, y2]`` pixel box to an integer normalized grid.

    The x and y axes are scaled independently, so screenshots of any aspect ratio
    share the same coordinate range. Values are clamped to the image boundaries.
    """
    _validate_dimensions(image_width, image_height, grid_size)
    if len(box_pixel) != 4:
        raise ValueError("A box must contain exactly four coordinates")
    x1, y1, x2, y2 = (float(value) for value in box_pixel)
    if x2 < x1 or y2 < y1:
        raise ValueError("Box maximum coordinates must not precede minimum coordinates")
    values = (
        x1 / image_width * grid_size,
        y1 / image_height * grid_size,
        x2 / image_width * grid_size,
        y2 / image_height * grid_size,
    )
    return [max(0, min(grid_size, round(value))) for value in values]


def denormalize_box(
    box_norm: Sequence[float],
    image_width: int,
    image_height: int,
    grid_size: int = GRID_SIZE,
) -> list[int]:
    """Convert an ``[x1, y1, x2, y2]`` normalized box to pixel coordinates."""
    _validate_dimensions(image_width, image_height, grid_size)
    if len(box_norm) != 4:
        raise ValueError("A box must contain exactly four coordinates")
    x1, y1, x2, y2 = (float(value) for value in box_norm)
    if x2 < x1 or y2 < y1:
        raise ValueError("Box maximum coordinates must not precede minimum coordinates")
    values = (
        x1 / grid_size * image_width,
        y1 / grid_size * image_height,
        x2 / grid_size * image_width,
        y2 / grid_size * image_height,
    )
    return [
        max(0, min(image_width, round(values[0]))),
        max(0, min(image_height, round(values[1]))),
        max(0, min(image_width, round(values[2]))),
        max(0, min(image_height, round(values[3]))),
    ]


def _validate_dimensions(image_width: int, image_height: int, grid_size: int) -> None:
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Image width and height must be positive")
    if grid_size <= 0:
        raise ValueError("Grid size must be positive")
