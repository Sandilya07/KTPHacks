#!/usr/bin/env python3
"""Lists every English sentence (masked, numbers replaced by tokens) that the demo cases show a user:
finding explanations, answers to the suggested questions, and the dispute letter. Each needs a translation
in i18n/demo_cache_<lang>.json for DEMO_MODE to work offline in that language.

  python scripts/dump_demo_strings.py          # print the masked strings
  python scripts/dump_demo_strings.py --check  # exit 1 if any are missing from the caches"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from audit.cms_data import load_cms_data, sample_cms_data, set_cms_data
from audit.engine import run_case
from audit.models import Case
from explain.explainer import Explainer
from explain.letter import build_letter
from extraction.cached import CachedExtractor
from extraction.pipeline import extract_case
from i18n.demo_cache import load_demo_cache
from i18n.glossary import supported_languages
from i18n.letter import english_segment_parts
from i18n.placeholders import protect
from i18n.qa import SUGGESTED

SAMPLES = ["overcharge", "overcharge_photo", "clean", "ask"]


def sample_case(name: str) -> Case:
    d = ROOT / "data" / "samples" / name
    raw = json.loads((d / "extraction.json").read_text())
    files = {k: next(p for p in d.iterdir() if p.stem == k and p.suffix != ".json") for k in ("bill", "eob")}
    case = extract_case(files["bill"], files["eob"], CachedExtractor(raw)).case
    case.confirmed = True
    return run_case(case)


def collect() -> dict[str, list[str]]:
    """masked English sentence -> where it is used. Covers the small sample rule tables and, when the CMS
    files are downloaded, the real tables too (they can add findings such as price outliers)."""
    out: dict[str, list[str]] = {}

    def add(text: str, where: str) -> None:
        out.setdefault(protect(text).masked, []).append(where)

    configs = [sample_cms_data()]
    real = load_cms_data()
    if real.source == "cms":
        configs.append(real)
    for cms in configs:
        set_cms_data(cms)
        for name in SAMPLES:
            case = sample_case(name)
            for e in Explainer(None).explain_all(case):
                for k in ("headline", "what_happened", "why_it_matters", "what_you_can_do"):
                    add(getattr(e, k), f"{name}: explanation {k}")
            for q in SUGGESTED:
                for part in answer_parts(case, q):
                    add(part, f"{name}: answer to '{q}'")
            for section, parts in english_segment_parts(build_letter(case, today=date(2026, 1, 1))):
                for part in parts:
                    add(part, f"{name}: letter {section}")
    set_cms_data(None)
    return out


def answer_parts(case: Case, question: str) -> list[str]:
    from i18n.qa import build_answer, detect_intent_en
    intent = detect_intent_en(question)
    ans = build_answer(case, intent, question) if intent else None
    return (ans.parts or []) if ans else []


def main() -> int:
    needed = collect()
    caches = load_demo_cache()
    if "--check" in sys.argv:
        bad = 0
        for lang in supported_languages():
            missing = [m for m in needed if m not in caches[lang]]
            print(f"{lang}: {len(needed) - len(missing)}/{len(needed)} covered")
            bad += len(missing)
        return 1 if bad else 0
    print(json.dumps({m: "" for m in needed}, indent=1, ensure_ascii=False))
    print(f"\n{len(needed)} strings", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
