"""Validator (critical). Guarantees LLM text cannot introduce facts:
  * every dollar amount, number, code, date and line id must appear in the source facts;
  * every sentence that contains a number must reference a value from the finding;
  * banned words (fraud, illegal, scam, lawsuit) are rejected;
  * the tier's required tone is present (definite factual / likely 'appears to conflict... review' /
    ask 'worth asking the billing office')."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from audit.models import Case, Finding

BANNED = re.compile(r"\b(fraud\w*|illegal\w*|scam\w*|lawsuit\w*)\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
LINE_RE = re.compile(r"\b[BE]\d{1,3}\b")
CODE_RE = re.compile(r"(?<![\w$.,])(?=[A-Z0-9]*\d)[A-Z0-9]{5}(?!\w|[.,]\d)")  # not a piece of an amount
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Facts:
    numbers: set[float] = field(default_factory=set)
    codes: set[str] = field(default_factory=set)
    dates: set[str] = field(default_factory=set)
    line_ids: set[str] = field(default_factory=set)

    def absorb(self, text: str) -> None:
        self.dates |= set(DATE_RE.findall(text))
        self.line_ids |= set(LINE_RE.findall(text))
        self.codes |= set(CODE_RE.findall(text))
        for tok in NUM_RE.findall(DATE_RE.sub(" ", text)):
            try:
                self.numbers.add(float(tok.replace(",", "")))
            except ValueError:
                pass

    def merge(self, other: Facts) -> Facts:
        self.numbers |= other.numbers
        self.codes |= other.codes
        self.dates |= other.dates
        self.line_ids |= other.line_ids
        return self


def facts_for_finding(case: Case, f: Finding) -> Facts:
    facts = Facts()
    facts.absorb(f"{f.evidence} {f.source} {f.impact:.2f}")
    facts.line_ids |= set(f.line_ids)
    by_id = {l.id: l for l in case.bill.lines} | {l.id: l for l in case.eob.lines}
    for lid in f.line_ids:
        line = by_id.get(lid)
        if line is None:
            continue
        facts.absorb(" ".join(str(v) for v in line.model_dump(exclude={"source", "confidence"}).values()))
        facts.line_ids.add(lid)
    return facts


def facts_for_case(case: Case, findings: list[Finding] | None = None) -> Facts:
    facts = Facts()
    for f in findings if findings is not None else case.findings:
        facts.merge(facts_for_finding(case, f))
    facts.absorb(f"{case.total_impact:.2f}")
    return facts


@dataclass
class Validation:
    ok: bool
    errors: list[str] = field(default_factory=list)


def check_numbers(text: str, facts: Facts) -> list[str]:
    errors = []
    for sentence in SENTENCE_RE.split(text):
        if not re.search(r"\d", sentence):
            continue
        s = sentence
        for d in DATE_RE.findall(s):
            if d not in facts.dates:
                errors.append(f"date {d} not in source data")
        s = DATE_RE.sub(" ", s)
        for lid in LINE_RE.findall(s):
            if lid not in facts.line_ids:
                errors.append(f"line id {lid} not in source data")
        s = LINE_RE.sub(" ", s)
        for code in CODE_RE.findall(s):
            if code not in facts.codes:
                errors.append(f"code {code} not in source data")
        s = CODE_RE.sub(" ", s)
        for tok in NUM_RE.findall(s):
            val = float(tok.replace(",", "").rstrip("."))
            if val not in facts.numbers:
                errors.append(f"number {tok} not in source data")
    return errors


def check_tone(text: str, tier: str) -> list[str]:
    low = text.lower()
    if tier == "likely":
        ok = re.search(r"appears? to", low) and "review" in low
        return [] if ok else ["likely tier must say this appears to conflict with a billing rule and should be reviewed"]
    if tier == "ask":
        ok = "worth asking" in low and "billing office" in low
        return [] if ok else ["ask tier must say this is worth asking the billing office about"]
    hedges = re.search(r"\b(might|possibly|perhaps|maybe)\b", low)
    return ["definite tier must state the discrepancy factually (no hedging)"] if hedges else []


def validate_text(text: str, facts: Facts, tier: str | None = None) -> Validation:
    errors = [f"banned word '{m.group(0)}'" for m in BANNED.finditer(text)]
    errors += check_numbers(text, facts)
    if tier:
        errors += check_tone(text, tier)
    return Validation(not errors, errors)
