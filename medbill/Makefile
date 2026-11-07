PY ?= python3
.PHONY: test lint eval data
test:
	$(PY) -m pytest -q
lint:
	$(PY) -m ruff check .
data:
	$(PY) scripts/generate_synthetic.py
eval: data
	$(PY) scripts/eval_audit.py
	$(PY) scripts/eval_extraction.py
