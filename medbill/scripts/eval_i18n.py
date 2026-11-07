#!/usr/bin/env python3
"""4F. Multilingual evaluation: 20 questions per language (15 answerable, 5 that must be deferred).

Measures: answers grounded (every number in the answer is in the case data), number integrity after the
translation round trip, glossary compliance, correct deferral, intent routing, and offline keyword routing.

--llm live      : the real model (needs ANTHROPIC_API_KEY)
--llm simulated : offline stand-in that 'translates' by tagging text and substituting glossary terms, and
                  injects number corruption on a fixed schedule to prove the integrity layer catches it.
                  It tests the pipeline, NOT translation quality. No native speaker has reviewed the output."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from audit.engine import run_case
from audit.models import Bill, Case, Eob
from explain.validator import validate_text
from i18n.glossary import TERM_PATTERNS, load_glossary, supported_languages
from i18n.placeholders import same_values
from i18n.qa import QA, detect_intent_native, qa_facts
from i18n.translate import Translator


class SimulatedLLM:
    def __init__(self, lang: str, questions: list[dict], corrupt_every: int = 4):
        self.lang, self.g = lang, load_glossary(lang)
        self.en_for = {q["q"]: q["en"] for q in questions}
        self.corrupt_every, self.n_translate = corrupt_every, 0
        self.injected = 0

    def complete_tool(self, system, user, tool):
        if tool["name"] == "to_english":
            if user in self.en_for:  # a question
                return {"english": self.en_for[user]}
            out = user.removeprefix(f"[{self.lang}] ")  # back-translation: undo the glossary substitution
            for t, e in self.g.terms.items():
                out = out.replace(e["pinned"], t)
            return {"english": out}
        text = user.split("\n\n")[0]
        for term, pat in TERM_PATTERNS.items():
            if term in self.g.terms:
                text = re.sub(pat, self.g.terms[term]["pinned"], text, flags=re.IGNORECASE)
        self.n_translate += 1
        if "rejected" not in user and self.n_translate % self.corrupt_every == 0 and "[[" in text:
            self.injected += 1
            text = re.sub(r"\[\[[A-Z]+_\d+\]\]", "", text, count=1) if self.injected % 2 else text + " 7"
        return {"translation": f"[{self.lang}] {text}"}


def compute(choice: str | None = None) -> dict:
    mode = choice or ("live" if os.environ.get("ANTHROPIC_API_KEY") else "simulated")
    d = json.loads((ROOT / "data" / "overcharge.json").read_text())
    case = run_case(Case(bill=Bill.model_validate(d["bill"]), eob=Eob.model_validate(d["eob"])))
    facts = qa_facts(case)
    out: dict = {"mode": mode, "langs": {}}
    for lang in [x for x in supported_languages() if (ROOT / "data" / "qa_eval" / f"{x}.json").exists()]:
        qs = json.loads((ROOT / "data" / "qa_eval" / f"{lang}.json").read_text(encoding="utf-8"))
        if mode == "live":
            from llm import AnthropicLLM
            llm = AnthropicLLM()
        else:
            llm = SimulatedLLM(lang, qs)
        qa = QA(Translator(llm))
        g = load_glossary(lang)
        keys = ["n", "grounded", "answered", "integrity", "verified", "gloss", "gloss_n", "defer_ok", "defer_n", "intent", "refs", "refs_n", "offline", "fell_back"]
        m = dict.fromkeys(keys, 0)
        for q in qs:
            r = qa.ask(case, q["q"], lang)
            m["n"] += 1
            m["intent"] += (r.kind == q["intent"])
            offline = detect_intent_native(q["q"], lang)
            m["offline"] += ((offline or "defer") == q["intent"] or (offline is None and q["intent"] == "defer"))
            if q["answerable"]:
                m["answered"] += 1
                m["grounded"] += (not r.deferred and validate_text(r.answer_en, facts).ok)
                if r.verified:
                    m["verified"] += 1
                    m["integrity"] += same_values(r.answer_en, r.answer)
                    if g.terms_in(r.answer_en):
                        m["gloss_n"] += 1
                        m["gloss"] += not g.check(r.answer_en, r.answer)
                else:
                    m["fell_back"] += 1
                if q["refs"]:
                    m["refs_n"] += 1
                    m["refs"] += set(q["refs"]) <= set(r.citations)
            else:
                m["defer_n"] += 1
                m["defer_ok"] += (r.deferred and r.answer == g.phrases["defer"])
        m["name"], m["reviewed"] = g.name, g.reviewed
        m["injected"] = llm.injected if mode == "simulated" else None
        m["pass"] = m["integrity"] == m["verified"] and m["defer_ok"] == m["defer_n"] and m["grounded"] == m["answered"]
        out["langs"][lang] = m
    out["pass"] = all(v["pass"] for v in out["langs"].values())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", choices=["live", "simulated"], default=None)
    r = compute(ap.parse_args().llm)
    print(f"LLM mode: {r['mode']}" + ("  (offline stand-in: tests the pipeline, not translation quality)" if r["mode"] == "simulated" else ""))
    pct = lambda a, b: f"{a}/{b}" + (f" ({100 * a // b}%)" if b else "")
    for lang, m in r["langs"].items():
        print(f"\n== {lang} ({m['name']})  glossary reviewed by native speaker: {m['reviewed']}")
        print(f"  intent routed correctly (with model)  : {pct(m['intent'], m['n'])}")
        print(f"  offline keyword routing (no model)    : {pct(m['offline'], m['n'])}")
        print(f"  answers grounded in case data         : {pct(m['grounded'], m['answered'])}")
        print(f"  expected citations present            : {pct(m['refs'], m['refs_n'])}")
        print(f"  verified translations / shown in English with notice: {m['verified']} / {m['fell_back']}")
        print(f"  number integrity after round trip     : {pct(m['integrity'], m['verified'])}   <- hard requirement: 100%")
        print(f"  glossary compliance                   : {pct(m['gloss'], m['gloss_n'])}")
        print(f"  unanswerable questions deferred       : {pct(m['defer_ok'], m['defer_n'])}")
        if m["injected"] is not None:
            print(f"  corruptions injected into translations: {m['injected']} (none may reach the user)")
    print("\n" + ("PASS" if r["pass"] else "FAIL"))
    print("Native-speaker spot check: NOT done (drafts need review by a Spanish and a Mongolian speaker).")
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
