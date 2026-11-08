# MedBill: a three-minute demonstration

**Pitch:** Medical bills tell patients what to pay without helping them understand why. MedBill compares the bill with the insurance statement, traces potential errors to the source, and helps the patient ask for a review in their own language.

## Before presenting

- From `medbill`, run `.venv\Scripts\python.exe scripts/dev.py --check`, then `.venv\Scripts\python.exe scripts/dev.py --demo`.
- Open `http://127.0.0.1:5173`. This mode uses explicitly labelled synthetic documents, deterministic billing checks, and the committed English/Spanish/Mongolian demo translations. It makes no LLM calls.
- If the ports are occupied, append `--api-port 18080 --web-port 15173` and open `http://127.0.0.1:15173` instead. The launcher never stops unrelated services.
- For a separate live AI demonstration, start with `--local` instead, after `ollama pull qwen3:4b`. Free-form questions and new translations need the local model; do not call the offline demo a live model benchmark.
- Keep the generated evidence report and the letter download visible as the final outcome. Avoid downloading real patient documents during the presentation.

## Walkthrough

| Time | Action | What to say |
| --- | --- | --- |
| 0:00–0:20 | Open the welcome screen. | “The patient has two documents and one question: do these charges make sense? We turn those documents into a clear explanation and a next step.” |
| 0:20–0:40 | Click **Explore a sample bill**. Review the lines and select **Looks right, continue**. | “We don’t silently trust extraction. The patient can compare and correct the data before any billing checks run.” |
| 0:40–1:05 | Show the **$412** amount in question and the side-by-side **$502 bill / $90 EOB** comparison. Expand the line table. | “On this synthetic example, the documents disagree. This is an amount to ask about, not a promise of savings or a payment instruction.” |
| 1:05–1:30 | Filter **Definite**, return to **All findings**, and click **Show evidence** on the office-visit mismatch. | “Every finding has a rule and exact bill/EOB lines. The model does not decide whether something is an error.” |
| 1:30–1:55 | Expand **What if the bill were corrected?** Choose **B5**, propose **40**, and preview. | “If that patient charge changes from $247 to $40, the bill balance becomes $295 and $205 remains in question. We rerun the actual rules on a copy; the original $412 review stays unchanged.” |
| 1:55–2:20 | Click **Ask a question**, then **How much do I actually owe?** | “Answers use the case, distinguish statements from final payment, and link back to evidence. Questions the documents cannot answer are deferred.” |
| 2:20–2:45 | Open **Write the letter** and download the **evidence report**. | “The patient leaves with a concrete review request, cited findings, and highlighted source pages in one portable report.” |
| 2:45–3:00 | Conclude. | “Our next step is validating with patient advocates and native speakers, expanding licensed rule data, and improving real-document extraction. Today, the end-to-end prototype already works on reproducible synthetic cases.” |

For a shorter slot, skip the filter and chat interactions; preserve the problem, source evidence, correction preview, and downloadable outcome.

## Optional proof points

- **Language access:** go to Welcome, type `Quiero entender mi factura`, and send. The interface detects Spanish without a language picker; repeat the sample review and ask `¿Cuánto debo realmente?`. The demo uses committed draft Spanish copy. Model-based support beyond the demo languages varies in quality and latency.
- **A clean counterexample:** start over, upload a sample, and select **Clean bill**. Show **No errors found**; the app should not manufacture a dispute.
- **A cautious result:** select **Worth asking**. These items carry zero disputed dollars and are not presented as confirmed errors.
- **Human review matters:** choose **Overcharge, phone photo**. The stored extraction has an intentionally low-confidence amount. The yellow review cell is part of the workflow, not an unexplained failure.
- **Honest boundaries:** ask about future insurance coverage. The documents do not support that answer, so the app points the patient to the billing office.

## Explaining the build to judges

| Criterion | Concrete evidence to show |
| --- | --- |
| Technical difficulty | One-to-one document matching, ordered billing rules with deduplicated dollar impact, extraction confidence and bounding boxes, number-preserving translations, deep-copy scenario evaluation, and PDF evidence assembly. |
| Innovation | The correction sandbox makes the audit interactive and inspectable; language models interpret questions while deterministic code retains control over financial facts. |
| Impact | Patients and patient advocates get an explanation, source evidence, a review letter, and a portable report in one workflow. Actual savings and clinical adoption have not been measured. |
| Design | Medical visual language, clear step navigation, mobile layouts, visible certainty levels, focus management, and reduced-motion support. |
| Functionality | Use the reproducible offline path and the clean-bill counterexample. Show a real PDF download and that a preview does not modify the original review. |
| Presentation | Follow one patient story. Name the example as synthetic, explain what the AI does, and finish with a usable artifact. |

## Boundaries to state accurately

This is a prototype, not a production clinical service or a compliance certification. Some billing tables are small samples; broader CMS data and licensed code descriptions require additional work. The local text model does not read arbitrary photos; stored photo samples replay extraction, while real text PDFs and manual entry work without a vision API. Automated translation checks protect values and catch some language/repetition failures; they do not prove medical translation quality. Draft translations need native-speaker review. Cases and their translation caches stay in memory until deletion or idle expiry.
