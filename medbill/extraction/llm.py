"""Model-backed extractor using Anthropic tool use. The model name comes from the MODEL env var."""
from __future__ import annotations

import base64
import io
import os
from typing import Protocol

from PIL import Image

from llm import tool_call_options

from .render import Page
from .schema import SYSTEM_PROMPT, TOOLS

DEFAULT_MODEL = "claude-sonnet-5-5"


class Extractor(Protocol):
    """Returns the raw dict described by extraction/schema.py. Bboxes are in *page coordinates*."""

    def extract(self, kind: str, pages: list[Page]) -> dict: ...

    def reextract_region(self, kind: str, page: Page, bbox: tuple[float, float, float, float]) -> dict | None:
        """Re-read one line from a cropped region. Return the single line dict or None."""
        ...


def _png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


class AnthropicExtractor:
    def __init__(self, client=None, model: str | None = None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.client = client
        self.model = model or os.environ.get("MODEL", DEFAULT_MODEL)

    def _call(self, kind: str, content: list[dict]) -> dict:
        tool = TOOLS[kind]
        resp = self.client.messages.create(
            model=self.model, max_tokens=8000,
            system=SYSTEM_PROMPT + f"\nReturn the result by calling the {tool['name']} tool.", tools=[tool],
            **tool_call_options(self.model, tool["name"]),
            messages=[{"role": "user", "content": content}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        raise RuntimeError("Model did not return the extraction tool call")

    def extract(self, kind: str, pages: list[Page]) -> dict:
        content: list[dict] = []
        for p in pages:
            content.append({"type": "text", "text": f"Page index {p.number}. Image size {p.image.size[0]}x{p.image.size[1]} px."})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                        "data": _png_b64(p.image)}})
            if p.has_text_layer:
                content.append({"type": "text", "text": "Text layer of this page:\n" + " ".join(w.text for w in p.words)})
        content.append({"type": "text", "text": f"Extract this {kind} using the tool. Bounding boxes in image pixels."})
        raw = self._call(kind, content)
        scale = {p.number: p.scale for p in pages}
        for line in raw.get("lines", []):  # image pixels -> page coordinates
            s = scale.get(line.get("page", 0), 1.0)
            if line.get("bbox"):
                line["bbox"] = [v / s for v in line["bbox"]]
        return raw

    def reextract_region(self, kind, page, bbox):
        crop = page.crop(bbox)
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _png_b64(crop)}},
            {"type": "text", "text": f"This crop shows one line of a {kind}. Extract exactly that one line "
                                     "using the tool; set page to 0 and bbox to the whole crop. Null if unreadable."},
        ]
        raw = self._call(kind, content)
        lines = raw.get("lines") or []
        if not lines:
            return None
        line = lines[0]
        line["page"], line["bbox"] = page.number, list(bbox)
        return line
