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


def compute(extractor_choice: str = "auto") -> dict | None:
    cases = [json.loads(p.read_text()) | {"dir": p.parent} for p in sorted((ROOT / "data" / "synthetic").glob("*/truth.json"))]
    if not cases:
        return None
    have_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    mode = extractor_choice if extractor_choice != "auto" else ("llm" if have_key else "text")
    if mode == "llm" and not have_key:
        return {"error": "ANTHROPIC_API_KEY is not set: cannot run the llm extractor."}
    if mode == "llm":
        from extraction.llm import AnthropicExtractor
        extractor = AnthropicExtractor()
    else:
        extractor = TextLayerExtractor()
    out: dict = {"mode": mode, "variants": {}}
    variants = [("clean PDF", "pdf", 95.0)] + ([("photo", "jpg", 85.0)] if mode == "llm" else [])
    for label, ext, target in variants:
        total = {"fields": 0, "correct": 0, "lines": 0, "found": 0, "silent": 0, "flagged_wrong": 0}
        per = {}
        for kind in ("bill", "eob"):
            files = [(c["dir"] / (f"{kind}.pdf" if ext == "pdf" else f"{kind}_photo.jpg"), c[kind]) for c in cases]
            per[kind] = evaluate(extractor, files, kind)
            for k in total:
                total[k] += per[kind][k]
        acc = 100 * total["correct"] / total["fields"]
        out["variants"][label] = {"per": per, "total": total, "accuracy": acc, "target": target,
                                  "pass": acc >= target and total["silent"] == 0}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extractor", choices=["text", "llm", "auto"], default="auto")
    r = compute(ap.parse_args().extractor)
    if r is None:
        print("No synthetic data. Run: make data")
        return 2
    if "error" in r:
        print(r["error"])
        return 2
    print(f"Extractor: {r['mode']}\n")
    for label, v in r["variants"].items():
        for kind, st in v["per"].items():
            print(row(f"{label} {kind}", st))
        print(row(f"{label} OVERALL", v["total"]))
        print(f"  target >= {v['target']:.0f}% and zero silent errors: {'PASS' if v['pass'] else 'FAIL'}\n")
    if r["mode"] == "text":
        print("Photo variants were NOT evaluated: they need the vision model (set ANTHROPIC_API_KEY, "
              "rerun with --extractor llm).")
    return 0 if all(v["pass"] for v in r["variants"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
