#!/usr/bin/env python3
"""Extraction evaluation: field-level accuracy for code, units, billed, patient_owed + line recall.

--extractor text : deterministic text-layer extractor (PDF only, no network)
--extractor llm  : vision model via the Anthropic API (needs ANTHROPIC_API_KEY; PDFs and photos)
--extractor auto : llm when a key is set, otherwise text (photos are skipped without a key)

"Silent errors" are wrong fields on lines NOT flagged needs_review: they must be zero."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from extraction.pipeline import extract_document
from extraction.textlayer import TextLayerExtractor

BILL_FIELDS = ("code", "units", "billed", "patient_owed")
EOB_FIELDS = ("code", "allowed", "plan_paid", "patient_resp")


def match(truth_lines, got_lines):
    """Greedy one-to-one match by (code, date), in order."""
    used, pairs = set(), []
    for t in truth_lines:
        for j, g in enumerate(got_lines):
            if j not in used and g.code == t["code"] and g.date == t["date"]:
                used.add(j)
                pairs.append((t, g))
                break
        else:
            pairs.append((t, None))
    return pairs


def evaluate(extractor, files, kind):
    fields = BILL_FIELDS if kind == "bill" else EOB_FIELDS
    stats = {"fields": 0, "correct": 0, "lines": 0, "found": 0, "silent": 0, "flagged_wrong": 0}
    for path, truth in files:
        got = extract_document(path, kind, extractor).model
        for t, g in match(truth["lines"], got.lines):
            stats["lines"] += 1
            stats["fields"] += len(fields)
            if g is None:
                continue
            stats["found"] += 1
            for f in fields:
                ok = abs(getattr(g, f) - t[f]) < 0.005 if f != "code" else g.code == t["code"]
                stats["correct"] += ok
                if not ok:
                    stats["flagged_wrong" if g.needs_review else "silent"] += 1
    return stats


def row(label, s):
    acc = 100 * s["correct"] / s["fields"] if s["fields"] else 0
    rec = 100 * s["found"] / s["lines"] if s["lines"] else 0
    return (f"{label:<22} field accuracy {acc:5.1f}%  line recall {rec:5.1f}%  "
            f"wrong-but-flagged {s['flagged_wrong']:>3}  SILENT errors {s['silent']:>3}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extractor", choices=["text", "llm", "auto"], default="auto")
    args = ap.parse_args()
    cases = [json.loads(p.read_text()) | {"dir": p.parent} for p in sorted((ROOT / "data" / "synthetic").glob("*/truth.json"))]
    if not cases:
        print("No synthetic data. Run: make data")
        return 2
    have_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    mode = args.extractor if args.extractor != "auto" else ("llm" if have_key else "text")
    if mode == "llm" and not have_key:
        print("ANTHROPIC_API_KEY is not set: cannot run the llm extractor.")
        return 2
    if mode == "llm":
        from extraction.llm import AnthropicExtractor
        extractor = AnthropicExtractor()
    else:
        extractor = TextLayerExtractor()
    print(f"Extractor: {mode}\n")
    ok = True
    variants = [("clean PDF", "pdf", 95.0)]
    if mode == "llm":
        variants.append(("photo", "jpg", 85.0))
    for label, ext, target in variants:
        total = {"fields": 0, "correct": 0, "lines": 0, "found": 0, "silent": 0, "flagged_wrong": 0}
        for kind in ("bill", "eob"):
            files = [(c["dir"] / (f"{kind}.pdf" if ext == "pdf" else f"{kind}_photo.jpg"), c[kind]) for c in cases]
            s = evaluate(extractor, files, kind)
            print(row(f"{label} {kind}", s))
            for k in total:
                total[k] += s[k]
        print(row(f"{label} OVERALL", total))
        acc = 100 * total["correct"] / total["fields"]
        verdict = acc >= target and total["silent"] == 0
        ok &= verdict
        print(f"  target >= {target:.0f}% and zero silent errors: {'PASS' if verdict else 'FAIL'}\n")
    if mode == "text":
        print("Photo variants were NOT evaluated: they need the vision model (set ANTHROPIC_API_KEY, "
              "rerun with --extractor llm).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
