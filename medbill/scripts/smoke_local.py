"""Opt-in real local-model smoke check against synthetic sample data (never runs in pytest)."""
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
from llm import OllamaLLM, llm_from_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", default="What is 80053?")
    args = parser.parse_args()
    load_environment()
    model = llm_from_env()
    if not isinstance(model, OllamaLLM):
        raise SystemExit("Set LLM_PROVIDER=ollama in medbill/.env first.")
    settings = Settings()
    raw = json.loads((settings.samples_dir / "overcharge" / "extraction.json").read_text())
    record = service.extract_from_bytes(service.sample_files("overcharge", settings), CachedExtractor(raw), "demo-sample")
    case = run_case(record.case)
    start = time.monotonic()
    answer = QA(service.translator_for(model, settings), model).ask(case, args.question)
    print(json.dumps({"language": answer.language, "kind": answer.kind, "verified": answer.verified,
                      "deferred": answer.deferred, "seconds": round(time.monotonic() - start, 1),
                      "answer": answer.answer, "citations": answer.citations}, ensure_ascii=True), flush=True)
    if answer.deferred or not answer.verified:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
