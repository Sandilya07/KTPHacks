import json
from pathlib import Path

from audit.engine import run_audit

DATA = Path(__file__).parent.parent / "data"


def load(name):
    case = json.loads((DATA / f"{name}.json").read_text())
    return case["bill"], case["eob"]


def test_overcharge_totals_412():
    result = run_audit(*load("overcharge"))
    by_rule = {f["rule"]: f for f in result["findings"]}
    assert set(by_rule) == {"duplicate_charge", "unbundling", "eob_mismatch"}
    assert by_rule["duplicate_charge"]["impact"] == 95
    assert by_rule["unbundling"]["impact"] == 110
    assert by_rule["eob_mismatch"]["impact"] == 207
    assert result["total_impact"] == 412


def test_every_finding_has_source():
    for f in run_audit(*load("overcharge"))["findings"]:
        assert f["source"] and f["line_ids"] and f["tier"] in {"definite", "likely", "ask"}


def test_clean_has_no_findings():
    result = run_audit(*load("clean"))
    assert result["findings"] == [] and result["total_impact"] == 0


def test_excess_units_and_balance():
    bill, eob = load("clean")
    bill["lines"][0]["units"] = 3
    bill["lines"][0]["patient_owed"] = 90
    bill["patient_balance"] = 150
    rules = {f["rule"] for f in run_audit(bill, eob)["findings"]}
    assert "excess_units" in rules
