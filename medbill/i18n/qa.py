"""4C. Grounded Q&A. Answers come only from the case: findings, bill lines, EOB lines and glossary notes.

Pipeline: question -> English (numbers placeholdered) -> intent -> deterministic English answer built from
the retrieved case data with citations -> optional LLM rephrasing (validated, falls back) -> the 3A
validator -> translated through the 4B layer. Anything the data cannot answer gets a fixed deferral phrase
from the language's glossary file. Medical and legal questions get a fixed redirect. Insurance coverage
rules that are not in the case data are never speculated about."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from audit.models import Case, Finding
from explain.templates import code_note, fallback_explanation, money
from explain.validator import BANNED, CODE_RE, LINE_RE, Facts, facts_for_case, validate_text
from llm import LLMClient

from .glossary import TERM_PATTERNS, load_glossary
from .translate import Translation, Translator

DEFINITIONS: dict[str, str] = json.loads((Path(__file__).parent / "definitions_en.json").read_text())
DEFER_EN = "Your bill and the documents for this case do not show that information. We suggest asking the billing office."
REDIRECT_EN = {
    "medical": "We cannot give medical advice. For questions about your health or treatment, please talk to your doctor.",
    "legal": "We cannot give legal advice. If you need legal help, please talk to a lawyer or a patient advocate.",
}
SUGGESTED = ["What does this charge mean?", "Why was I charged twice?", "How much do I actually owe?",
             "What should I say when I call billing?", "What is an EOB?", "What happens next?"]

# Checked in this order; the first match wins. "defer" intents are recognised on purpose so we never guess.
INTENTS: list[tuple[str, str]] = [
    ("medical", r"\b(diagnos\w*|medications?|medicine|treatments?|symptoms?|side effects?|dosage|should i (take|stop))\b"),
    ("legal", r"\b(lawyer|attorney|sue|suing|lawsuit|legal(ly)?|court|my rights|statute|illegal)\b"),
    ("defer", r"\b(cover|covers|covered|coverage)\b|\bwill (my )?insurance\b|\b(my|our) (deductible|copay|coinsurance|policy|premium|plan|out-of-pocket)\b"),
    ("what_is_eob", r"\beobs?\b|explanations? of benefits"),
    ("charged_twice", r"\b(twice|two times|double|duplicate[sd]?|again)\b"),
    ("how_much_owe", r"how much.*\b(owe|pay)\b|\bamount (due|owed)\b|\bmy balance\b|\btotal (due|owed|balance)\b|\bwhat do i owe\b"),
    ("what_to_say", r"what (should|do|can) i say|what to say|\bcall(ing)? (the )?(billing|office)|phone call|\bscript\b"),
    ("what_happens_next", r"what happens next|next steps?|what (do i do|should i do) next|what now|then what"),
    ("define_term", r"^\s*(what|define)\b.*"),  # refined below: needs a glossary term
    ("charge_meaning", r"\b(mean|means|explain)\b|what (is|does).*\b(charge|code|line|bill)\b|\b(charge|code|line)\b.*\b(for|about)\b"),
]
NATIVE_ORDER = ["medical", "legal", "coverage", "what_is_eob", "charged_twice", "how_much_owe", "what_to_say",
                "what_happens_next", "charge_meaning"]


def detect_language(text: str) -> str:
    """Best-effort offline language guess among the supported ones: Cyrillic -> mn, Spanish markers -> es."""
    letters = [c for c in text if c.isalpha()]
    if letters and sum("Ѐ" <= c <= "ӿ" for c in letters) / len(letters) > 0.4:
        return "mn"
    if re.search(r"[¿¡ñáéíóú]|\b(el|la|los|las|de|que|qué|mi|mis|factura|cobro|cobraron|cuánto|cuanto|por)\b", text.lower()):
        return "es"
    return "en"


def detect_intent_en(q: str) -> str | None:
    low = q.lower()
    for name, pat in INTENTS:
        if not re.search(pat, low):
            continue
        if name == "define_term":
            if not re.search(r"\bmy\b", low) and any(re.search(p, q, re.IGNORECASE) for p in TERM_PATTERNS.values()):
                return name
            continue
        return name
    return None


def detect_intent_native(q: str, lang: str) -> str | None:
    hints = load_glossary(lang).hints
    low = q.lower()
    for name in NATIVE_ORDER:
        if any(h in low for h in hints.get(name if name != "coverage" else "coverage", [])):
            return "defer" if name == "coverage" else name
    return None


@dataclass
class Answer:
    text_en: str
    citations: list[str] = field(default_factory=list)
    kind: str = ""
    deferred: bool = False
    # The same text as reusable sentences. Translating sentence by sentence means a human-written
    # translation (DEMO_MODE cache) can be reused for any case that produces the same sentences.
    parts: list[str] | None = None

    @classmethod
    def of(cls, parts: list[str], citations: list[str], kind: str) -> Answer:
        return cls(" ".join(parts), citations, kind, parts=parts)


@dataclass
class QAResult:
    answer: str  # in the user's language when verified, else English with a notice
    language: str
    kind: str
    citations: list[str]
    deferred: bool
    english_question: str | None = None
    answer_en: str = ""
    notice: str = ""
    verified: bool = True


def qa_facts(case: Case) -> Facts:
    facts = facts_for_case(case)
    facts.absorb(f"{case.bill.account_number} {case.bill.patient_balance:.2f} {case.eob.total_patient_responsibility:.2f}")
    for line in case.bill.lines + case.eob.lines:
        facts.absorb(" ".join(str(v) for v in line.model_dump(exclude={"source", "confidence"}).values()))
    return facts


# ---- deterministic answer builders ------------------------------------------------------------
def _expl_parts(case: Case, f: Finding) -> list[str]:
    e = fallback_explanation(case, f)
    return [e["what_happened"], e["why_it_matters"]]


def _line_parts(case: Case, line) -> tuple[list[str], list[str]]:
    from audit.matching import match_lines
    eob = match_lines(case).pairs.get(line.id)
    parts = [f"Code {line.code}: {code_note(case, line.code)}",
             f"On {line.date}, line {line.id} on your bill shows billed {money(line.billed)} and patient owed {money(line.patient_owed)}."]
    cites = [line.id]
    if eob:
        parts.append(f"Your EOB (line {eob.id}) shows patient responsibility {money(eob.patient_resp)}.")
        cites.append(eob.id)
    for f in case.findings:
        if line.id in f.line_ids:
            parts += ["Our checks flagged this line.", *_expl_parts(case, f)]
            cites.append(f.id)
    return parts, cites


def build_answer(case: Case, intent: str, question_en: str) -> Answer | None:
    """Deterministic English answer from the case data, or None when the data cannot answer."""
    fs = case.findings
    if intent == "what_is_eob":
        return Answer.of([DEFINITIONS["EOB"], "Compare each line on your EOB with your bill."], [], intent)
    if intent == "define_term":
        for term, pat in TERM_PATTERNS.items():
            if re.search(pat, question_en, re.IGNORECASE) and term in DEFINITIONS:
                return Answer.of([DEFINITIONS[term]], [], intent)
        return None
    if intent == "charged_twice":
        dups = [f for f in fs if f.rule == "duplicate_charge"]
        if not dups:
            return Answer.of(["Our checks did not find a code billed twice on the same day.",
                              "If you see two lines you do not understand, it is worth asking the billing office about them."], [], intent)
        return Answer.of([p for f in dups for p in _expl_parts(case, f)], [i for f in dups for i in [f.id, *f.line_ids]], intent)
    if intent == "how_much_owe":
        parts = [f"Your bill asks you to pay {money(case.bill.patient_balance)}."]
        cites = []
        if case.eob.total_patient_responsibility:
            parts.append(f"Your EOB says your share is {money(case.eob.total_patient_responsibility)}.")
        if case.total_impact > 0:
            parts.append(f"Our checks found {money(case.total_impact)} that may not be owed, so the amount you actually owe may be lower.")
            cites = [f.id for f in fs if f.impact > 0]
        else:
            parts.append("Our checks did not find a reason to question the amount.")
        return Answer.of([*parts, "Only the billing office can confirm the final amount."], cites, intent)
    if intent == "what_to_say":
        parts = [f"When you call the billing office, you can say: I am calling about account {case.bill.account_number}. I have my bill and my EOB."]
        for f in fs[:3]:
            parts += [f.evidence, "Could you review this?"]
        if not fs:
            parts.append("I would like an itemized bill with codes, please.")
        parts.append("Ask them to note the date of your call and the name of the person you spoke with.")
        return Answer.of(parts, [f.id for f in fs[:3]], intent)
    if intent == "what_happens_next":
        parts = ["First, check that the lines on your bill match your documents."]
        if fs:
            parts += ["Then call the billing office and ask them to review the lines we flagged, or send the letter we prepared.",
                      "Ask for a written reply and keep notes of who you spoke with."]
        else:
            parts += ["Our checks did not find anything to dispute.", "If something still looks wrong, it is worth asking the billing office."]
        return Answer.of(parts, [f.id for f in fs], intent)
    if intent == "charge_meaning":
        codes = CODE_RE.findall(question_en)
        ids = LINE_RE.findall(question_en)
        lines = [l for l in case.bill.lines if l.code in codes or l.id in ids]
        if (codes or ids) and not lines:
            return None  # asked about something that is not on this bill
        if lines:
            parts, cites = [], []
            for l in lines[:3]:
                p, c = _line_parts(case, l)
                parts += p
                cites += c
            return Answer.of(parts, cites, intent)
        if fs:
            parts = [x for f in fs[:3] for x in [fallback_explanation(case, f)["headline"] + ".", *_expl_parts(case, f)]]
            return Answer.of(parts, [i for f in fs[:3] for i in [f.id, *f.line_ids]], intent)
        parts = ["Your bill lists these charges:"] + [f"code {l.code} ({code_note(case, l.code).rstrip('.')})." for l in case.bill.lines[:5]]
        return Answer.of(parts, [l.id for l in case.bill.lines[:5]], intent)
    return None


PHRASE_TOOL = {"name": "write_answer", "description": "Rewrite the draft answer in friendlier plain language.",
               "input_schema": {"type": "object", "required": ["answer", "citations"],
                                "properties": {"answer": {"type": "string"},
                                               "citations": {"type": "array", "items": {"type": "string"}}}}}


class QA:
    def __init__(self, translator: Translator, llm: LLMClient | None = None):
        self.translator, self.llm = translator, llm

    def _fixed(self, kind: str, lang: str, english: str, q_en: str | None) -> QAResult:
        key = {"defer": "defer", "medical": "redirect_medical", "legal": "redirect_legal"}[kind]
        text = english if lang == "en" else load_glossary(lang).phrases[key]
        return QAResult(text, lang, kind, [], True, q_en, english)

    def _rephrase(self, case: Case, draft: Answer, facts: Facts) -> Answer:
        if self.llm is None:
            return draft
        try:
            out = self.llm.complete_tool(
                "Rewrite the draft answer for a patient in plain language. Keep every fact. Use only the numbers, codes "
                "and ids already in the draft. Never add advice about insurance coverage. List the ids you relied on.",
                json.dumps({"draft": draft.text_en, "available_ids": draft.citations}), PHRASE_TOOL)
        except Exception:  # noqa: BLE001
            return draft
        text, cites = str(out.get("answer", "")), list(out.get("citations", []))
        if text and validate_text(text, facts).ok and not BANNED.search(text) and set(cites) <= set(draft.citations):
            return Answer(text, cites or draft.citations, draft.kind)  # rephrased: translate as one text
        return draft

    def ask(self, case: Case, question: str, lang: str = "auto") -> QAResult:
        lang = detect_language(question) if lang == "auto" else lang
        q_en = self.translator.to_english(question, lang)
        intent = detect_intent_en(q_en) if q_en else None
        if intent is None and lang != "en":
            intent = detect_intent_native(question, lang)
        if intent in ("medical", "legal"):
            return self._fixed(intent, lang, REDIRECT_EN[intent], q_en)
        if intent in (None, "defer"):
            return self._fixed("defer", lang, DEFER_EN, q_en)
        draft = build_answer(case, intent, q_en or question)
        if draft is None:
            return self._fixed("defer", lang, DEFER_EN, q_en)
        facts = qa_facts(case)
        if not validate_text(draft.text_en, facts).ok:  # step 4: the 3A validator (should never trigger)
            return self._fixed("defer", lang, DEFER_EN, q_en)
        draft = self._rephrase(case, draft, facts)
        tr: Translation = (self.translator.translate_parts(draft.parts, lang) if draft.parts
                           else self.translator.translate(draft.text_en, lang))
        return QAResult(tr.text, lang, intent, draft.citations, False, q_en, draft.text_en, tr.notice, tr.verified)
