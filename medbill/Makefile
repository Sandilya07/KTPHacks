PY ?= python3
.PHONY: test lint eval data web-test
test:
	$(PY) -m pytest -q
lint:
	$(PY) -m ruff check .
data:
	$(PY) scripts/generate_synthetic.py
eval: data
	$(PY) scripts/eval_dashboard.py
web-test:
	cd web && PY="$(PY)" npx playwright test flow
