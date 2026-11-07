#!/usr/bin/env python3
"""Generate synthetic bills + EOBs (PDF and noisy phone-photo JPEG) with ground truth.

20 cases: 10 with one seeded error (known type and dollar impact), 10 clean. 3 bill layouts and 2 EOB
layouts (different column orders, fonts, table styles). Output: data/synthetic/<case>/ with
bill.pdf, bill_photo.jpg, eob.pdf, eob_photo.jpg and truth.json. Deterministic (seeded). Synthetic only."""
from __future__ import annotations

import io
import json
import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter
from reportlab.lib.colors import Color, black
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from audit.cms_data import get_cms_data

OUT = ROOT / "data" / "synthetic"
SEED = 42

# code -> (description, billed per unit)
CODES = {"99213": ("Office visit, established", 150.0), "99214": ("Office visit, detailed", 220.0),
         "85025": ("Blood count, complete", 45.0), "93000": ("Electrocardiogram", 60.0),
         "71046": ("Chest x-ray, 2 views", 140.0), "80061": ("Lipid panel", 55.0),
         "83036": ("Hemoglobin A1c", 35.0), "80053": ("Metabolic panel", 95.0),
         "82947": ("Glucose test", 110.0)}
CLEAN_CODES = ["99213", "99214", "85025", "93000", "71046", "80061", "83036"]
PROVIDERS = ["Lakeside Family Clinic", "Riverbend Medical Group", "Oak Street Health Center",
             "Summit Imaging and Lab", "Harbor Pediatrics"]
PAYERS = ["Northwind Health Plan", "Bluebird Insurance Co", "Evergreen Mutual", "Pioneer Health Partners"]

# --- layouts: columns are (field, header label, width in points) ----------------------------------
BILL_LAYOUTS = [
    {"name": "bill-A", "font": "Helvetica", "style": "grid", "date": "%Y-%m-%d",
     "cols": [("date", "Date", 66), ("code", "Code", 46), ("mod", "Mod", 36), ("description", "Description", 150),
              ("units", "Units", 40), ("billed", "Billed", 66), ("patient_owed", "Patient Owed", 80)],
     "balance_label": "Patient Balance Due", "balance_pos": "below"},
    {"name": "bill-B", "font": "Times-Roman", "style": "zebra", "date": "%m/%d/%Y",
     "cols": [("date", "Service Date", 76), ("description", "Description", 150), ("code", "CPT", 46),
              ("mod", "Mod", 36), ("units", "Qty", 36), ("billed", "Charge", 66), ("patient_owed", "You Owe", 70)],
     "balance_label": "Amount Due", "balance_pos": "above"},
    {"name": "bill-C", "font": "Courier", "style": "underline", "date": "%b %d, %Y",
     "cols": [("code", "Code", 44), ("date", "Date of Service", 90), ("mod", "Mod", 32),
              ("description", "Description", 125), ("units", "Units", 38), ("billed", "Amount Billed", 82),
              ("patient_owed", "Patient Balance", 90)],
     "balance_label": "Patient Balance Due", "balance_pos": "below"},
]
EOB_LAYOUTS = [
    {"name": "eob-A", "font": "Helvetica", "style": "grid", "date": "%Y-%m-%d",
     "cols": [("date", "Date", 62), ("code", "Code", 46), ("mod", "Mod", 34), ("allowed", "Allowed", 60),
              ("plan_paid", "Plan Paid", 62), ("patient_resp", "Patient Resp", 72), ("status", "Status", 108),
              ("adjustment_reason", "Remark", 70)]},
    {"name": "eob-B", "font": "Times-Roman", "style": "zebra", "date": "%m/%d/%Y",
     "cols": [("date", "Service Date", 70), ("code", "Procedure", 62), ("mod", "Mod", 34), ("status", "Status", 105),
              ("allowed", "Allowed Amt", 72), ("plan_paid", "Plan Paid", 58), ("patient_resp", "You Owe", 60),
              ("adjustment_reason", "Reason", 60)]},
]
STATUS_TEXT = {"processed": "Processed", "denied-duplicate": "Denied - Duplicate",
               "denied-bundled": "Denied - Bundled", "denied-other": "Denied"}


