"""Extractor that replays a stored extraction (DEMO_MODE sample cases, so the demo works offline)."""
from __future__ import annotations

import copy

from .render import Page


class CachedExtractor:
    def __init__(self, raw: dict[str, dict]):
        self.raw = raw  # {"bill": {...}, "eob": {...}} in the extraction schema (bboxes in page coordinates)

    def extract(self, kind: str, pages: list[Page]) -> dict:
        return copy.deepcopy(self.raw[kind])

    def reextract_region(self, kind, page, bbox):
        return None
