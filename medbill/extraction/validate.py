"""Turn raw extraction dicts into validated Pydantic objects, run arithmetic/format checks,
lower confidence on any failure, and produce warnings. Extraction is never silently trusted."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from audit.models import BillLine, EobLine, Source

CODE_RE = re.compile(r"^[A-Z0-9]{5}$")
LOW_CONF = 0.8
MIN_DATE = date(2015, 1, 1)
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y")
EOB_STATUSES = {"processed", "denied-duplicate", "denied-bundled", "denied-other"}
# line field -> confidence group
GROUPS = {"date": "date", "code": "code", "description": "description", "units": "units",
          "billed": "amounts", "patient_owed": "amounts", "allowed": "amounts", "plan_paid": "amounts",
          "patient_resp": "amounts", "status": "status"}
REQUIRED = {"bill": ("date", "code", "billed", "patient_owed"), "eob": ("date", "code", "patient_resp")}


def normalize_date(s: str | None) -> str | None:
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_money(s) -> float | None:
    if s is None or isinstance(s, (int, float)):
        return None if s is None else float(s)
    cleaned = re.sub(r"[^\d.\-()]", "", str(s))
    if not cleaned:
        return None
    neg = cleaned.startswith(("(", "-"))
    try:
        v = float(cleaned.strip("()-"))
    except ValueError:
        return None
    return -v if neg else v


def make_line(kind: str, raw: dict, idx: int):
    """Build one BillLine/EobLine from a raw dict. Returns (line, failures)."""
    prefix = "B" if kind == "bill" else "E"
    conf = {k: max(0.0, min(1.0, float(v))) for k, v in (raw.get("confidence") or {}).items()
            if isinstance(v, (int, float))}
    failures: list[str] = []
    vals: dict = {}

    def fail(group: str, msg: str) -> None:
        failures.append(msg)
        conf[group] = min(conf.get(group, 1.0), 0.5)

    for name in REQUIRED[kind]:
        group = GROUPS[name]
        if raw.get(name) is None:
            fail(group, f"{name} could not be read")
    iso = normalize_date(raw.get("date"))
    if raw.get("date") is not None:
        if iso is None:
            fail("date", f"date '{raw.get('date')}' is not a valid date")
        elif not MIN_DATE <= date.fromisoformat(iso) <= date.today() + timedelta(days=1):
            fail("date", f"date {iso} is not plausible")
    vals["date"] = iso or ""
    code = (raw.get("code") or "").strip().upper()
    if raw.get("code") is not None and not CODE_RE.match(code):
        fail("code", f"code '{code}' is not a 5-character code")
    vals["code"] = code
    vals["modifiers"] = [m.strip().upper() for m in (raw.get("modifiers") or []) if m and m.strip()]
    money = ("billed", "patient_owed") if kind == "bill" else ("allowed", "plan_paid", "patient_resp")
    for name in money:
        v = parse_money(raw.get(name))
        vals[name] = 0.0 if v is None else v
        if v is not None and v < 0:
            fail("amounts", f"{name} is negative")
    if kind == "bill":
        vals["description"] = raw.get("description") or ""
        units = raw.get("units")
        vals["units"] = 1 if units is None else int(units)
        if vals["units"] < 1:
            fail("units", "units must be at least 1")
        if vals["patient_owed"] > vals["billed"] + 0.005:
            fail("amounts", "patient_owed is higher than billed")
        cls = BillLine
    else:
        status = raw.get("status") or "processed"
        vals["status"] = status if status in EOB_STATUSES else "denied-other"
        vals["adjustment_reason"] = raw.get("adjustment_reason") or ""
        cls = EobLine
    bbox, page = raw.get("bbox"), raw.get("page")
    source = Source(page=int(page), bbox=tuple(float(v) for v in bbox)) \
        if bbox and page is not None and len(bbox) == 4 else None
    line = cls(id=f"{prefix}{idx}", source=source, confidence=conf, **vals)
    relevant = ("date", "code", "description", "units", "amounts") if kind == "bill" \
        else ("date", "code", "amounts", "status")
    reported = [v for g, v in line.confidence.items() if g in relevant]
    for g in relevant:  # a group the model did not score is only as trusted as its weakest scored one
        line.confidence.setdefault(g, min(reported, default=0.7))
    return line, failures


def needs_second_pass(line, failures: list[str]) -> bool:
    return bool(failures) or line.min_confidence < LOW_CONF


def check_totals(kind: str, lines: list, printed: float | None) -> list[str]:
    """Line sums versus the printed total. Returns warnings (empty when consistent or total missing)."""
    if kind == "bill":
        total, label = round(sum(l.patient_owed for l in lines), 2), "patient balance"
    else:
        total, label = round(sum(l.patient_resp for l in lines), 2), "total patient responsibility"
    if not printed:
        return []
    if abs(total - printed) > 0.005:
        return [f"{kind}: the {label} ({printed:.2f}) does not match the sum of the lines ({total:.2f})"]
    return []
