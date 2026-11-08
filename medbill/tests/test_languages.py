import pytest

from i18n.languages import ascii_digits, language_name, normalize_language, refine_local_detection, wrong_output_language
from i18n.placeholders import protect, same_values
from i18n.translate import Translator


@pytest.mark.parametrize("source,expected", [("ukr", "uk"), ("tam", "ta"), ("tel", "te"), ("ara", "ar"),
                                            ("tl", "fil"), ("zh-hant-tw", "zh-Hant-TW"), ("es-419", "es-419")])
def test_language_codes_are_canonical_without_a_three_language_allowlist(source, expected):
    assert normalize_language(source) == expected
    assert language_name(source) != source


@pytest.mark.parametrize("language,wrong_model", [("ta", "ml"), ("te", "en"), ("gu", "ml"),
                                                 ("pa", "hi"), ("mn", "km"), ("mr", "hi"), ("ne", "hi")])
def test_script_and_offline_checks_correct_model_confusions(language, wrong_model):
    import json
    from pathlib import Path
    corpus = json.loads((Path(__file__).parent.parent / "data/qa_eval/multilingual.json").read_text(encoding="utf-8"))
    question = next(row["question"] for row in corpus if row["language"] == language)
    assert refine_local_detection(question, wrong_model) == language


def test_localized_digits_are_normalized_for_case_lookup():
    assert ascii_digits("الرمز ٨٠٠٥٣") == "الرمز 80053"
    assert ascii_digits("कोड ८००५३") == "कोड 80053"


def test_mongolian_is_not_mistaken_for_russian_because_both_use_cyrillic():
    question = "Миний нэхэмжлэх дээрх 80053 код юу гэсэн үг вэ?"
    assert refine_local_detection(question, "ru") == "mn"
    assert refine_local_detection("Что означает код 80053 в моём счёте?", "ru") == "ru"


@pytest.mark.parametrize("translated", ["代码80053在2024-03-05日的费用为$95.00，行B2，账户ACCT-0001。",
                                       "コード80053は2024-03-05に$95.00、行B2、口座ACCT-0001。"])
def test_values_stay_protected_next_to_non_latin_letters(translated):
    english = "Code 80053 on 2024-03-05 costs $95.00, line B2, account ACCT-0001."
    assert same_values(english, translated)
    assert all(value not in protect(translated).masked for value in ("80053", "2024-03-05", "$95.00", "ACCT-0001"))


def test_english_echo_is_not_verified_as_hindi_translation():
    assert wrong_output_language("A blood test that checks several body chemicals including blood sugar and kidney function.", "hi")


def test_local_translation_inserts_billing_values_in_python():
    class Local:
        provider = "ollama"
        def complete_tool(self, system, user, tool):
            assert "95.00" not in user and "80053" not in user
            return {"segments": {"s0": "Vous devez", "s2": "pour le code"}}
    result = Translator(Local()).translate("You owe $95.00 for code 80053.", "fr")
    assert result.verified and "$95.00" in result.text and "80053" in result.text


def test_languages_outside_offline_detector_are_not_replaced_by_its_guess(monkeypatch):
    monkeypatch.setattr("i18n.languages.offline_guess", lambda text: ("ur", .99))
    assert refine_local_detection("پرسیارێکم دەربارەی پسوولەکەم هەیە", "ckb") == "ckb"


def test_romanized_language_is_not_replaced_just_because_it_uses_latin(monkeypatch):
    monkeypatch.setattr("i18n.languages.offline_guess", lambda text: ("id", .99))
    assert refine_local_detection("Mera bill itna zyada kyun hai?", "hi") == "hi"


def test_traditional_chinese_is_not_silently_changed_to_simplified():
    from i18n.languages import chinese_script_tag
    assert chinese_script_tag("我的帳單上的代碼", "zh-Hans") == "zh-Hant"
    assert chinese_script_tag("我的账单上的代码", "zh-Hant") == "zh-Hans"
    assert wrong_output_language("我的账单上的代码", "zh-Hant")


def test_repeated_word_loops_are_rejected():
    from i18n.languages import repetitive_output
    assert repetitive_output("रक्त रक्त रक्त रक्त रक्त रक्त")
    assert not repetitive_output("Code 80053 is a blood test. Code 99213 is an office visit.")


def test_english_translation_is_allowed_when_english_is_the_target():
    assert not wrong_output_language("A blood test that checks several body chemicals including blood sugar and kidney function.", "en")


def test_output_language_catalog_is_not_an_allowlist(monkeypatch):
    monkeypatch.setattr("i18n.languages.offline_guess", lambda text: ("ur", 1.0))
    assert not wrong_output_language("پرسیارێکم دەربارەی پسوولەکەم هەیە " * 3, "ckb")
