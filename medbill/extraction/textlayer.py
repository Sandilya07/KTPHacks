"""Deterministic extractor for PDFs that have a text layer (no model, no network).

It reads word positions, finds the table header row, assigns each word to a column by x position and
returns the same raw dict shape as the model extractor, with real bounding boxes in PDF points.
It is an offline baseline and the evaluation path for clean PDFs; photos need the vision model."""
from __future__ import annotations

import re

from .render import Page, Word
from .validate import CODE_RE, normalize_date, parse_money

BILL_PHRASES = {
    "date": ["date of service", "service date", "dos", "date"],
    "code": ["cpt/hcpcs", "hcpcs", "cpt", "code"],
    "mod": ["modifier", "mod"],
    "description": ["description", "service"],
    "units": ["units", "qty"],
    "billed": ["amount billed", "billed", "charge"],
    "patient_owed": ["patient balance", "patient owed", "you owe"],
}
EOB_PHRASES = {
    "date": ["date of service", "service date", "date"],
    "code": ["procedure", "code", "cpt"],
    "mod": ["modifier", "mod"],
    "allowed": ["allowed amt", "allowed amount", "allowed"],
    "plan_paid": ["plan paid", "insurance paid"],
    "patient_resp": ["patient resp", "you owe", "member owes"],
    "status": ["status", "decision"],
    "adjustment_reason": ["remark", "reason"],
}
MONEY_RE = re.compile(r"^\(?-?\$?[\d,]+\.\d{2}\)?$")


def _rows(words: list[Word], tol: float = 3.0) -> list[list[Word]]:
    rows: list[list[Word]] = []
    for w in sorted(words, key=lambda w: ((w.y0 + w.y1) / 2, w.x0)):
        yc = (w.y0 + w.y1) / 2
        if rows and abs(yc - sum((x.y0 + x.y1) / 2 for x in rows[-1]) / len(rows[-1])) <= tol:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w.x0) for r in rows]


def _header_columns(row: list[Word], phrases: dict[str, list[str]]) -> dict[str, float]:
    """Map field -> x0 of the header phrase, matching longest phrases first."""
    toks = [w.text.lower().strip(":") for w in row]
    found: dict[str, float] = {}
    i = 0
    options = sorted(((p.split(), f) for f, ps in phrases.items() for p in ps), key=lambda t: -len(t[0]))
    while i < len(toks):
        for words, field in options:
            if toks[i:i + len(words)] == words and field not in found:
                found[field] = row[i].x0
                i += len(words) - 1
                break
        i += 1
    return found


def _find_header(rows, phrases, required):
    for idx, row in enumerate(rows):
        cols = _header_columns(row, phrases)
        if all(f in cols for f in required):
            return idx, cols
    return None, {}


def _cells(row: list[Word], cols: dict[str, float]) -> dict[str, list[Word]]:
    order = sorted(cols.items(), key=lambda kv: kv[1])
    cells: dict[str, list[Word]] = {f: [] for f in cols}
    for w in row:
        owner = None
        for f, x in order:
            if x <= w.x0 + 3:
                owner = f
        if owner:
            cells[owner].append(w)
    return cells


def _text(ws: list[Word]) -> str:
    return " ".join(w.text for w in ws).strip()


def _find(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else None


class TextLayerExtractor:
    def extract(self, kind: str, pages: list[Page]) -> dict:
        phrases = BILL_PHRASES if kind == "bill" else EOB_PHRASES
        required = ("date", "code", "billed") if kind == "bill" else ("date", "code", "patient_resp")
        lines, all_text = [], []
        for p in pages:
            rows = _rows(p.words)
            all_text += [_text(r) for r in rows]
            h, cols = _find_header(rows, phrases, required)
            if h is None:
                continue
            for row in rows[h + 1:]:
                cells = _cells(row, cols)
                code = _text(cells.get("code", [])).upper()
                date = normalize_date(_text(cells.get("date", [])))
                if not CODE_RE.match(code) or date is None:
                    continue
                bbox = [min(w.x0 for w in row), min(w.y0 for w in row),
                        max(w.x1 for w in row), max(w.y1 for w in row)]
                mods = [m for m in re.split(r"[,\s]+", _text(cells.get("mod", []))) if m and m != "-"]
                line: dict = {"page": p.number, "bbox": bbox, "date": date, "code": code, "modifiers": mods}
                conf = {"date": 0.97, "code": 0.97, "amounts": 0.97}
                if kind == "bill":
                    units = _text(cells.get("units", []))
                    line.update(description=_text(cells.get("description", [])) or None,
                                units=int(units) if units.isdigit() else None,
                                billed=parse_money(_text(cells.get("billed", [])) or None),
                                patient_owed=parse_money(_text(cells.get("patient_owed", [])) or None))
                    conf.update(description=0.95, units=0.97 if units.isdigit() else 0.3)
                else:
                    status = _text(cells.get("status", [])).lower()
                    line.update(allowed=parse_money(_text(cells.get("allowed", [])) or None),
                                plan_paid=parse_money(_text(cells.get("plan_paid", [])) or None),
                                patient_resp=parse_money(_text(cells.get("patient_resp", [])) or None),
                                status=("denied-duplicate" if "duplicate" in status else
                                        "denied-bundled" if "bundl" in status else
                                        "denied-other" if "denied" in status else "processed"),
                                adjustment_reason=_text(cells.get("adjustment_reason", [])) or None)
                    conf["status"] = 0.95
                for k in [k for k in ("billed", "patient_owed", "allowed", "plan_paid", "patient_resp") if k in line]:
                    if line[k] is None:
                        conf["amounts"] = 0.3
                line["confidence"] = conf
                lines.append(line)
        text = "\n".join(all_text)
        money = r"\$?([\d,]+\.\d{2})"
        if kind == "bill":
            return {"provider": _find(text, r"(?:billing provider|provider)\s*:\s*(.+)"),
                    "account_number": _find(text, r"account(?: number| no\.?| #)?\s*[:#]\s*([A-Z0-9-]+)"),
                    "patient_balance": parse_money(_find(text, rf"(?:patient balance due|balance due|amount due)\s*:?\s*{money}")),
                    "lines": lines}
        net = _find(text, r"(out[- ]of[- ]network|in[- ]network)")
        return {"payer": _find(text, r"(?:payer|health plan|plan)\s*:\s*(.+)"),
                "network_status": None if net is None else ("out" if net.lower().startswith("out") else "in"),
                "total_patient_responsibility": parse_money(
                    _find(text, rf"(?:total patient responsibility|total you owe)\s*:?\s*{money}")),
                "lines": lines}

    def reextract_region(self, kind, page, bbox):
        return None  # a text layer is already exact; nothing to re-read
