"""3A. Explain each finding in plain language. The LLM may only phrase what the rules found.

Flow per finding: LLM draft -> validator -> up to 2 retries with the failure reasons -> deterministic
template. Every call is counted so the fallback rate can be reported."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from audit.models import Case, Finding
from llm import LLMClient

from .templates import code_note, fallback_explanation
from .validator import Facts, facts_for_finding, validate_text

log = logging.getLogger(__name__)
FIELDS = ("headline", "what_happened", "why_it_matters", "what_you_can_do")

TOOL = {
    "name": "write_explanation",
    "description": "Explain one billing finding to a patient in plain language (reading level grade 6 to 8).",
    "input_schema": {"type": "object", "required": list(FIELDS),
                     "properties": {k: {"type": "string"} for k in FIELDS}},
}
TONE = {
    "definite": "State the discrepancy factually. No hedging words.",
    "likely": "Say this appears to conflict with a billing rule and should be reviewed.",
    "ask": "Say this is worth asking the billing office about. Do not call it an error.",
}
SYSTEM = (
    "You explain medical billing findings to patients in plain language at a grade 6 to 8 reading level. "
    "The finding was already decided by a rules engine; you do NOT judge whether it is an error. "
    "Use ONLY the dollar amounts, codes, dates, line ids and numbers in the facts you are given; never invent "
    "or compute new numbers. Never use the words fraud, illegal, scam or lawsuit. Never accuse anyone. "
    "Keep every field short (one to three sentences)."
)


@dataclass
class Explanation:
    finding_id: str
    headline: str
    what_happened: str
    why_it_matters: str
    what_you_can_do: str
    source: str = "fallback"  # "llm" or "fallback"

    def text(self) -> str:
        return f"{self.headline} {self.what_happened} {self.why_it_matters} {self.what_you_can_do}"


@dataclass
class ExplainerStats:
    total: int = 0
    llm_ok: int = 0
    validator_failures: int = 0
    fallbacks: int = 0
    failure_reasons: list[str] = field(default_factory=list)

    @property
    def fallback_rate(self) -> float:
        return self.fallbacks / self.total if self.total else 0.0


class Explainer:
    def __init__(self, llm: LLMClient | None = None, max_retries: int = 2):
        self.llm, self.max_retries, self.stats = llm, max_retries, ExplainerStats()

    def _payload(self, case: Case, f: Finding) -> dict:
        bill = [l.model_dump(exclude={"source", "confidence", "needs_review"}) for l in case.bill.lines if l.id in f.line_ids]
        eob = [l.model_dump(exclude={"source", "confidence", "needs_review"}) for l in case.eob.lines if l.id in f.line_ids]
        codes = {l["code"] for l in bill + eob}
        return {"finding": {"rule": f.rule, "tier": f.tier, "impact": f.impact, "evidence": f.evidence, "source": f.source,
                            "line_ids": f.line_ids},
                "bill_lines": bill, "eob_lines": eob,
                "code_notes": {c: code_note(case, c) for c in sorted(codes)}}

    def explain(self, case: Case, f: Finding) -> Explanation:
        self.stats.total += 1
        facts: Facts = facts_for_finding(case, f)
        if self.llm is not None:
            feedback = ""
            for attempt in range(1 + self.max_retries):
                user = json.dumps(self._payload(case, f), indent=1) + f"\n\nTone: {TONE[f.tier]}{feedback}"
                try:
                    draft = self.llm.complete_tool(SYSTEM, user, TOOL)
                except Exception as exc:  # noqa: BLE001 - network/API failure: fall back, never crash the audit
                    log.warning("explainer LLM call failed for %s: %s", f.id, exc)
                    self.stats.failure_reasons.append(f"llm error: {exc}")
                    break
                text = {k: str(draft.get(k, "")) for k in FIELDS}
                result = validate_text(" ".join(text.values()), facts, f.tier)
                if result.ok and all(text.values()):
                    self.stats.llm_ok += 1
                    return Explanation(f.id, **text, source="llm")
                self.stats.validator_failures += 1
                self.stats.failure_reasons += result.errors or ["empty field"]
                feedback = "\n\nYour previous answer was rejected: " + "; ".join(result.errors) + ". Fix these."
                log.info("explanation for %s rejected (attempt %d): %s", f.id, attempt + 1, result.errors)
        self.stats.fallbacks += 1
        return Explanation(f.id, **fallback_explanation(case, f), source="fallback")

    def explain_all(self, case: Case) -> list[Explanation]:
        return [self.explain(case, f) for f in case.findings]