def money(v: float) -> str:
    return f"${v:,.2f}"


# --- case construction ------------------------------------------------------------------------------
def _eob_line(code, dt, billed, rng, status="processed"):
    if status != "processed":
        return {"date": dt, "code": code, "modifiers": [], "allowed": 0.0, "plan_paid": 0.0,
                "patient_resp": 0.0, "status": status,
                "adjustment_reason": "CARC 97" if status == "denied-bundled" else "CARC 18"}
    allowed = round(billed * rng.uniform(0.5, 0.7), 2)
    resp = round(min(allowed, rng.choice([15.0, 20.0, 25.0, 30.0, round(allowed * 0.2, 2)])), 2)
    return {"date": dt, "code": code, "modifiers": [], "allowed": allowed, "plan_paid": round(allowed - resp, 2),
            "patient_resp": resp, "status": status, "adjustment_reason": ""}


def _bill_line(code, dt, units, billed, owed):
    return {"date": dt, "code": code, "modifiers": [], "description": CODES[code][0], "units": units,
            "billed": round(billed, 2), "patient_owed": round(owed, 2)}


def build_case(i: int, seeded_type: str | None, rng: random.Random) -> dict:
    d0 = date(2025, 1, 6) + timedelta(days=rng.randrange(0, 600))
    dts = [d0.isoformat(), (d0 + timedelta(days=rng.randrange(14, 40))).isoformat()]
    bill, eob, errors = [], [], []
    n_clean = rng.randint(2, 4)
    codes = rng.sample(CLEAN_CODES, n_clean)
    if seeded_type in ("unbundled", "excess_units"):
        codes = [c for c in codes if c not in ("85025",)][: n_clean - 1] or ["99213"]
    for k, code in enumerate(codes):
        dt = dts[0] if k < 2 else dts[1]
        billed = CODES[code][1]
        e = _eob_line(code, dt, billed, rng)
        eob.append(e)
        bill.append(_bill_line(code, dt, 1, billed, e["patient_resp"]))

    def add_error(kind, line_ids, impact):
        errors.append({"type": kind, "bill_line_ids": line_ids, "impact": round(impact, 2)})

    if seeded_type == "duplicate":
        src = rng.choice(bill)
        bill.append(dict(src))
        if rng.random() < 0.5:
            eob.append(_eob_line(src["code"], src["date"], src["billed"], rng, "denied-duplicate"))
        add_error("duplicate", [f"B{len(bill)}"], src["patient_owed"])
    elif seeded_type == "unbundled":
        dt = dts[0]
        e1 = _eob_line("80053", dt, 95.0, rng)
        eob += [e1, _eob_line("82947", dt, 110.0, rng, "denied-bundled")]
        owed2 = round(rng.choice([35.0, 60.0, 85.0, 110.0]), 2)
        bill += [_bill_line("80053", dt, 1, 95.0, e1["patient_resp"]), _bill_line("82947", dt, 1, 110.0, owed2)]
        add_error("unbundled", [f"B{len(bill)}"], owed2)
    elif seeded_type == "eob_mismatch":
        j = rng.randrange(len(bill))
        # Overcharge strictly between the EOB amount and the billed amount (never above billed).
        extra = round((bill[j]["billed"] - bill[j]["patient_owed"]) * rng.uniform(0.35, 0.85), 2)
        bill[j]["patient_owed"] = round(bill[j]["patient_owed"] + extra, 2)
        add_error("eob_mismatch", [f"B{j + 1}"], extra)
    elif seeded_type == "excess_units":
        code, units = "93000", rng.choice([4, 5, 6])
        limit = get_cms_data().mue.get(code)
        limit = limit.limit if limit else 1
        e = _eob_line(code, dts[1], 60.0 * units, rng)
        eob.append(e)
        bill.append(_bill_line(code, dts[1], units, 60.0 * units, e["patient_resp"]))
        add_error("excess_units", [f"B{len(bill)}"], e["patient_resp"] / units * (units - limit))
    elif seeded_type == "balance_billing":
        j = rng.randrange(len(bill))
        e = eob[j]
        impact = bill[j]["billed"] - e["patient_resp"]
        bill[j]["patient_owed"] = bill[j]["billed"]
        add_error("balance_billing", [f"B{j + 1}"], impact)

    for n, l in enumerate(bill, 1):
        l["id"] = f"B{n}"
    for n, l in enumerate(eob, 1):
        l["id"] = f"E{n}"
    total_resp = round(sum(l["patient_resp"] for l in eob), 2)
    prov, payer = rng.choice(PROVIDERS), rng.choice(PAYERS)
    return {
        "case_id": f"case{i:02d}", "kind": "seeded" if seeded_type else "clean", "seeded_type": seeded_type,
        "bill": {"provider": prov, "account_number": f"ACCT-{rng.randrange(10000, 99999)}",
                 "patient_balance": round(sum(l["patient_owed"] for l in bill), 2), "lines": bill},
        "eob": {"payer": payer, "network_status": "in", "total_patient_responsibility": total_resp, "lines": eob},
        "seeded_errors": errors, "expected_total": round(sum(e["impact"] for e in errors), 2),
    }


