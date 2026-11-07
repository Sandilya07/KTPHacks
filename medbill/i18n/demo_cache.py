"""Hand-written translations keyed by *masked* English text, so DEMO_MODE shows verified-safe translations
with no model. Files: i18n/demo_cache_<lang>.json. Missing files just mean an empty cache."""
from __future__ import annotations

import json
from pathlib import Path

from .glossary import supported_languages

DIR = Path(__file__).parent


def load_demo_cache() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for lang in supported_languages():
        p = DIR / f"demo_cache_{lang}.json"
        out[lang] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return out
