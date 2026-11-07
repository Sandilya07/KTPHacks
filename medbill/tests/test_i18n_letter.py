from datetime import date

from explain.letter import build_letter
from i18n.letter import english_segments, translate_letter
from i18n.placeholders import same_values
from i18n.translate import Translator
from tests.helpers import overcharge_case
from tests.test_translate import FnLLM, good


def test_letter_segments_cover_every_part():
    letter = build_letter(overcharge_case(), today=date(2026, 1, 15))
    sections = [s for s, _ in english_segments(letter)]
    assert sections[0] == "opening" and sections.count("request") == 4 and "total" in sections
    assert sum(s.startswith("charge") for s in sections) == 3


def test_translated_letter_keeps_every_number_and_english_is_untouched():
    letter = build_letter(overcharge_case(), today=date(2026, 1, 15))
    before = letter.to_text()
    segs = translate_letter(letter, Translator(FnLLM(good)), "es")
    assert all(s.verified for s in segs)
    assert all(same_values(s.english, s.translated) for s in segs)  # amounts, dates, codes identical
    assert any("$412.00" in s.translated for s in segs)
    assert letter.to_text() == before  # the English letter is what gets sent


def test_unverifiable_segments_fall_back_to_english_with_notice():
    letter = build_letter(overcharge_case(), today=date(2026, 1, 15))
    segs = translate_letter(letter, Translator(None), "mn")
    assert all(not s.verified and s.translated == s.english and s.notice for s in segs)
