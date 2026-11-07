import random

import pytest

from i18n.glossary import load_glossary, supported_languages
from i18n.placeholders import protect, restore, same_values, verify_tokens

TEXT = ("Code 99213 was billed on 2024-03-05 for $1,234.50 on account ACCT-0001. "
        "Lines B2 and E4 differ by 207.00, about 15% of the total.")


def test_protect_replaces_every_protected_value_and_roundtrips():
    p = protect(TEXT)
    for original in ("99213", "2024-03-05", "$1,234.50", "ACCT-0001", "B2", "E4", "207.00", "15%"):
        assert original not in p.masked
    assert restore(p.masked, p.mapping) == TEXT
    assert {t.split("_")[0] for t in p.mapping} == {"[[CODE", "[[DATE", "[[AMT", "[[ACCT", "[[LINE", "[[PCT"}


def test_five_digit_amount_is_not_mistaken_for_a_code():
    p = protect("You owe $12,345.00 and 54321.00 for code 99214.")
    assert sorted(p.mapping.values()) == ["$12,345.00", "54321.00", "99214"]


def test_clean_translation_passes():
    p = protect(TEXT)
    fake = "[es] " + p.masked
    assert verify_tokens(p.masked, fake, p.mapping) == []


@pytest.mark.parametrize("corrupt", [
    lambda s: s.replace("[[AMT_1]]", ""),                          # dropped token
    lambda s: s.replace("[[AMT_1]]", "[[AMT_1]] [[AMT_1]]"),       # duplicated token
    lambda s: s.replace("[[CODE_1]]", "[[CODE_9]]"),               # invented token
    lambda s: s.replace("[[DATE_1]]", "[DATE_1]"),                 # mangled brackets
    lambda s: s + " Debe 500 dólares.",                            # stray digits
    lambda s: s.replace("[[PCT_1]]", "15 por ciento"),             # value translated as free text
])
def test_deliberately_corrupted_translations_are_caught(corrupt):
    p = protect(TEXT)
    assert verify_tokens(p.masked, corrupt("[es] " + p.masked), p.mapping)


def test_property_random_digit_corruption_always_caught():
    rng = random.Random(1)
    p = protect(TEXT)
    for _ in range(200):
        out = "[es] " + p.masked + f" {rng.randint(0, 99999)}"
        assert verify_tokens(p.masked, out, p.mapping)


def test_same_values_detects_changed_numbers():
    assert same_values(TEXT, TEXT.replace("$1,234.50", "$1,234.50"))
    assert not same_values(TEXT, TEXT.replace("$1,234.50", "$1,243.50"))
    assert not same_values(TEXT, TEXT.replace("99213", "99214"))
    assert not same_values(TEXT, TEXT.replace("2024-03-05", "2024-03-06"))


def test_glossary_pinning_and_check():
    es = load_glossary("es")
    assert {"es", "mn"} <= set(supported_languages())
    src = "Ask about the allowed amount and your EOB."
    assert set(es.terms_in(src)) == {"allowed amount", "EOB"}
    assert not es.check(src, "Pregunte sobre el monto permitido y su EOB.")
    assert es.check(src, "Pregunte sobre la cantidad aprobada y su EOB.")
    mn = load_glossary("mn")
    assert not mn.check("The billed amount is high.", "Нэхэмжилсэн дүнг шалгана уу.")
    assert not es.reviewed and not mn.reviewed  # drafts: flagged as needing a native speaker
