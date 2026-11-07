import pytest

from explain.validator import validate_text
from i18n.glossary import load_glossary
from i18n.qa import (
    DEFER_EN,
    QA,
    REDIRECT_EN,
    build_answer,
    detect_intent_en,
    detect_intent_native,
    detect_language,
    qa_facts,
)
from i18n.translate import Translator
from tests.helpers import ScriptedLLM, overcharge_case
from tests.test_translate import FnLLM, good


@pytest.fixture
def case():
    return overcharge_case()


def en_qa():
    return QA(Translator(None))


@pytest.mark.parametrize("q,intent", [
    ("What does this charge mean?", "charge_meaning"), ("Why was I charged twice?", "charged_twice"),
    ("How much do I actually owe?", "how_much_owe"), ("What should I say when I call billing?", "what_to_say"),
    ("What is an EOB?", "what_is_eob"), ("What happens next?", "what_happens_next"),
    ("What is a deductible?", "define_term"), ("Will my insurance cover my next surgery?", "defer"),
    ("What is my deductible?", "defer"), ("Should I take this medication?", "medical"),
    ("Can I sue the hospital?", "legal"), ("Who is the clinic's accountant?", None),
])
def test_intents(q, intent):
    assert detect_intent_en(q) == intent


@pytest.mark.parametrize("q", ["How much do I owe?", "Why was I charged twice?", "What should I say when I call billing?",
                               "What does code 99214 mean?", "What is an EOB?", "What happens next?", "What is a claim?"])
def test_answers_are_grounded_and_cited(case, q):
    r = en_qa().ask(case, q, "en")
    assert not r.deferred and validate_text(r.answer, qa_facts(case)).ok
    ids = {f.id for f in case.findings} | {l.id for l in case.bill.lines} | {l.id for l in case.eob.lines}
    assert set(r.citations) <= ids
    if r.kind in ("charged_twice", "how_much_owe"):
        assert r.citations


def test_how_much_owe_uses_case_numbers(case):
    r = en_qa().ask(case, "How much do I owe?", "en")
    assert "$502.00" in r.answer and "$90.00" in r.answer and "$412.00" in r.answer


def test_charged_twice_cites_duplicate(case):
    r = en_qa().ask(case, "Why was I charged twice?", "en")
    assert "80053" in r.answer and any(c in r.citations for c in ("B2", "B3"))


def test_code_not_on_bill_defers(case):
    r = en_qa().ask(case, "What does code 12345 mean?", "en")
    assert r.deferred and r.answer == DEFER_EN


@pytest.mark.parametrize("q", ["Will my insurance cover a future surgery?", "What is my deductible?",
                               "Is my doctor in network next year?", "What is my policy number?", "Who owns this clinic?"])
def test_unanswerable_questions_defer(case, q):
    assert en_qa().ask(case, q, "en").deferred


def test_redirects_are_fixed_phrases(case):
    assert en_qa().ask(case, "Should I stop taking my medication?", "en").answer == REDIRECT_EN["medical"]
    assert en_qa().ask(case, "Can I sue them?", "en").answer == REDIRECT_EN["legal"]


@pytest.mark.parametrize("lang", ["es", "mn"])
def test_defer_and_redirect_use_the_language_glossary(case, lang):
    g = load_glossary(lang)
    qa = QA(Translator(FnLLM(lambda s, u, t, n: {"english": "Will my insurance cover surgery?"})))
    r = qa.ask(case, "pregunta", lang)
    assert r.deferred and r.answer == g.phrases["defer"]
    qa2 = QA(Translator(FnLLM(lambda s, u, t, n: {"english": "Can I sue them?"})))
    assert qa2.ask(case, "pregunta", lang).answer == g.phrases["redirect_legal"]


def test_spanish_question_end_to_end_keeps_numbers_intact(case):
    def fn(system, user, tool, n):
        if tool == "to_english" and "[[" not in user:  # the question; otherwise it is a back-translation
            return {"english": "How much do I owe?"}
        return good(system, user, tool, n)
    r = QA(Translator(FnLLM(fn))).ask(case, "¿Cuánto debo?", "es")
    assert r.verified and not r.deferred and r.answer.startswith("[es]")
    for v in ("$502.00", "$90.00", "$412.00"):
        assert v in r.answer


def test_offline_native_hints_pick_the_intent_without_a_model(case):
    assert detect_intent_native("¿Por qué me cobraron dos veces?", "es") == "charged_twice"
    assert detect_intent_native("Яагаад надаас хоёр удаа авсан бэ?", "mn") == "charged_twice"
    r = QA(Translator(None)).ask(case, "¿Por qué me cobraron dos veces?", "es")
    assert r.kind == "charged_twice" and not r.verified and r.notice and "80053" in r.answer  # English + notice


def test_llm_rephrase_is_validated_or_ignored(case):
    bad = {"answer": "You are owed $999.00 back.", "citations": []}
    r = QA(Translator(None), ScriptedLLM(bad)).ask(case, "How much do I owe?", "en")
    assert "$999.00" not in r.answer and "$502.00" in r.answer
    ok = {"answer": "Your bill asks for $502.00 but your EOB says $90.00.", "citations": []}
    assert QA(Translator(None), ScriptedLLM(ok)).ask(case, "How much do I owe?", "en").answer == ok["answer"]


def test_language_detection():
    assert detect_language("¿Cuánto debo por la factura?") == "es"
    assert detect_language("Би хэдийг төлөх ёстой вэ?") == "mn"
    assert detect_language("How much do I owe?") == "en"


def test_auto_detection_uses_model_for_new_languages(case):
    def fn(system, user, tool, n):
        if tool == "detect_language":
            return {"language": "fr"}
        if tool == "to_english":
            return {"english": "How much do I owe?" if "Translate the user's question" in system else user}
        return {"translation": user}
    result = QA(Translator(FnLLM(fn))).ask(case, "Combien dois-je payer ?")
    assert result.language == "fr"
    assert result.kind == "how_much_owe"
    assert "$502.00" in result.answer


