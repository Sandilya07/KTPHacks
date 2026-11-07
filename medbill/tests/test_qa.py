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
