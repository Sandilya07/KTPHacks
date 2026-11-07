import random

import pytest

from audit.models import Finding
from explain.validator import Facts, facts_for_finding, validate_text
from tests.helpers import bl, case, el


@pytest.fixture
def facts_and_case():
    c = case([bl("B1", "99213", billed=150.0, owed=30.0), bl("B2", "99213", billed=150.0, owed=30.0)], [el("E1")])
    f = Finding(id="x", rule="duplicate_charge", tier="definite", line_ids=["B1", "B2"], impact=30.0,
                evidence="Code 99213 appears on 2024-01-02 in lines B1 and B2.", source="Duplicate rule")
    return facts_for_finding(c, f), c, f


GOOD = "Code 99213 was billed twice on 2024-01-02, on lines B1 and B2. The second line adds $30.00."


def test_accepts_grounded_text(facts_and_case):
    assert validate_text(GOOD, facts_and_case[0], "definite").ok


@pytest.mark.parametrize("bad,why", [
    ("The second line adds $31.00.", "number"), ("Code 99214 was billed twice.", "code"),
    ("It happened on 2024-01-03.", "date"), ("See line B9.", "line id"),
    ("This is fraud.", "banned"), ("That looks illegal.", "banned"), ("This is a scam.", "banned"),
    ("You could file a lawsuit.", "banned"), ("You are owed 3 refunds.", "number"),
])
def test_rejects_invented_or_banned(facts_and_case, bad, why):
    assert not validate_text(f"{GOOD} {bad}", facts_and_case[0], "definite").ok, why


def test_property_random_invented_numbers_are_rejected(facts_and_case):
    facts = facts_and_case[0]
    rng = random.Random(0)
    for _ in range(300):
        amount = round(rng.uniform(0.01, 5000), 2)
        if amount in facts.numbers:
            continue
        assert not validate_text(f"The bill asks for ${amount:,.2f}.", facts).ok
        code = "".join(rng.choice("0123456789") for _ in range(5))
        if code not in facts.codes:
            assert not validate_text(f"Code {code} was billed.", facts).ok


def test_property_every_fact_value_is_accepted(facts_and_case):
    facts = facts_and_case[0]
    for amount in facts.numbers:
        assert validate_text(f"The amount is {amount:.2f}.", facts).ok
    for code in facts.codes:
        assert validate_text(f"Code {code} is listed.", facts).ok


def test_tone_checks():
    facts = Facts()
    assert validate_text("This appears to conflict with a billing rule and should be reviewed.", facts, "likely").ok
    assert not validate_text("This is wrong.", facts, "likely").ok
    assert validate_text("It is worth asking the billing office about this.", facts, "ask").ok
    assert not validate_text("Call them.", facts, "ask").ok
    assert not validate_text("This might be wrong.", facts, "definite").ok
    assert validate_text("The bill does not match the EOB.", facts, "definite").ok
