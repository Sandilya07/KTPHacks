"""Deterministic audit engine. No LLM is involved: the rules alone decide what is a finding.

Rules live in audit/rules/ (one file each, auto-registered). Each rule sees the findings of
earlier rules in case.findings so impact is never double counted."""
from __future__ import annotations

from .models import Bill, Case, Eob
from .rules import load_rules


def run_case(case: Case) -> Case:
    """Run every rule and store the findings on the case.

    Rules see earlier findings through `work.findings`, so the working list lives on a private copy and
    is only assigned to the case at the end. Two audits of the same case at once (a double request from
    the browser) therefore cannot interleave and duplicate findings."""
    work = case.model_copy(update={"findings": []})
    for rule in load_rules():
        work.findings.extend(rule.run(work))
    case.findings = work.findings
    case.total_impact = round(sum(f.impact for f in case.findings), 2)
    return case


def run_audit(bill: dict, eob: dict) -> dict:
    """Phase 1 compatible entry point: dicts in, dicts out."""
    case = run_case(Case(bill=Bill.model_validate(bill), eob=Eob.model_validate(eob)))
    return {"findings": [f.model_dump() for f in case.findings], "total_impact": case.total_impact}
