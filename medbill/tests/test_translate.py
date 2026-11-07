from i18n.placeholders import protect
from i18n.translate import Translator
import pytest

EN = "Code 99213 was billed on 2024-03-05 for $95.00. This is a claim about your deductible."


class FnLLM:
    """Mock translation model driven by a function(system, user, tool_name) -> dict."""

    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def complete_tool(self, system, user, tool):
        self.calls.append((system, user, tool["name"]))
        return self.fn(system, user, tool["name"], len(self.calls))


def good(system, user, tool, n):
    if tool == "translate":
        t = user.split("\n\n")[0]
        return {"translation": "[es] " + t.replace("claim", "reclamo").replace("deductible", "deducible")}
    return {"english": user.replace("[es] ", "")}


def test_verified_translation_restores_numbers():
    tr = Translator(FnLLM(good)).translate(EN, "es")
    assert tr.verified and "$95.00" in tr.text and "99213" in tr.text and "2024-03-05" in tr.text
    assert "[[" not in tr.text and tr.attempts == 1


def test_model_never_sees_raw_numbers():
    llm = FnLLM(good)
    Translator(llm).translate(EN, "es")
    for _, user, tool in llm.calls:
        for secret in ("99213", "$95.00", "2024-03-05"):
            assert secret not in user, (tool, user)


def test_corrupted_translation_retries_then_succeeds():
    def fn(system, user, tool, n):
        if tool == "translate" and n == 1:
            return {"translation": "[es] Código [[CODE_1]] el [[DATE_1]] por 95 dólares. reclamo deducible"}
        return good(system, user, tool, n)
    llm = FnLLM(fn)
    tr = Translator(llm).translate(EN, "es")
    assert tr.verified and tr.attempts == 2 and tr.errors


def test_always_corrupt_falls_back_to_english_with_notice():
    def fn(system, user, tool, n):
        return {"translation": "[es] Cuesta 95 dólares"} if tool == "translate" else {"english": ""}
    tr = Translator(FnLLM(fn)).translate(EN, "es")
    assert not tr.verified and tr.text == EN and "inglés" in tr.notice and tr.source == "english"


def test_back_translation_mismatch_is_caught():
    def fn(system, user, tool, n):
        if tool == "to_english":
            return {"english": user.replace("[es] ", "") + " 5"}  # back-translation introduces a number
        return good(system, user, tool, n)
    tr = Translator(FnLLM(fn)).translate(EN, "es")
    assert not tr.verified and tr.text == EN


def test_glossary_miss_triggers_retry_and_is_reported_if_it_persists():
    def stubborn(system, user, tool, n):
        return {"translation": "[es] " + user.split("\n\n")[0]} if tool == "translate" else {"english": user.replace("[es] ", "")}
    tr = Translator(FnLLM(stubborn)).translate(EN, "es")
    assert tr.verified and tr.attempts == 2 and tr.glossary_warnings  # numbers fine, glossary non-compliant
    assert Translator(FnLLM(good)).translate(EN, "es").glossary_warnings == []


def test_cache_is_keyed_on_masked_text_and_reused_for_other_numbers():
    p = protect(EN)
    cache = {"es": {p.masked: "Código [[CODE_1]] el [[DATE_1]] por [[AMT_1]]. Es un reclamo sobre su deducible."}}
    tr = Translator(None, cache).translate(EN, "es")
    assert tr.source == "cache" and tr.verified and "$95.00" in tr.text
    other = Translator(None, cache).translate(EN.replace("$95.00", "$12.00").replace("99213", "99214"), "es")
    assert other.source == "cache" and "$12.00" in other.text and "99214" in other.text


def test_no_model_and_no_cache_shows_english_with_notice():
    tr = Translator(None).translate(EN, "mn")
    assert not tr.verified and tr.text == EN and tr.notice


def test_english_is_a_noop_and_questions_roundtrip():
    assert Translator(None).translate(EN, "en").text == EN
    fn = lambda s, u, t, n: {"english": "How much do I owe for [[CODE_1]]?"}
    assert Translator(FnLLM(fn)).to_english("¿Cuánto debo por 99213?", "es") == "How much do I owe for 99213?"
    bad = lambda s, u, t, n: {"english": "How much do I owe for 55555?"}
    assert Translator(FnLLM(bad)).to_english("¿Cuánto debo por 99213?", "es") is None


def test_detects_languages_outside_demo_glossaries():
    llm = FnLLM(lambda s, u, t, n: {"language": "fr"})
    assert Translator(llm).detect_language("Je veux comprendre ma facture") == "fr"
    assert llm.calls[0][2] == "detect_language"


def test_unknown_glossary_uses_verified_model_translation():
    tr = Translator(FnLLM(good)).translate("Code 99213 costs $95.00.", "fr")
    assert tr.verified and "99213" in tr.text and "$95.00" in tr.text


def test_rejects_invalid_detected_language():
    import pytest
    with pytest.raises(ValueError):
        Translator(FnLLM(lambda s, u, t, n: {"language": "../../file"})).detect_language("hello")


@pytest.mark.parametrize("value", ["", "   ", None, 123, []])
def test_invalid_translation_values_fall_back_instead_of_being_verified(value):
    llm = FnLLM(lambda s, u, tool, n: {"translation": value} if tool == "translate" else {"english": ""})
    result = Translator(llm).translate("Please review this charge.", "fr")
    assert not result.verified and result.text == "Please review this charge." and result.notice


@pytest.mark.parametrize("value", ["", "   ", None, [], 123])
def test_invalid_question_translation_returns_none(value):
    assert Translator(FnLLM(lambda s, u, t, n: {"english": value})).to_english("Bonjour", "fr") is None


def test_blank_back_translation_cannot_verify_numberless_answer():
    llm = FnLLM(lambda s, u, tool, n: {"translation": "Veuillez vérifier."} if tool == "translate" else {"english": ""})
    assert not Translator(llm).translate("Please review.", "fr").verified


def test_empty_parts_does_not_crash():
    result = Translator(None).translate_parts([], "fr")
    assert result.text == "" and result.verified


@pytest.mark.parametrize("lang", ["zh-hant-tw", "es-419"])
def test_detected_language_accepts_script_and_region_subtags(lang):
    from i18n.languages import normalize_language
    assert Translator(FnLLM(lambda s, u, t, n: {"language": lang})).detect_language("hello") == normalize_language(lang)
