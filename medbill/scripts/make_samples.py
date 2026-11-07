#!/usr/bin/env python3
"""Build the committed demo samples in data/samples/: overcharge (PDF), overcharge_photo (phone photo),
clean, and ask (only 'worth asking' findings). Each has bill + EOB files and a cached extraction
(extraction.json) that DEMO_MODE serves so the demo works offline. Synthetic data only."""
from __future__ import annotations

import importlib.util
import json
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "generate_synthetic.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)
OUT = ROOT / "data" / "samples"


def raw_extraction(doc: dict, kind: str, bboxes, geometry=None, weak=()) -> dict:
    lines = []
    for i, (l, bb) in enumerate(zip(doc["lines"], bboxes, strict=True)):
        bb = gen.map_bbox(bb, geometry) if geometry else bb
        conf = {"date": 0.97, "code": 0.97, "amounts": 0.97, "description": 0.95, "units": 0.97, "status": 0.95}
        if i in weak:
            conf["amounts"] = 0.62  # a smudged number: the review screen should highlight it
        lines.append({**{k: v for k, v in l.items() if k != "id"}, "page": 0, "bbox": bb, "confidence": conf})
    head = ({"provider": doc["provider"], "account_number": doc["account_number"], "patient_balance": doc["patient_balance"]}
            if kind == "bill" else {"payer": doc["payer"], "network_status": doc["network_status"],
                                    "total_patient_responsibility": doc["total_patient_responsibility"]})
    return {**head, "lines": lines}


def bl(code, date, units, billed, owed, mods=None):
    return {"date": date, "code": code, "modifiers": mods or [], "description": gen.CODES.get(code, ("Chest x-ray, 2 views",))[0],
            "units": units, "billed": billed, "patient_owed": owed}


def ask_case() -> dict:
    b = [bl("99213", "2026-02-10", 1, 150.0, 20.0), bl("93000", "2026-02-10", 1, 60.0, 25.0),
         bl("93000", "2026-02-10", 1, 60.0, 25.0, ["76"]), bl("85025", "2026-02-10", 1, 45.0, 10.0),
         bl("71046", "2026-02-10", 1, 900.0, 30.0)]
    e = [{"date": "2026-02-10", "code": c, "modifiers": m, "allowed": a, "plan_paid": a - r, "patient_resp": r,
          "status": "processed", "adjustment_reason": ""}
         for c, m, a, r in (("99213", [], 90.0, 20.0), ("93000", [], 37.0, 25.0), ("93000", ["76"], 37.0, 25.0),
                            ("71046", [], 60.0, 30.0))]
    for n, l in enumerate(b, 1):
        l["id"] = f"B{n}"
    for n, l in enumerate(e, 1):
        l["id"] = f"E{n}"
    return {"bill": {"provider": "Harbor Pediatrics", "account_number": "ACCT-0003",
                     "patient_balance": sum(x["patient_owed"] for x in b), "lines": b},
            "eob": {"payer": "Evergreen Mutual", "network_status": "in", "total_patient_responsibility": 80.0, "lines": e}}


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    rng = random.Random(7)
    sources = {"overcharge": json.loads((ROOT / "data" / "overcharge.json").read_text()),
               "clean": json.loads((ROOT / "data" / "clean.json").read_text()), "ask": ask_case()}
    layouts = {"overcharge": (0, 0), "clean": (1, 1), "ask": (2, 0)}
    for name, doc in sources.items():
        d = OUT / name
        d.mkdir(parents=True)
        bi, ei = layouts[name]
        bb = gen.render_pdf(d / "bill.pdf", doc["bill"], "bill", gen.BILL_LAYOUTS[bi])
        eb = gen.render_pdf(d / "eob.pdf", doc["eob"], "eob", gen.EOB_LAYOUTS[ei])
        ext = {"bill": raw_extraction(doc["bill"], "bill", bb), "eob": raw_extraction(doc["eob"], "eob", eb)}
        (d / "extraction.json").write_text(json.dumps(ext, indent=1) + "\n")
        if name == "overcharge":  # the phone-photo version of case 1
            p = OUT / "overcharge_photo"
            p.mkdir()
            gb = gen.photo_variant(d / "bill.pdf", p / "bill.jpg", rng)
            ge = gen.photo_variant(d / "eob.pdf", p / "eob.jpg", rng)
            ext = {"bill": raw_extraction(doc["bill"], "bill", bb, gb, weak=(4,)),
                   "eob": raw_extraction(doc["eob"], "eob", eb, ge)}
            (p / "extraction.json").write_text(json.dumps(ext, indent=1) + "\n")
    print("Wrote", sorted(x.name for x in OUT.iterdir()))


if __name__ == "__main__":
    main()
