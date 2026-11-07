#!/usr/bin/env python3
"""Run 20 findings through the explainer; count validator failures, retries and template fallbacks,
and confirm no accepted text contains a number or code absent from its finding.

--llm live      : the real model (needs ANTHROPIC_API_KEY)
--llm simulated : offline stand-in that writes plausible text but deliberately invents numbers and
                  banned words on a fixed schedule, to prove the validator catches them. This tests
                  the safety net, NOT model quality.
--llm none      : templates only
Default: live when a key is set, otherwise simulated."""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from audit.engine import run_case
from audit.models import Bill, Case, Eob
from explain.explainer import Explainer
from explain.templates import fallback_explanation
from explain.validator import facts_for_finding, validate_text


def _case(t) -> Case:
    return Case(bill=Bill.model_validate(t["bill"]), eob=Eob.model_validate(t["eob"]))


def gather(n: int = 20) -> list[tuple[Case, object]]:
    truths = [json.loads(p.read_text()) for p in sorted((ROOT / "data" / "synthetic").glob("*/truth.json"))]
    cases = [run_case(_case(t)) for t in truths]
    variants = []
    for i, t in enumerate(t for t in truths if t["kind"] == "seeded"):
        v = copy.deepcopy(t)
        if i % 4 == 0:
            v["bill"]["lines"][0]["billed"] *= 9  # price outlier
        elif i % 4 == 1:
            v["eob"]["lines"] = v["eob"]["lines"][:-1]  # missing EOB line
        elif i % 4 == 2:
            v["bill"]["patient_balance"] += 25.0  # balance arithmetic
        else:
            v["bill"]["lines"][-1]["modifiers"] = ["76"]  # repeat modifier / modifier-based downgrades
        variants.append(v)
    cases += [run_case(_case(t)) for t in variants]
    pairs = [(c, f) for c in cases for f in c.findings]
    seen, out = set(), []
    for c, f in pairs:  # prefer one finding per (rule, tier) first for coverage, then fill up
        if (f.rule, f.tier) not in seen:
            seen.add((f.rule, f.tier))
            out.append((c, f))
    out += [p for p in pairs if p not in out]
    return out[:n]


class SimulatedLLM:
    """Offline stand-in. Every 4th first attempt invents a number, every 8th keeps doing it (forcing the
    template fallback), every 7th uses a banned word. Otherwise returns the template text unchanged."""

    def __init__(self, case_finding_pairs):
        self.pairs, self.i, self.attempt = case_finding_pairs, -1, 0
        self.by_prompt: dict[str, tuple] = {}

    def complete_tool(self, system, user, tool):
        for c, f in self.pairs:
            if f.evidence in user and f.id in {x.id for x in c.findings} and f.rule in user:
                case, finding = c, f
                break
        else:
            raise RuntimeError("unknown finding")
        if "rejected" not in user:
            self.i += 1
            self.attempt = 0
        else:
            self.attempt += 1
        text = fallback_explanation(case, finding)
        text["what_happened"] += " This was easy to miss."
        if self.i % 4 == 3 and (self.attempt == 0 or self.i % 8 == 7):
            text["why_it_matters"] += " You may be owed $1,234.56 back."
        if self.i % 7 == 6 and self.attempt == 0:
            text["headline"] = "This looks like fraud"
        return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", choices=["live", "simulated", "none"], default=None)
    args = ap.parse_args()
    mode = args.llm or ("live" if os.environ.get("ANTHROPIC_API_KEY") else "simulated")
    pairs = gather()
    if len(pairs) < 20:
        print("Need data/synthetic (run: make data)")
        return 2
    if mode == "live":
        from llm import AnthropicLLM
        llm = AnthropicLLM()
    elif mode == "simulated":
        llm = SimulatedLLM(pairs)
    else:
        llm = None
    ex = Explainer(llm)
    leaks = 0
    for case, f in pairs:
        e = ex.explain(case, f)
        if not validate_text(e.text(), facts_for_finding(case, f), f.tier).ok:
            leaks += 1
    s = ex.stats
    print(f"LLM mode: {mode}{'  (offline stand-in: tests the validator, not model quality)' if mode == 'simulated' else ''}")
    print(f"Findings explained        : {s.total}  ({len({(f.rule, f.tier) for _, f in pairs})} distinct rule/tier types)")
    print(f"Accepted from the LLM     : {s.llm_ok}")
    print(f"Validator rejections      : {s.validator_failures}")
    print(f"Template fallbacks        : {s.fallbacks}  ({100 * s.fallback_rate:.0f}%)")
    print(f"Accepted text with a number/code/banned word not in its finding: {leaks}")
    print("PASS" if leaks == 0 else "FAIL")
    return 0 if leaks == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
