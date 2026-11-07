# MedBill Auditor

Multilingual medical bill auditor built for KTP Hackathon. Upload an itemized bill and an EOB, get flagged
errors with evidence, ask questions in your own language, and generate a dispute letter.

> Informational only. Not legal or medical advice. **Synthetic data only: never use real patient information.**

**Status:** Phases 1 to 3 done; Phase 4 (multilingual) in progress. Phases 5 (API and UI) and 6 (demo and pitch)
are next. This README is updated as each part lands.

## Principles

1. **The LLM never decides whether something is an error.** A deterministic rules engine does. LLMs only extract
   text into fields, explain findings, and translate explanations.
2. Every finding carries its source: rule, code pair or limit used, and the bill and EOB line ids.
3. Three confidence tiers with different wording: `definite`, `likely`, `ask`. Nothing is ever called fraud or illegal.
4. **Numbers are sacred.** Amounts, codes, dates and account numbers are swapped for placeholder tokens before
   translation, restored afterwards, and verified.
5. Grounded answers only; if the case data cannot answer, the app says so and points to the billing office.
6. Extraction is never silently trusted: low-confidence lines are flagged and the user confirms before any audit.
7. CPT descriptions belong to the AMA, so we use code numbers plus our own plain-language notes.
8. Privacy by default: cases live in memory only.

## What is built

| Phase | What | Where |
|---|---|---|
| 1 | Deterministic audit core | `medbill/audit/` |
| 2 | Pydantic models, rule registry, CMS data loaders, extraction pipeline, synthetic data and evals | `audit/`, `extraction/`, `scripts/` |
| 3 | Explainer with validator and template fallback, dispute letter (text and PDF) | `explain/` |
| 4 (partial) | Number-integrity placeholder layer, per-language glossaries (Spanish, Mongolian), translator with token/glossary checks and a back-translation check, offline translation cache, grounded multilingual Q&A (intent routing, case-only retrieval with citations, deferral and medical/legal redirects) | `i18n/` |

Rules (one file each in `audit/rules/`, auto-registered): duplicate charge, unbundling (NCCI), excess units (MUE),
EOB mismatch and balance billing, missing EOB line, price outlier (Medicare fee schedule, always `ask`), balance arithmetic.

## Setup

Requires Python 3.11 or newer.

```bash
cd medbill
python3.12 -m venv .venv && source .venv/bin/activate
pip install pydantic pymupdf pillow numpy anthropic reportlab pytest ruff
cp .env.example .env   # optional: ANTHROPIC_API_KEY=..., MODEL=...
make test
```

## Environment variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables live model paths (extraction, explanations, translation). Without it everything falls back to deterministic code. |
| `MODEL` | Model string for all calls (default `claude-sonnet-5-5`). |
| `PRICE_OUTLIER_MULTIPLE` | Price-outlier threshold over the Medicare fee schedule (default `5`). |
| `CMS_FILES_DIR` | Where downloaded CMS files live (default `audit/cms_data/files`). |

## Make targets (run from `medbill/`, pass `PY=.venv/bin/python` if needed)

| Target | Does |
|---|---|
| `make test` | Unit tests (no network; LLM calls are mocked) |
| `make lint` | ruff |
| `make data` | Generate 20 synthetic bills and EOBs (PDF and phone-photo JPEG) with ground truth into `data/synthetic/` |
| `make eval` | Run the evaluation scripts |

## CMS data and licensing

`python scripts/fetch_cms_data.py` downloads the pinned quarter (`audit/cms_data/config.json`) of the MUE tables
and Medicare Physician Fee Schedule, and records source URLs and dates in `audit/cms_data/manifest.json`.

**The NCCI procedure-to-procedure files are behind an AMA (CPT) license click-through on cms.gov.** The script will
not accept that license for you. Read it on the CMS page, then either download the files into
`audit/cms_data/files/ncci_practitioner/` yourself or re-run with `--accept-ama-license`. Until then, unbundling
uses a small **sample** pair table, and the loader says so (`parts["ncci"] == "sample"`).

HCPCS Level II, NCCI, MUE and the fee schedule are public CMS data. CPT code descriptions are AMA property and are
not redistributed here.

## Evaluation (offline results)

| Check | Result |
|---|---|
| Seeded error recall, 10 bills | 10/10, dollar impact exact |
| False positives (definite or likely) on 10 clean bills | 0 |
| Clean-PDF extraction (text-layer extractor) | 100% field accuracy |
| Photo extraction | **not measured** (needs `ANTHROPIC_API_KEY` and the vision model) |
| Explainer validator, 20 findings, simulated LLM | 0 accepted texts with an invented number, code or banned word; template fallback fires on a fixed schedule to prove the safety net |

Q&A: questions are translated to English (numbers placeholdered), routed to one of six supported answer types or a glossary-term definition, and answered from the case data only. Anything else, including coverage and personal-plan questions ("will my insurance cover...", "what is my deductible"), gets a fixed deferral phrase pointing to the billing office; medical and legal questions get a fixed redirect. Without a model, Spanish and Mongolian questions are still routed by keyword hints in the glossary files, and the answer is shown in English with a notice.

Translation safety (unit-tested with deliberately corrupted numbers): the model only sees placeholder tokens, never raw amounts, codes or dates; dropped, duplicated, invented or mangled tokens and stray digits are rejected, then a back-translation to English must carry the same multiset of numbers and codes. On failure it retries once, then shows the English text with a notice. Known limit: two amounts swapped in position keep the same multiset, so that case is not detectable.

Honest caveats: the clean-PDF number comes from PDFs our own generator made. The explainer eval uses an offline
stand-in unless `ANTHROPIC_API_KEY` is set, so it tests the validator, not model quality. Spanish and Mongolian
glossary and phrase files are **drafts that need review by a native speaker**.