def test_build_answer_none_for_unknown_intent(case):
    assert build_answer(case, "nonsense", "x") is None


@pytest.mark.parametrize("question", ["Why am I being overcharged", "Why is my bill so high?",
                                      "Why are they charging me so much?", "Is my bill incorrect?"])
def test_overcharge_questions_explain_findings_in_demo(case, question):
    result = en_qa().ask(case, question, "en")
    assert not result.deferred
    assert "$412.00" in result.answer
    assert "80053" in result.answer
    assert result.citations and validate_text(result.answer, qa_facts(case)).ok


def test_overcharge_question_does_not_assume_an_error_on_clean_bill(case):
    case.findings, case.total_impact = [], 0
    result = en_qa().ask(case, "Why am I being overcharged?", "en")
    assert not result.deferred and "did not find" in result.answer


def test_natural_question_uses_case_and_followup_history(case):
    llm = ScriptedLLM({"kind": "answer", "answer": "The bill asks you to pay $502.00.",
                       "citations": ["B2"], "case_specific": True})
    history = [{"role": "user", "text": "Tell me about my balance"},
               {"role": "assistant", "text": "Your bill asks for $502.00."}]
    result = QA(Translator(None), llm).ask(case, "Can you walk me through that?", "en", history)
    assert not result.deferred and result.kind == "natural"
    assert result.citations == ["B2"]
    import json
    context = json.loads(llm.calls[0][1])
    assert context["conversation"] == history and context["potential_overcharge"] == 412
    assert "bill" in context and "insurance_statement" in context and context["findings"]


@pytest.mark.parametrize("answer,citations", [("You owe $9999.99.", ["B2"]),
                                              ("Your bill asks for $502.00.", ["B999"]),
                                              ("Your bill asks for $502.00.", [])])
def test_natural_answers_reject_unknown_values_or_missing_evidence(case, answer, citations):
    llm = ScriptedLLM({"kind": "answer", "answer": answer, "citations": citations, "case_specific": True})
    result = QA(Translator(None), llm).ask(case, "Walk me through these expenses", "en")
    assert result.deferred and "$9999.99" not in result.answer


def test_model_failure_still_explains_overcharges(case):
    result = QA(Translator(None), ScriptedLLM(RuntimeError("offline"))).ask(
        case, "Why am I being overcharged?", "en")
    assert not result.deferred and "$412.00" in result.answer


@pytest.mark.parametrize("lang,question", [("fr", "Pourquoi cette facture est-elle si élevée ?"),
                                          ("hi", "मेरा बिल इतना अधिक क्यों है?"),
                                          ("ar", "لماذا فاتورتي مرتفعة؟")])
def test_natural_multilingual_question_detects_and_translates(case, lang, question):
    def fn(system, user, tool, n):
        if tool == "detect_language":
            return {"language": lang}
        if tool == "to_english":
            return {"english": "Please walk me through these expenses" if "question" in system else user}
        if tool == "answer_bill_question":
            return {"kind": "answer", "answer": "Your bill asks for $502.00.", "citations": ["B2"], "case_specific": True}
        return {"translation": f"[{lang}] " + user}
    llm = FnLLM(fn)
    result = QA(Translator(llm), llm).ask(case, question)
    assert result.language == lang and result.verified and not result.deferred
    assert result.answer.startswith(f"[{lang}]") and "$502.00" in result.answer


@pytest.mark.parametrize("question,intent", [
    ("How much do I owe according to my EOB?", "how_much_owe"),
    ("Why was I charged twice on my EOB?", "charged_twice"),
    ("Explain code 99214 on the EOB", "charge_meaning"),
    ("What does EOB mean?", "what_is_eob"),
])
def test_eob_mentions_do_not_override_question_intent(question, intent):
    assert detect_intent_en(question) == intent


@pytest.mark.parametrize("citations", [None, [None], [{}], "B2"])
def test_malformed_rephrase_citations_use_deterministic_answer(case, citations):
    llm = ScriptedLLM({"answer": "Your bill asks for $502.00.", "citations": citations})
    result = QA(Translator(None), llm).ask(case, "How much do I owe?", "en")
    assert not result.deferred and "$412.00" in result.answer


def test_zero_insurance_responsibility_is_reported(case):
    case.eob.total_patient_responsibility = 0
    result = en_qa().ask(case, "How much do I owe?", "en")
    assert "Your EOB says your share is $0.00." in result.answer


def test_numeric_case_answer_requires_evidence_even_if_model_marks_it_general(case):
    llm = ScriptedLLM({"kind": "answer", "answer": "Your bill asks for $502.00.",
                       "citations": [], "case_specific": False})
    result = QA(Translator(None), llm).ask(case, "Walk me through these expenses", "en")
    assert result.deferred


def test_bare_code_question_uses_available_description(case):
    result = en_qa().ask(case, "What is 80053?", "en")
    assert not result.deferred and "blood test" in result.answer and "80053" in result.answer


def test_explain_all_charges_again_does_not_select_duplicate_intent(case):
    result = en_qa().ask(case, "Can you explain all the charges again", "en")
    assert result.kind == "all_charges" and not result.deferred
    for line in case.bill.lines:
        assert line.id in result.citations


def test_question_translation_failure_does_not_claim_document_evidence_is_missing(case):
    result = QA(Translator(None)).ask(case, "Bonjour, pouvez-vous expliquer ceci ?", "fr")
    assert result.kind == "translation_unavailable" and not result.deferred
    assert "translate your question" in result.answer and "documents for this case do not show" not in result.answer
