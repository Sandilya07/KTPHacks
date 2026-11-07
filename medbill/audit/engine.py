"""Deterministic audit engine. No LLM is involved: the rules alone decide what is a finding.

Rules live in audit/rules/ (one file each, auto-registered). Each rule sees the findings of
earlier rules in case.findings so impact is never double counted."""
from __future__ import annotations

from .models import Bill, Case, Eob
from .rules import load_rules


def run_case(case: Case) -> Case:
    case.findings = []
    for rule in load_rules():
        case.findings.extend(rule.run(case))
    case.total_impact = round(sum(f.impact for f in case.findings), 2)
    return case


def run_audit(bill: dict, eob: dict) -> dict:
    """Phase 1 compatible entry point: dicts in, dicts out."""
    case = run_case(Case(bill=Bill.model_validate(bill), eob=Eob.model_validate(eob)))
    return {"findings": [f.model_dump() for f in case.findings], "total_impact": case.total_impact}
