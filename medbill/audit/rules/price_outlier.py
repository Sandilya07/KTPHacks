from ..cms_data import get_cms_data
from ..config import PRICE_OUTLIER_MULTIPLE
from ..models import Case, Finding
from . import flagged_line_ids

NAME = "price_outlier"
ORDER = 60


def run(case: Case) -> list[Finding]:
    pfs = get_cms_data().pfs
    skip = flagged_line_ids(case)
    out = []
    for b in case.bill.lines:
        price = pfs.get(b.code)
        if not price or b.id in skip or b.units < 1:
            continue
        per_unit = b.billed / b.units
        if per_unit > PRICE_OUTLIER_MULTIPLE * price:
            out.append(Finding(
                id=Finding.make_id(NAME, [b.id]), rule=NAME, tier="ask", line_ids=[b.id],
                impact_line_ids=[], impact=0.0,
                evidence=(f"Line {b.id} bills {per_unit:.2f} per unit for {b.code}; the Medicare fee "
                          f"schedule amount is {price:.2f}. This is worth asking about."),
                source=f"Medicare Physician Fee Schedule non-facility amount {price:.2f} x "
                       f"{PRICE_OUTLIER_MULTIPLE:g} threshold",
            ))
    return out
