from ..models import Case, Finding

NAME = "duplicate_charge"
ORDER = 10
REPEAT = {"76", "77"}


def run(case: Case) -> list[Finding]:
    out, seen = [], {}
    for line in case.bill.lines:
        key = (line.code, line.date)
        first = seen.setdefault(key, line)
        if first is line:
            continue
        mods = set(line.modifiers) | set(first.modifiers)
        # Repeat-procedure modifiers or different modifiers (e.g. left/right) may be legitimate.
        legit = bool(mods & REPEAT) or sorted(first.modifiers) != sorted(line.modifiers)
        ids = [first.id, line.id]
        out.append(Finding(
            id=Finding.make_id(NAME, ids), rule=NAME, tier="ask" if legit else "definite",
            line_ids=ids, impact_line_ids=[] if legit else [line.id],
            impact=0.0 if legit else line.patient_owed,
            evidence=(f"Code {line.code} appears on {line.date} in lines {first.id} and {line.id}"
                      + (" with a repeat or differing modifier, which can be legitimate." if legit else ".")),
            source=f"Duplicate rule: same code and date of service ({line.code}, {line.date})",
        ))
    return out
