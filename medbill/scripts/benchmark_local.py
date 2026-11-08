"""Opt-in latency check using synthetic bills; writes timings, never patient documents."""
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
from llm import OllamaLLM


class TimedModel(OllamaLLM):
    def __init__(self):
        super().__init__()
        self.calls = []

    def complete_tool(self, system, user, tool):
        start = time.perf_counter()
        try:
            return super().complete_tool(system, user, tool)
        finally:
            self.calls.append({"tool": tool["name"], "seconds": round(time.perf_counter() - start, 3)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--languages", default="en,es,fr", help="Comma-separated language codes to measure")
    args = parser.parse_args()
    load_environment()
    model, settings = TimedModel(), Settings()
    corpus = json.loads((ROOT / "data/qa_eval/multilingual.json").read_text(encoding="utf-8"))
    selected = set(args.languages.split(","))
    questions = [(item["language"], item["question"]) for item in corpus if item["language"] in selected]
    if "en" in selected:
        questions.append(("en", "How much do I actually owe?"))
    raw = json.loads((settings.samples_dir / "overcharge/extraction.json").read_text())
    record = service.extract_from_bytes(service.sample_files("overcharge", settings), CachedExtractor(raw), "demo-sample")
    run_case(record.case)
    rows = []
    for expected, question in questions:
        for repeat in (False, True):
            # Mirror API lifetime: a fresh Translator per request, with a case cache when supported.
            options = {"memo": record.translation_memo} if hasattr(record, "translation_memo") else {}
            translator = service.translator_for(model, settings, **options)
            model.calls.clear()
            start = time.perf_counter()
            result = QA(translator, model).ask(record.case, question)
            row = {"language": expected, "repeat": repeat, "seconds": round(time.perf_counter() - start, 6),
                   "calls": model.calls.copy(), "verified": result.verified, "deferred": result.deferred,
                   "detected": result.language, "kind": result.kind}
            rows.append(row)
            print(json.dumps(row), flush=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"model": model.model, "results": rows}, indent=2), encoding="utf-8")
    from scripts.eval_multilingual import equivalent
    if not rows or any(not row["verified"] or row["deferred"] or not equivalent(row["detected"], row["language"]) for row in rows):
        raise SystemExit("A benchmark answer did not pass; inspect the report.")


if __name__ == "__main__":
    main()
