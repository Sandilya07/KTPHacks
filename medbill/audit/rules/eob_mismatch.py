from ..matching import match_lines
from ..models import Case, Finding
from . import flagged_line_ids

NAME = "eob_mismatch"
ORDER = 40
EPS = 0.005


def run(case: Case) -> list[Finding]:
    skip = flagged_line_ids(case)
    matches = match_lines(case).pairs
    out = []
    for b in case.bill.lines:
        e = matches.get(b.id)
        if e is None or b.id in skip:
            continue
        ids = [b.id, e.id]
        balance_billing = (case.eob.network_status == "in" and e.allowed > 0
                           and b.patient_owed >= b.billed - EPS and b.billed > e.allowed + EPS)
        if balance_billing:
            rule, diff = "balance_billing", b.patient_owed - e.patient_resp
            ev = (f"Bill line {b.id} charges the patient {b.patient_owed:.2f}, the full billed amount, "
                  f"but the in-network allowed amount on EOB line {e.id} is {e.allowed:.2f}.")
            src = f"EOB allowed amount for {b.code} on {b.date} (in network)"
        elif b.patient_owed > e.patient_resp + EPS:
            rule, diff = NAME, b.patient_owed - e.patient_resp
            ev = (f"Bill line {b.id} asks the patient for {b.patient_owed:.2f}; "
                  f"EOB line {e.id} says patient responsibility is {e.patient_resp:.2f}.")
            src = f"EOB patient responsibility for {b.code} on {b.date}"
        else:
            continue
        out.append(Finding(id=Finding.make_id(rule, ids), rule=rule, tier="definite", line_ids=ids,
                           impact_line_ids=[b.id], impact=round(diff, 2), evidence=ev, source=src))
    return out
