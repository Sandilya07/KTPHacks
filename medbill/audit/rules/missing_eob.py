from ..matching import match_lines
from ..models import Case, Finding
from . import flagged_line_ids

NAME = "missing_eob_line"
ORDER = 50


def run(case: Case) -> list[Finding]:
    skip = flagged_line_ids(case)
    out = []
    for b in match_lines(case).unmatched_bill:
        if b.id in skip:
            continue
        out.append(Finding(
            id=Finding.make_id(NAME, [b.id]), rule=NAME, tier="ask", line_ids=[b.id],
            impact_line_ids=[], impact=0.0,
            evidence=f"Bill line {b.id} ({b.code} on {b.date}) has no matching line on the EOB.",
            source=f"Matching by code, date and modifiers: no EOB line for {b.code} on {b.date}",
        ))
    return out
