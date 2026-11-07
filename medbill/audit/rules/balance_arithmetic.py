from ..models import Case, Finding

NAME = "balance_arithmetic"
ORDER = 90


def run(case: Case) -> list[Finding]:
    total = round(sum(l.patient_owed for l in case.bill.lines), 2)
    bal = round(case.bill.patient_balance, 2)
    if bal == total:
        return []
    return [Finding(
        id=Finding.make_id(NAME, []), rule=NAME, tier="definite", line_ids=[], impact_line_ids=[],
        impact=max(bal - total, 0.0),
        evidence=f"Line amounts add up to {total:.2f} but the bill shows a balance of {bal:.2f}.",
        source="Arithmetic: sum of patient_owed versus patient_balance",
    )]
