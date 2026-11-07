"""Match bill lines to EOB lines (PLAN.md 2C): code + date + modifiers, then code + date,
then code only, each tier tie-broken by closeness of the amounts, then order.
Matching is one-to-one. Unmatched lines on both sides are logged."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .models import BillLine, Case, EobLine

log = logging.getLogger(__name__)


@dataclass
class MatchResult:
    pairs: dict[str, EobLine] = field(default_factory=dict)  # bill line id -> EOB line
    unmatched_bill: list[BillLine] = field(default_factory=list)
    unmatched_eob: list[EobLine] = field(default_factory=list)


def _tiers(b: BillLine, e: EobLine) -> int | None:
    if b.code != e.code:
        return None
    if b.date == e.date and sorted(b.modifiers) == sorted(e.modifiers):
        return 0
    if b.date == e.date:
        return 1
    return 2


def match_lines(case: Case) -> MatchResult:
    remaining = list(case.eob.lines)
    res = MatchResult()
    for tier in (0, 1, 2):
        for b in case.bill.lines:
            if b.id in res.pairs:
                continue
            cands = [e for e in remaining if _tiers(b, e) == tier]
            if not cands:
                continue
            # amounts: prefer the EOB line whose patient responsibility is closest to what was billed to patient
            best = min(cands, key=lambda e: (abs(b.patient_owed - e.patient_resp), remaining.index(e)))
            res.pairs[b.id] = best
            remaining.remove(best)
    res.unmatched_bill = [b for b in case.bill.lines if b.id not in res.pairs]
    res.unmatched_eob = remaining
    for b in res.unmatched_bill:
        log.info("unmatched bill line %s (%s %s)", b.id, b.code, b.date)
    for e in res.unmatched_eob:
        log.info("unmatched EOB line %s (%s %s)", e.id, e.code, e.date)
    return res
