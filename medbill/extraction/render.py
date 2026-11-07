"""Load a PDF or image into pages: an image, plus the text layer when the PDF has a usable one.

Bounding boxes are always in *page coordinates*: PDF points for PDFs, pixels for photos.
`scale` converts page coordinates to image pixels (image_px = page_coord * scale)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image

from .preprocess import preprocess_photo

DPI = 200
MIN_WORDS_FOR_TEXT_LAYER = 15
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


@dataclass
class Page:
    number: int  # 0-based
    image: Image.Image
    scale: float  # image pixels per page-coordinate unit
    words: list[Word] = field(default_factory=list)
    has_text_layer: bool = False

    def crop(self, bbox: tuple[float, float, float, float], pad: float = 6.0) -> Image.Image:
        x0, y0, x1, y1 = bbox
        s, w, h = self.scale, *self.image.size
        box = (max(0, int((x0 - pad) * s)), max(0, int((y0 - pad) * s)),
               min(w, int((x1 + pad) * s)), min(h, int((y1 + pad) * s)))
        return self.image.crop(box)


def load_pages(path: str | Path) -> list[Page]:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return _load_pdf(path)
    if path.suffix.lower() in IMAGE_SUFFIXES:
        img = preprocess_photo(Image.open(path))
        return [Page(0, img, 1.0)]
    raise ValueError(f"Unsupported file type: {path.suffix}")


def _load_pdf(path: Path) -> list[Page]:
    pages = []
    # Opening bytes also avoids retaining a Windows file handle if a malformed PDF fails to open.
    with pymupdf.open(stream=path.read_bytes(), filetype="pdf") as doc:
        for i, p in enumerate(doc):
            pix = p.get_pixmap(dpi=DPI)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            words = [Word(*w[:4], w[4]) for w in p.get_text("words")]
            pages.append(Page(i, img, DPI / 72.0, words, len(words) >= MIN_WORDS_FOR_TEXT_LAYER))
    return pages
