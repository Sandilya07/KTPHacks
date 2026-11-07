# MedBill web app

Run the API from `medbill` and the web app from `medbill/web`:

```powershell
.venv\Scripts\python.exe -m uvicorn api.main:app_factory --factory --port 8000
npm.cmd run dev
```

Run the Python command from `medbill`; run the npm command from `medbill/web`.

The welcome screen accepts a sentence in the user's language. Send it to detect the language and translate the interface, then start the document review. Questions also detect their language automatically and update the experience when the language changes. Speech input and playback controls have been removed.

Live detection and translation use the existing configured model (`ANTHROPIC_API_KEY`, optional `MODEL`, and `DEMO_MODE=0` in the API process environment). Languages do not require a glossary file; existing reviewed glossaries still guide Spanish and Mongolian translations. Short or ambiguous text may be misidentified, so use a full sentence.

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
