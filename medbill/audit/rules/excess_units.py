from collections import defaultdict

from ..cms_data import get_cms_data
from ..models import Case, Finding
from . import flagged_line_ids

NAME = "excess_units"
ORDER = 30


def run(case: Case) -> list[Finding]:
    mue = get_cms_data().mue
    out = []
    # MAI 1 = per claim line; MAI 2 and 3 = per date of service across lines.
    per_day: dict[tuple[str, str], list] = defaultdict(list)
    skip = flagged_line_ids(case)  # lines already charged back (e.g. duplicates) are not recounted
    for line in case.bill.lines:
        if line.id in skip:
            continue
        per_day[(line.code, line.date)].append(line)
    for (code, date), lines in per_day.items():
        entry = mue.get(code)
        if entry is None:
            continue
        groups = [[l] for l in lines] if entry.mai == "1" else [lines]
        for grp in groups:
            units = sum(l.units for l in grp)
            if units <= entry.limit:
                continue
            # Charge the excess starting from the last line.
            excess, impact, ids = units - entry.limit, 0.0, []
            for l in reversed(grp):
                take = min(excess, l.units)
                if take:
                    impact += l.patient_owed / l.units * take
                    ids.append(l.id)
                    excess -= take
            all_ids = [l.id for l in grp]
            out.append(Finding(
                id=Finding.make_id(NAME, all_ids), rule=NAME, tier="likely", line_ids=all_ids,
                impact_line_ids=ids, impact=round(impact, 2),
                evidence=f"{units} units of {code} were billed on {date}; the limit is {entry.limit}.",
                source=f"MUE: {code} limit {entry.limit}, adjudication indicator {entry.mai}",
            ))
    return out
