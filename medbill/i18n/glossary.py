"""4A. Per-language glossary files (i18n/glossary_<lang>.json). Adding a language = adding one file."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DIR = Path(__file__).parent

# canonical term -> pattern for finding it in English source text
TERM_PATTERNS = {
    "deductible": r"\bdeductibles?\b", "copay": r"\bco-?pays?\b", "coinsurance": r"\bco-?insurance\b",
    "allowed amount": r"\ballowed amounts?\b", "EOB": r"\bEOBs?\b|\bexplanations? of benefits\b",
    "in-network": r"\bin-network\b", "out-of-network": r"\bout-of-network\b",
    "prior authorization": r"\bprior authorizations?\b", "balance billing": r"\bbalance billing\b",
    "billed amount": r"\bbilled amounts?\b", "patient responsibility": r"\bpatient responsibility\b",
    "claim": r"\bclaims?\b", "denial": r"\bdenials?\b", "appeal": r"\bappeals?\b",
    "itemized bill": r"\bitemized bills?\b",
}


@dataclass
class Glossary:
    lang: str
    name: str
    reviewed: bool
    terms: dict[str, dict]  # canonical -> {"pinned": str, "check": optional substring}
    phrases: dict[str, str]
    hints: dict[str, list[str]] = field(default_factory=dict)
    speech_lang: str = ""

    def terms_in(self, english: str) -> list[str]:
        return [t for t, pat in TERM_PATTERNS.items() if t in self.terms and re.search(pat, english, re.IGNORECASE)]

    def prompt_block(self, english: str) -> str:
        used = self.terms_in(english)
        return "\n".join(f'- "{t}" must be translated as "{self.terms[t]["pinned"]}"' for t in used)

    def check(self, english: str, translated: str) -> list[str]:
        """Glossary terms that appear in the English source must appear pinned in the translation."""
        low = translated.lower()
        errs = []
        for t in self.terms_in(english):
            entry = self.terms[t]
            needle = entry.get("check") or entry["pinned"]
            if needle.lower() not in low:
                errs.append(f'"{t}" should appear as "{entry["pinned"]}"')
        return errs


_cache: dict[str, Glossary] = {}


def load_glossary(lang: str) -> Glossary:
    if lang not in _cache:
        path = DIR / f"glossary_{lang}.json"
        if not path.exists():
            raise KeyError(f"No glossary for language '{lang}'")
        d = json.loads(path.read_text(encoding="utf-8"))
        _cache[lang] = Glossary(d["lang"], d["name"], d.get("reviewed", False), d["terms"], d["phrases"],
                                d.get("hints", {}), d.get("speech_lang", d["lang"]))
    return _cache[lang]


def supported_languages() -> list[str]:
    return sorted(p.stem.removeprefix("glossary_") for p in DIR.glob("glossary_*.json"))
