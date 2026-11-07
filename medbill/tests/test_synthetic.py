import importlib.util
import random
from pathlib import Path

from audit.engine import run_case
from audit.models import Bill, Case, Eob

spec = importlib.util.spec_from_file_location("gen", Path(__file__).parent.parent / "scripts" / "generate_synthetic.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def audit(case):
    return run_case(Case(bill=Bill.model_validate(case["bill"]), eob=Eob.model_validate(case["eob"])))


def test_generator_is_deterministic():
    a = gen.build_case(1, "duplicate", random.Random(7))
    b = gen.build_case(1, "duplicate", random.Random(7))
    assert a == b


def test_clean_cases_have_no_strong_findings_and_seeded_totals_match():
    rng = random.Random(3)
    for _ in range(15):
        assert not [f for f in audit(gen.build_case(0, None, rng)).findings if f.tier != "ask"]
    for kind in ("duplicate", "unbundled", "eob_mismatch", "balance_billing"):
        case = gen.build_case(0, kind, rng)
        assert case["expected_total"] > 0
        assert abs(audit(case).total_impact - case["expected_total"]) < 0.01, kind
