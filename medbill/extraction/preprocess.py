"""Photo preprocessing with Pillow + numpy: auto-rotate (EXIF), deskew, boost contrast."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps


def estimate_skew(img: Image.Image, max_angle: float = 8.0, step: float = 0.5) -> float:
    """Angle (degrees, counter-clockwise positive) that best straightens text rows.

    Uses the projection-profile method: the right angle maximizes row-sum variance."""
    small = ImageOps.autocontrast(img.convert("L"))
    small.thumbnail((700, 700))
    arr = 255 - np.asarray(small.point(lambda v: 255 if v > 150 else 0), dtype=np.uint8)
    pil = Image.fromarray(arr)
    best, best_score = 0.0, -1.0
    for a in np.arange(-max_angle, max_angle + step, step):
        rot = np.asarray(pil.rotate(float(a), resample=Image.BILINEAR), dtype=np.float32)
        score = float(np.var(rot.sum(axis=1)))
        if score > best_score:
            best, best_score = float(a), score
    return best


def preprocess_photo(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img).convert("RGB")
    angle = estimate_skew(img)
    if abs(angle) >= 0.5:
        img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))
    return ImageOps.autocontrast(img, cutoff=1)
