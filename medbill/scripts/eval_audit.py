#!/usr/bin/env python3
"""Audit evaluation on the synthetic set: recall of seeded errors, false positives on clean bills.

Runs the deterministic engine on ground-truth bills/EOBs (extraction is evaluated separately)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from audit.cms_data import get_cms_data
from audit.engine import run_case
from audit.models import Bill, Case, Eob

RULE_FOR = {"duplicate": "duplicate_charge", "unbundled": "unbundling", "eob_mismatch": "eob_mismatch",
            "excess_units": "excess_units", "balance_billing": "balance_billing"}


def main() -> int:
    cases = [json.loads(p.read_text()) for p in sorted((ROOT / "data" / "synthetic").glob("*/truth.json"))]
    if not cases:
        print("No synthetic data. Run: make data")
        return 2
    found = total = impact_ok = fp_strong = fp_ask = 0
    clean = 0
    misses = []
    for t in cases:
        res = run_case(Case(bill=Bill.model_validate(t["bill"]), eob=Eob.model_validate(t["eob"])))
        if t["kind"] == "seeded":
            for err in t["seeded_errors"]:
                total += 1
                hit = [f for f in res.findings if f.rule == RULE_FOR[err["type"]]
                       and set(f.impact_line_ids) & set(err["bill_line_ids"])]
                if hit:
                    found += 1
                    impact_ok += abs(hit[0].impact - err["impact"]) < 0.01
                else:
                    misses.append(f"{t['case_id']}: {err['type']}")
            extra = [f for f in res.findings if f.tier != "ask" and f.rule not in RULE_FOR.values()]
            fp_strong += len(extra)
        else:
            clean += 1
            fp_strong += sum(f.tier != "ask" for f in res.findings)
            fp_ask += sum(f.tier == "ask" for f in res.findings)
    src = get_cms_data()
    print(f"CMS data: {src.source} {src.parts}")
    print(f"Seeded error recall      : {found}/{total}")
    print(f"Dollar impact exact      : {impact_ok}/{found}")
    print(f"Clean bills              : {clean}; definite/likely false positives: {fp_strong}; 'ask' notes: {fp_ask}")
    for m in misses:
        print("  MISSED", m)
    ok = found == total and fp_strong == 0
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
