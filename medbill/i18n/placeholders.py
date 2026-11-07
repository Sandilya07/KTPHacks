"""4B. Number-integrity layer. Dollar amounts, dates, codes, account numbers, percentages (and line ids)
are replaced by placeholder tokens like [[AMT_1]] before any text goes to a translation model, then
restored and verified afterwards. A numeric value is never translated as free text."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s\d{1,2},\s\d{4}"
# Order matters: alternatives are tried left to right at each position, so amounts and dates win
# over the bare 5-character code pattern.
PATTERN = re.compile("|".join([
    rf"(?P<DATE>(?<![A-Za-z0-9_])\d{{4}}-\d{{2}}-\d{{2}}(?![A-Za-z0-9_])|(?<![A-Za-z0-9_])\d{{1,2}}/\d{{1,2}}/\d{{2,4}}(?![A-Za-z0-9_])|\b{_MONTH})",
    r"(?P<AMT>\$\s?\d[\d,]*(?:\.\d{1,2})?|(?<![A-Za-z0-9_])\d[\d,]*\.\d{2}(?![A-Za-z0-9_]))",
    r"(?P<PCT>(?<![A-Za-z0-9_])\d+(?:\.\d+)?\s?%)",
    r"(?P<ACCT>(?<![A-Za-z0-9_])[A-Z]{2,6}-\d{3,}(?![A-Za-z0-9_]))",
    r"(?P<LINE>(?<![A-Za-z0-9_])[BE]\d{1,3}(?![A-Za-z0-9_]))",
    r"(?P<CODE>(?<![A-Za-z0-9_$.,])(?=[A-Z0-9]*\d)[A-Z0-9]{5}(?![A-Za-z0-9_]|[.,]\d))",
]))
TOKEN_RE = re.compile(r"\[\[([A-Z]+)_(\d+)\]\]")
DIGITS_RE = re.compile(r"\d+")


@dataclass
class Protected:
    masked: str
    mapping: dict[str, str] = field(default_factory=dict)  # token -> original text

    def values(self) -> Counter:
        return Counter(self.mapping.values())


def protect(text: str) -> Protected:
    counts: Counter = Counter()
    mapping: dict[str, str] = {}

    def sub(m: re.Match) -> str:
        kind = m.lastgroup or "X"
        counts[kind] += 1
        token = f"[[{kind}_{counts[kind]}]]"
        mapping[token] = m.group(0)
        return token

    return Protected(PATTERN.sub(sub, text), mapping)


def restore(text: str, mapping: dict[str, str]) -> str:
    return TOKEN_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)


def _strip_tokens(text: str) -> str:
    return TOKEN_RE.sub(" ", text)


def verify_tokens(source_masked: str, translated: str, mapping: dict[str, str]) -> list[str]:
    """Each source token must appear exactly once, none invented, no stray digits introduced."""
    errors = []
    found = Counter(m.group(0) for m in TOKEN_RE.finditer(translated))
    want = Counter(m.group(0) for m in TOKEN_RE.finditer(source_masked))
    for tok, n in want.items():
        if found[tok] != n:
            errors.append(f"token {tok} appears {found[tok]} times, expected {n}")
    for tok in found:
        if tok not in want:
            errors.append(f"unknown token {tok}")
    if Counter(DIGITS_RE.findall(_strip_tokens(translated))) != Counter(DIGITS_RE.findall(_strip_tokens(source_masked))):
        errors.append("stray or changed digits outside placeholders")
    return errors


def same_values(a: str, b: str) -> bool:
    """True when two texts carry the same multiset of protected values (amounts, codes, dates...)."""
    return protect(a).values() == protect(b).values()