# --- PDF rendering ----------------------------------------------------------------------------------
def _fit(text: str, font: str, size: float, width: float) -> str:
    while text and stringWidth(text, font, size) > width - 4:
        text = text[:-1]
    return text


def render_pdf(path: Path, doc: dict, kind: str, layout: dict) -> list[list[float]]:
    """Draw the document; returns each line's bbox in PDF points (top-left origin)."""
    font, size, row_h = layout["font"], 9.5, 20
    bold = {"Helvetica": "Helvetica-Bold", "Times-Roman": "Times-Bold", "Courier": "Courier-Bold"}[font]
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    H = 792
    x0 = 36
    c.setFont(bold, 15)
    c.drawString(x0, H - 50, doc["provider"] if kind == "bill" else doc["payer"])
    c.setFont(font, size)
    y = H - 75
    if kind == "bill":
        c.drawString(x0, y, f"Provider: {doc['provider']}")
        c.drawString(x0, y - 14, f"Account: {doc['account_number']}")
        if layout["balance_pos"] == "above":
            c.setFont(bold, 11)
            c.drawString(x0, y - 32, f"{layout['balance_label']}: {money(doc['patient_balance'])}")
            c.setFont(font, size)
    else:
        c.drawString(x0, y, f"Payer: {doc['payer']}")
        c.drawString(x0, y - 14, "Network Status: In-Network" if doc["network_status"] == "in" else
                     "Network Status: Out-of-Network")
    top = y - 60
    xs, x = {}, x0
    for field, label, w in layout["cols"]:
        xs[field] = (x, w)
        assert stringWidth(label, bold, size) <= w - 2, f"header '{label}' too wide in {layout['name']}"
        x += w
    table_w = x - x0
    # header
    if layout["style"] == "grid":
        c.setFillColor(Color(0.85, 0.88, 0.92))
        c.rect(x0 - 2, top - 5, table_w + 4, row_h, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont(bold, size)
    for field, (cx, _) in xs.items():
        c.drawString(cx, top, {f: l for f, l, _ in layout["cols"]}[field])
    if layout["style"] == "underline":
        c.line(x0, top - 6, x0 + table_w, top - 6)
    c.setFont(font, size)
    bboxes = []
    for n, line in enumerate(doc["lines"], 1):
        ry = top - n * row_h
        if layout["style"] == "zebra" and n % 2 == 0:
            c.setFillColor(Color(0.93, 0.93, 0.93))
            c.rect(x0 - 2, ry - 5, table_w + 4, row_h, fill=1, stroke=0)
            c.setFillColor(black)
        if layout["style"] == "grid":
            c.setStrokeColor(Color(0.6, 0.6, 0.6))
            c.rect(x0 - 2, ry - 5, table_w + 4, row_h, fill=0, stroke=1)
        for field, (cx, w) in xs.items():
            if field == "date":
                val = date.fromisoformat(line["date"]).strftime(layout["date"])
            elif field == "mod":
                val = ",".join(line["modifiers"]) or "-"
            elif field in ("billed", "patient_owed", "allowed", "plan_paid", "patient_resp"):
                val = money(line[field])
            elif field == "status":
                val = STATUS_TEXT[line["status"]]
            else:
                val = str(line.get(field, ""))
            c.drawString(cx, ry, _fit(val, font, size, w))
        bboxes.append([x0 - 2, H - (ry + row_h - 5), x0 + table_w + 2, H - (ry - 5)])
    after = top - (len(doc["lines"]) + 1) * row_h
    c.setFont(bold, 11)
    if kind == "bill" and layout["balance_pos"] == "below":
        c.drawString(x0, after, f"{layout['balance_label']}: {money(doc['patient_balance'])}")
    if kind == "eob":
        c.drawString(x0, after, f"Total Patient Responsibility: {money(doc['total_patient_responsibility'])}")
    c.save()
    return bboxes


# --- phone-photo noise -------------------------------------------------------------------------------
def photo_variant(pdf: Path, out: Path, rng: random.Random) -> None:
    with pymupdf.open(pdf) as d:
        pix = d[0].get_pixmap(dpi=130)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    bg = Image.new("RGB", (img.width + 120, img.height + 120), (92, 86, 80))
    bg.paste(img, (60, 60))
    bg = bg.rotate(rng.uniform(-5, 5), resample=Image.BICUBIC, expand=True, fillcolor=(92, 86, 80))
    bg = bg.filter(ImageFilter.GaussianBlur(rng.uniform(0.7, 1.3)))
    # shadow gradient across the page
    w, h = bg.size
    lo = rng.uniform(0.62, 0.85)
    grad = Image.linear_gradient("L").resize((w, h)).rotate(rng.choice([0, 90, 180, 270]))
    grad = grad.point(lambda v: int(255 * (lo + (1 - lo) * v / 255)))
    bg = Image.composite(bg, Image.new("RGB", bg.size, (0, 0, 0)), grad)
    buf = io.BytesIO()
    bg.save(buf, format="JPEG", quality=rng.randint(45, 65))
    out.write_bytes(buf.getvalue())


def main() -> None:
    rng = random.Random(SEED)
    if OUT.exists():
        shutil.rmtree(OUT)
    seeded = ["duplicate"] * 3 + ["unbundled"] * 2 + ["eob_mismatch"] * 2 + ["excess_units"] + ["balance_billing"] * 2
    plan = [(i, seeded[i] if i < 10 else None) for i in range(20)]
    for i, kind in plan:
        case = build_case(i, kind, rng)
        d = OUT / case["case_id"]
        d.mkdir(parents=True)
        bl, el = BILL_LAYOUTS[i % 3], EOB_LAYOUTS[i % 2]
        case["layouts"] = {"bill": bl["name"], "eob": el["name"]}
        case["bboxes"] = {"bill": render_pdf(d / "bill.pdf", case["bill"], "bill", bl),
                          "eob": render_pdf(d / "eob.pdf", case["eob"], "eob", el)}
        photo_variant(d / "bill.pdf", d / "bill_photo.jpg", rng)
        photo_variant(d / "eob.pdf", d / "eob_photo.jpg", rng)
        (d / "truth.json").write_text(json.dumps(case, indent=2) + "\n")
    print(f"Wrote {len(plan)} cases to {OUT}")


if __name__ == "__main__":
    main()
