# MedBill web app

Run the API from `medbill` and the web app from `medbill/web`:

```powershell
.venv\Scripts\python.exe -m uvicorn api.main:app_factory --factory --port 8000
npm.cmd run dev
```

Run the Python command from `medbill`; run the npm command from `medbill/web`.

The welcome screen accepts a sentence in the user's language. Send it to detect the language and translate the interface, then start the document review. Questions also detect their language automatically and update the experience when the language changes. Speech input and playback controls have been removed.

The API loads `medbill/.env` automatically. The default local configuration uses Ollama and Qwen3 4B, with no API key or hosted API calls:

```env
DEMO_MODE=0
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:4b
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Install Ollama, run `ollama pull qwen3:4b` once, and keep Ollama running (`ollama serve` if the desktop app is not running). The model download is about 2.5 GB. Restart the backend after changing `.env`. Existing process environment variables take precedence; remove a previous `$env:DEMO_MODE` override if needed.

The small model interprets the question and recent conversation; Python supplies amounts, descriptions and citations from the case. Other billing questions use a validated model answer or an explicit deferral. Local mode uses deterministic English audit explanations and letters to reduce wait times. Spanish and Mongolian interface copy uses the existing translations. Other languages use the model and may be slower or fail verification; English with a notice is the fallback.

Language support is automatic and is not limited to the two reviewed glossary files. ISO language aliases and regional/script tags are normalized, an offline detector and script checks correct common model confusions, and named target languages are passed to the model. Right-to-left scripts use the appropriate page direction. Local translations keep billing codes, amounts and dates in Python while translating the surrounding text; this also supports numbers next to Chinese/Japanese text and localized digits in questions. Interface text is translated in smaller verified batches and cached in memory by language and source copy.

The local-model question corpus passed 36 cases covering 35 languages and both Chinese scripts. Separate numeric-integrity and UI checks passed in French, Arabic, Hindi, Chinese and Japanese; see the three `local_*_report.json` files in `data/qa_eval`. Translated chat answers include expandable original English text. The offline detector's language catalog is not an allowlist: languages outside it can still use the model. Obvious wrong-language output and repetition are rejected, and translation failures are distinguished from missing bill information.

The 4B model replaces the 1.7B default because the smaller model failed several non-Latin language checks. It still runs locally without an API key. Quality varies by language and input, and a verified result means the automated language/numeric checks passed; it does not certify medical translation accuracy. Initial UI and long-document translations can take longer on CPU hardware.

Local document input supports PDFs with text. Scanned photos need manual entry in this configuration. Sample documents always use their stored extraction so all ten scenarios work without image-model calls. The Upload screen includes six additional synthetic scenarios and download links for each bill and EOB. Their `expected.json` files document the findings. Recreate the new pairs without deleting other samples using `python scripts/make_samples.py --only-new` from `medbill`.

For the optional hosted provider instead, set `LLM_PROVIDER=anthropic`, supply `ANTHROPIC_API_KEY`, and optionally set `MODEL`. Short or ambiguous language input may be misidentified, so use a full sentence.

With a model configured, questions use the bill, insurance statement, audit findings and billing definitions as context instead of relying on a fixed list of phrases. The last eight chat messages help interpret follow-up questions. Answers must pass number and citation checks before display, then use verified translation into the detected language. Missing evidence produces a clear deferral. If the answer model is unavailable, deterministic answers remain available; for example, “Why am I being overcharged?” explains the findings in demo mode too.

Offline/demo mode retains English, Spanish and Mongolian detection and cached translations. It does not provide arbitrary-language translation. Failed verification shows English with a notice. Amounts, billing codes, dates and account identifiers keep the existing placeholder verification. Interface translations also verify placeholders and template variables. Original documents and the English letter for sending remain available.

Checks:

```powershell
npm.cmd run build
# From medbill:
.venv\Scripts\python.exe -m pytest tests/test_translate.py tests/test_qa.py tests/test_api.py tests/test_i18n_letter.py -q
# From medbill/web, using a Python environment with API dependencies:
$env:PY = (Resolve-Path '../.venv/Scripts/python.exe').Path
npx.cmd playwright test
```

To exercise the real local model against synthetic data, run `.venv\Scripts\python.exe scripts/smoke_local.py` from `medbill`. You can pass a question as its argument. It checks that an answer is produced and verified; normal pytest runs never require Ollama.

The wider corpus is `data/qa_eval/multilingual.json`. Run `python scripts/eval_multilingual.py --stage qa --resume` from `medbill` to continue the real-model checks. The result is saved incrementally in `data/qa_eval/local_multilingual_report.json`. The `numbers` and `interface` stages exercise numeric preservation and small UI translation batches; use a separate `--output` file and optionally select codes with `--languages fr,ar,hi,zh,ja`. These are functional smoke checks on one synthetic question per language, not a human translation review.
