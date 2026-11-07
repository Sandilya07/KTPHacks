from ..cms_data import get_cms_data
from ..config import NCCI_OVERRIDE_MODIFIERS
from ..models import Case, Finding
from . import flagged_line_ids

NAME = "unbundling"
ORDER = 20


def run(case: Case) -> list[Finding]:
    ncci = get_cms_data().ncci
    skip = flagged_line_ids(case)  # e.g. duplicate lines
    out, done = [], set()
    for a in case.bill.lines:
        for b in case.bill.lines:
            if a is b or a.date != b.date or a.id in skip or b.id in skip or b.id in done:
                continue
            edit = ncci.lookup(a.code, b.code, a.date)
            if edit is None or edit.indicator == "9":
                continue
            done.add(b.id)
            ids = [a.id, b.id]
            override = edit.indicator == "1" and bool(set(b.modifiers) & NCCI_OVERRIDE_MODIFIERS)
            ask = override
            note = f"{a.code} and {b.code} are normally not billed together on the same day"
            out.append(Finding(
                id=Finding.make_id(NAME, ids), rule=NAME, tier="ask" if ask else "likely",
                line_ids=ids, impact_line_ids=[] if ask else [b.id],
                impact=0.0 if ask else b.patient_owed,
                evidence=(f"Codes {a.code} and {b.code} were billed on {a.date}. {note}."
                          + (f" Line {b.id} carries modifier {','.join(b.modifiers)}, so this may be allowed."
                             if ask else "")),
                source=f"NCCI PTP edit: column 1 {a.code}, column 2 {b.code}, modifier indicator "
                       f"{edit.indicator}, effective {edit.effective}"
                       + (f", deleted {edit.deletion}" if edit.deletion else ""),
            ))
    return out
