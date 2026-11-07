import pytest

from audit.models import Finding
from explain.explainer import Explainer
from explain.templates import fallback_explanation
from explain.validator import facts_for_finding, validate_text
from tests.helpers import ScriptedLLM, bl, case, el, overcharge_case

GOOD = {"headline": "Code 99213 was billed twice", "what_happened": "Lines B1 and B2 both list code 99213 on 2024-01-02.",
        "why_it_matters": "The second line adds $20.00 to what you owe.", "what_you_can_do": "Ask the billing office to remove line B2."}


def dup_case():
    from audit.engine import run_case
    return run_case(case([bl("B1"), bl("B2")], [el("E1"), el("E2", status="denied-duplicate", resp=0.0)]))


def test_no_llm_uses_fallback_and_counts_it():
    c = dup_case()
    ex = Explainer(None)
    e = ex.explain(c, c.findings[0])
    assert e.source == "fallback" and ex.stats.fallbacks == 1 and ex.stats.fallback_rate == 1.0


def test_valid_llm_output_is_used():
    c = dup_case()
    ex = Explainer(ScriptedLLM(GOOD))
    assert ex.explain(c, c.findings[0]).source == "llm" and ex.stats.llm_ok == 1


def test_invented_number_retries_then_succeeds():
    c = dup_case()
    bad = dict(GOOD, why_it_matters="The second line adds $99.00 to what you owe.")
    llm = ScriptedLLM(bad, GOOD)
    ex = Explainer(llm)
    e = ex.explain(c, c.findings[0])
    assert e.source == "llm" and len(llm.calls) == 2 and ex.stats.validator_failures == 1
    assert "rejected" in llm.calls[1][1]  # retry prompt tells the model why


def test_three_failures_fall_back_to_template():
    c = dup_case()
    bad = dict(GOOD, headline="This is fraud")
    llm = ScriptedLLM(bad)
    ex = Explainer(llm)
    e = ex.explain(c, c.findings[0])
    assert e.source == "fallback" and len(llm.calls) == 3 and ex.stats.fallbacks == 1


def test_llm_exception_falls_back_without_crashing():
    c = dup_case()
    assert Explainer(ScriptedLLM(RuntimeError("boom"))).explain(c, c.findings[0]).source == "fallback"


def test_all_overcharge_findings_fallbacks_pass_validator():
    c = overcharge_case()
    for f in c.findings:
        e = fallback_explanation(c, f)
        assert validate_text(" ".join(e.values()), facts_for_finding(c, f), f.tier).ok, (f.rule, e)


def finding(rule, tier, ids, impact=10.0, evidence="Evidence 99213 on 2024-01-02."):
    return Finding(id="f", rule=rule, tier=tier, line_ids=ids, impact_line_ids=ids[:1] if impact else [],
                   impact=impact, evidence=evidence, source="Source rule")


@pytest.mark.parametrize("f", [
    finding("duplicate_charge", "definite", ["B1", "B2"]),
    finding("duplicate_charge", "ask", ["B1", "B2"], 0.0),
    finding("unbundling", "likely", ["B1", "B2"]),
    finding("unbundling", "ask", ["B1", "B2"], 0.0),
    finding("excess_units", "likely", ["B1"], evidence="3 units of 99213 were billed on 2024-01-02; the limit is 1."),
    finding("balance_billing", "definite", ["B1", "E1"]),
    finding("eob_mismatch", "definite", ["B1", "E1"]),
    finding("missing_eob_line", "ask", ["B1"], 0.0),
    finding("price_outlier", "ask", ["B1"], 0.0),
    finding("balance_arithmetic", "definite", [], 10.0),
])
def test_fallback_exists_for_every_rule_type_and_is_valid(f):
    c = case([bl("B1", "99213", mods=["59"]), bl("B2", "82947")], [el("E1")])
    e = fallback_explanation(c, f)
    assert all(e.values())
    facts = facts_for_finding(c, f)
    assert validate_text(" ".join(e.values()), facts, f.tier).ok, e
