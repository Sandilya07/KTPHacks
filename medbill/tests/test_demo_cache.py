"""DEMO_MODE promise: every sentence the sample cases show can be translated offline, from a cache, with
every number intact. If a rule or template changes its English text, this test says which sentence needs a
new translation (python scripts/dump_demo_strings.py prints them)."""
import importlib.util
from pathlib import Path

import pytest

from i18n.demo_cache import load_demo_cache
from i18n.glossary import load_glossary, supported_languages
from i18n.placeholders import protect, same_values, verify_tokens
from i18n.translate import Translator

spec = importlib.util.spec_from_file_location("dump", Path(__file__).parent.parent / "scripts" / "dump_demo_strings.py")
dump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dump)
CACHES = load_demo_cache()


@pytest.fixture(scope="module")
def needed():
    return dump.collect()


@pytest.mark.parametrize("lang", ["es", "mn"])
def test_every_demo_sentence_is_translated_with_every_placeholder_intact(needed, lang):
    assert lang in supported_languages()
    missing = [m for m in needed if m not in CACHES[lang]]
    assert not missing, f"{len(missing)} sentences need a {lang} translation, e.g. {missing[:2]}"
    for masked in needed:
        assert not verify_tokens(masked, CACHES[lang][masked], protect(masked).mapping), masked


@pytest.mark.parametrize("lang", ["es", "mn"])
def test_cached_translations_follow_the_glossary(needed, lang):
    g = load_glossary(lang)
    for masked in needed:
        english = masked.replace("[[", "").replace("]]", "")
        assert not g.check(english, CACHES[lang][masked]), (masked, g.check(english, CACHES[lang][masked]))


@pytest.mark.parametrize("lang", ["es", "mn"])
def test_demo_cases_translate_end_to_end_offline(lang):
    """Run the real flow in DEMO conditions (no model): everything must come back verified from the cache."""
    from datetime import date

    from explain.letter import build_letter
    from i18n.letter import translate_letter
    from i18n.qa import QA, SUGGESTED
    tr = Translator(None, CACHES)
    for name in dump.SAMPLES:
        case = dump.sample_case(name)
        for seg in translate_letter(build_letter(case, today=date(2026, 1, 1)), tr, lang):
            assert seg.verified and same_values(seg.english, seg.translated), (name, seg.section)
        qa = QA(tr)
        for q in SUGGESTED:
            r = qa.ask(case, q, "en")
            assert r.verified and not r.notice
            t = tr.translate_parts(dump.answer_parts(case, q), lang) if r.kind and not r.deferred else None
            if t:
                assert t.verified and same_values(" ".join(dump.answer_parts(case, q)), t.text), (name, q)
