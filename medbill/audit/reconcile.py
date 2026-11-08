"""Deterministic document comparison and a correction sandbox; no generated amounts."""
from decimal import Decimal, ROUND_HALF_UP

from .engine import run_case
from .matching import match_lines
from .models import Case


def amount(value) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Enter a finite amount.")
    return result.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)


def reconciliation(case: Case) -> dict:
    matches = match_lines(case)
    rows = []
    for bill in case.bill.lines:
        eob = matches.pairs.get(bill.id)
        basis = "unmatched"
        if eob:
            basis = ("code" if bill.date != eob.date else "date" if sorted(bill.modifiers) != sorted(eob.modifiers) else "exact")
        findings = [f.id for f in case.findings if bill.id in f.line_ids]
        rows.append({
            "bill_id": bill.id, "eob_id": eob.id if eob else None,
            "code": bill.code, "date": bill.date, "eob_date": eob.date if eob else None,
            "bill_owed": float(amount(bill.patient_owed)),
            "eob_responsibility": float(amount(eob.patient_resp)) if eob else None,
            "difference": float(amount(bill.patient_owed) - amount(eob.patient_resp)) if eob else None,
            "match_basis": basis, "finding_ids": findings,
            "line_ids": [bill.id, *([eob.id] if eob else [])],
        })
    eob_total = (float(amount(case.eob.total_patient_responsibility))
                 if "total_patient_responsibility" in case.eob.model_fields_set else None)
    balance = amount(case.bill.patient_balance)
    line_total = sum((amount(line.patient_owed) for line in case.bill.lines), Decimal(0))
    return {
        "bill_balance": float(balance), "bill_line_total": float(line_total),
        "balance_matches_lines": balance == line_total,
        "eob_total": eob_total,
        "statement_difference": float(balance - amount(eob_total)) if eob_total is not None else None,
        "matched_lines": len(matches.pairs), "total_lines": len(rows),
        "rows": rows,
        "unmatched_eob": [{"id": line.id, "code": line.code, "date": line.date,
                           "patient_responsibility": line.patient_resp} for line in matches.unmatched_eob],
        "tiers": {tier: {"count": sum(f.tier == tier for f in case.findings),
                         "impact": float(sum((amount(f.impact) for f in case.findings if f.tier == tier), Decimal(0)))}
                  for tier in ("definite", "likely", "ask")},
    }


def preview_correction(case: Case, line_id: str, patient_owed: float) -> dict:
    """Change one patient's line amount and the stated balance by the same delta on a deep copy.

    This models a corrected statement, not a promise about what the patient should pay.
    Original documents, confirmation, findings and all other amounts stay untouched.
    """
    original = run_case(case.model_copy(deep=True))
    proposed = original.model_copy(deep=True)
    line = next((line for line in proposed.bill.lines if line.id == line_id), None)
    if line is None:
        raise ValueError("That bill line was not found.")
    correction = amount(patient_owed)
    if not correction.is_finite() or correction < 0:
        raise ValueError("Enter a finite, nonnegative amount.")
    old = amount(line.patient_owed)
    balance = amount(proposed.bill.patient_balance) + correction - old
    if balance < 0:
        raise ValueError("This correction would make the stated balance negative. Review the original amounts first.")
    line.patient_owed = float(correction)
    proposed.bill.patient_balance = float(balance)
    run_case(proposed)
    before_ids = {finding.id for finding in original.findings}
    after_ids = {finding.id for finding in proposed.findings}
    return {
        "preview_only": True, "line_id": line_id,
        "original_line_amount": float(old), "proposed_line_amount": float(correction),
        "original_balance": original.bill.patient_balance, "proposed_balance": proposed.bill.patient_balance,
        "original_impact": original.total_impact, "proposed_impact": proposed.total_impact,
        "impact_change": float(amount(original.total_impact) - amount(proposed.total_impact)),
        "resolved_finding_ids": sorted(before_ids - after_ids), "new_finding_ids": sorted(after_ids - before_ids),
        "remaining_finding_count": len(proposed.findings),
    }
