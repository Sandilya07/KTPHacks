#!/usr/bin/env python3
"""`make eval`: one table with the numbers that go on the results slide.

Every row says how it was measured (live model, offline stand-in, or not measured) so no number can be
mistaken for something it is not."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pct(a: float, b: float) -> str:
    return f"{100 * a / b:.0f}%" if b else "n/a"


def main() -> int:
    live = bool(os.environ.get("ANTHROPIC_API_KEY"))
    rows: list[tuple[str, str, str, str]] = []  # metric, result, how measured, target met
    audit = load("eval_audit").compute()
    ext = load("eval_extraction").compute()
    expl = load("eval_explainer").compute()
    i18n = load("eval_i18n").compute()
    if audit is None or ext is None or expl is None:
        print("No synthetic data. Run: make data")
        return 2
    ok = True

    def add(metric, result, how, passed):
        nonlocal ok
        rows.append((metric, result, how, {True: "yes", False: "NO", None: "not measured"}[passed]))
        ok &= passed is not False

    if "error" in ext:
        add("Extraction accuracy", "-", ext["error"], None)
    else:
        for label, v in ext["variants"].items():
            t = v["total"]
            how = "vision model" if ext["mode"] == "llm" else "text-layer extractor (our own PDFs)"
            add(f"Extraction field accuracy, {label}", f"{v['accuracy']:.1f}%  ({t['silent']} silent errors)", how, v["pass"])
        if "photo" not in ext["variants"]:
            add("Extraction field accuracy, photo", "-", "needs ANTHROPIC_API_KEY", None)
    add("Seeded-error recall", f"{audit['found']}/{audit['total']} ({pct(audit['found'], audit['total'])})",
        f"rules engine, {audit['cms']}", audit["found"] == audit["total"])
    add("Dollar impact exact", f"{audit['impact_ok']}/{audit['found']}", "rules engine", audit["impact_ok"] == audit["found"])
    add("False positives on clean bills (definite/likely)", f"{audit['fp_strong']} of {audit['clean']} bills",
        "rules engine", audit["fp_strong"] == 0)
    how = "live model" if expl["mode"] == "live" else "offline stand-in (tests the validator)"
    add("Explainer: validator fallback rate", f"{100 * expl['fallback_rate']:.0f}%  ({expl['fallbacks']} of {expl['total']})", how, None if expl["mode"] != "live" else True)
    add("Explainer: invented numbers/codes/banned words accepted", str(expl["leaks"]), how, expl["leaks"] == 0)
    how = "live model" if i18n["mode"] == "live" else "offline stand-in (tests the pipeline)"
    for m in i18n["langs"].values():
        add(f"Translation number integrity, {m['name']}", f"{m['integrity']}/{m['verified']} ({pct(m['integrity'], m['verified'])})", how, m["integrity"] == m["verified"])
        add(f"Unanswerable questions deferred, {m['name']}", f"{m['defer_ok']}/{m['defer_n']}", how, m["defer_ok"] == m["defer_n"])
        add(f"Offline keyword routing (no model), {m['name']}", f"{m['offline']}/{m['n']}", "keyword hints in the glossary file", None)
    w = [max(len(r[i]) for r in rows + [("Metric", "Result", "How it was measured", "Target met")]) for i in range(4)]
    line = lambda r: "  ".join(c.ljust(w[i]) for i, c in enumerate(r))
    print(line(("Metric", "Result", "How it was measured", "Target met")))
    print("  ".join("-" * x for x in w))
    for r in rows:
        print(line(r))
    print()
    print("Mode:", "ANTHROPIC_API_KEY set: live paths used where marked" if live else "no API key: model rows use offline stand-ins or are not measured")
    print("Native-speaker review of Spanish and Mongolian text: NOT done.")
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
