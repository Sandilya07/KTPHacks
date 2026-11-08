"""Opt-in evaluation of real local-model detection and Q&A on synthetic billing questions."""
from pathlib import Path
import argparse
import json
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api import service
from api.settings import Settings, load_environment
from audit.engine import run_case
from extraction.cached import CachedExtractor
from i18n.qa import QA
from llm import llm_from_env


def equivalent(a, b):
    if b.split("-")[0] == "zh":
        from langcodes import Language
        return Language.get(a).maximize().script == Language.get(b).maximize().script
    aliases = {"tl": "fil", "cmn": "zh"}
    return aliases.get(a.split("-")[0], a.split("-")[0]) == aliases.get(b.split("-")[0], b.split("-")[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["detect", "qa", "numbers", "interface"], default="qa")
    parser.add_argument("--languages", default="")
    parser.add_argument("--output", default="data/qa_eval/local_multilingual_report.json")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rerun", action="store_true", help="Rerun selected cases even if they previously passed.")
    args = parser.parse_args()
    load_environment()
    model, settings = llm_from_env(), Settings()
    translator = service.translator_for(model, settings)
    raw = json.loads((settings.samples_dir / "overcharge" / "extraction.json").read_text())
    record = service.extract_from_bytes(service.sample_files("overcharge", settings), CachedExtractor(raw), "demo-sample")
    case = run_case(record.case)
    corpus = json.loads((ROOT / "data/qa_eval/multilingual.json").read_text(encoding="utf-8"))
    selected = set(args.languages.split(",")) if args.languages else None
    results = []
    if args.resume and (ROOT / args.output).exists():
        previous = json.loads((ROOT / args.output).read_text(encoding="utf-8"))
        if previous.get("model") != getattr(model, "model", None) or previous.get("stage") != args.stage:
            raise SystemExit("Cannot resume a report from a different model or stage.")
        results = previous["results"]
    # Keep successful measurements; rerun failures after a fix.
    results = [result for result in results if result["passed"]]
    if args.rerun:
        results = [result for result in results if selected and result["expected"] not in selected]
    completed = {result["expected"] for result in results}
    for item in corpus:
        if selected and item["language"] not in selected:
            continue
        if item["language"] in completed:
            continue
        start = time.monotonic()
        result = {"expected": item["language"], "question": item["question"]}
        try:
            if args.stage == "detect":
                result["detected"] = translator.detect_language(item["question"])
                result["passed"] = equivalent(result["detected"], item["language"])
            elif args.stage == "qa":
                answer = QA(translator, model).ask(case, item["question"])
                result.update(detected=answer.language, answer=answer.answer, kind=answer.kind,
                              english_question=answer.english_question, verified=answer.verified,
                              deferred=answer.deferred, notice=answer.notice)
                result["passed"] = (equivalent(answer.language, item["language"]) and answer.verified
                                    and not answer.deferred and "80053" in answer.answer
                                    and (item["language"] == "en" or answer.answer != answer.answer_en))
            elif args.stage == "numbers":
                from i18n.placeholders import same_values
                lang = translator.detect_language(item["question"])
                original = "Line B2: code 80053 on 2024-03-05 costs $95.00."
                answer = translator.translate(original, lang)
                result.update(detected=lang, answer=answer.text, verified=answer.verified)
                result["passed"] = (equivalent(lang, item["language"]) and answer.verified and same_values(original, answer.text)
                                    and (item["language"] == "en" or answer.text.strip() != original))
            else:
                from i18n.interface import translate_interface
                lang = translator.detect_language(item["question"])
                strings = {"title": "Ask about your bill", "send": "Send", "total": "Amount in question: {amount}"}
                answer = translate_interface(strings, translator, lang)
                result.update(detected=lang, answer=answer)
                result["passed"] = (equivalent(lang, item["language"]) and set(answer) == set(strings)
                                    and "{amount}" in answer["total"] and answer["title"] != strings["title"])
        except Exception as exc:
            result.update(passed=False, error=str(exc))
        result["seconds"] = round(time.monotonic() - start, 1)
        results.append(result)
        (ROOT / args.output).write_text(json.dumps({"stage": args.stage, "model": getattr(model, "model", None),
                                                   "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k not in ("question", "answer")}), flush=True)
    print(f"Passed {sum(r['passed'] for r in results)}/{len(results)}", flush=True)
    if any(not result["passed"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
