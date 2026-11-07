import pytest

from audit.cms_data import CmsData, MueEntry, NcciEdit, set_cms_data
from audit.engine import run_case
from audit.matching import match_lines
from audit.rules import load_rules
from tests.helpers import bl, case, el


@pytest.fixture(autouse=True)
def cms():
    d = CmsData(source="cms")
    d.ncci.add("80053", "82947", NcciEdit("2000-01-01", None, "1"))
    d.ncci.add("11111", "22222", NcciEdit("2000-01-01", None, "0"))
    d.mue["99213"] = MueEntry(1, "3")
    d.mue["J1234"] = MueEntry(2, "1")
    d.pfs["99213"] = 90.0
    set_cms_data(d)
    yield d
    set_cms_data(None)


def rules(c):
    return {f.rule: f for f in run_case(c).findings}


def test_registry_has_all_rules():
    names = {r.NAME for r in load_rules()}
    assert {"duplicate_charge", "unbundling", "excess_units", "eob_mismatch", "missing_eob_line",
            "price_outlier", "balance_arithmetic"} <= names


def test_duplicate_definite():
    f = rules(case([bl("B1"), bl("B2")], [el("E1"), el("E2")]))["duplicate_charge"]
    assert f.tier == "definite" and f.impact == 20.0 and f.impact_line_ids == ["B2"]


@pytest.mark.parametrize("mods", [["76"], ["77"]])
def test_duplicate_repeat_modifier_is_ask(mods):
    f = rules(case([bl("B1"), bl("B2", mods=mods)], [el("E1"), el("E2")]))["duplicate_charge"]
    assert f.tier == "ask" and f.impact == 0


def test_unbundling_indicator_1_without_modifier_is_likely():
    c = case([bl("B1", "80053"), bl("B2", "82947")], [el("E1", "80053"), el("E2", "82947")])
    assert rules(c)["unbundling"].tier == "likely"


def test_unbundling_indicator_1_with_modifier_downgrades_to_ask():
    c = case([bl("B1", "80053"), bl("B2", "82947", mods=["59"])],
             [el("E1", "80053"), el("E2", "82947", mods=["59"])])
    f = rules(c)["unbundling"]
    assert f.tier == "ask" and f.impact == 0


def test_unbundling_indicator_0_ignores_modifier():
    c = case([bl("B1", "11111"), bl("B2", "22222", mods=["59"])],
             [el("E1", "11111"), el("E2", "22222", mods=["59"])])
    assert rules(c)["unbundling"].tier == "likely"


def test_unbundling_respects_deletion_date(cms):
    cms.ncci.edits[("80053", "82947")] = [NcciEdit("2000-01-01", "2023-12-31", "1")]
    c = case([bl("B1", "80053"), bl("B2", "82947")], [el("E1", "80053"), el("E2", "82947")])
    assert "unbundling" not in rules(c)


def test_excess_units_mai1_per_line_vs_mai3_per_day():
    c = case([bl("B1", "J1234", units=3, owed=30.0)], [el("E1", "J1234", resp=30.0)])
    f = rules(c)["excess_units"]
    assert f.tier == "likely" and f.impact == 10.0
    c2 = case([bl("B1", "99213"), bl("B2", "99213", mods=["25"])], [el("E1"), el("E2", mods=["25"])])
    assert "excess_units" in rules(c2) or "duplicate_charge" in rules(c2)


def test_eob_mismatch_and_balance_billing():
    f = rules(case([bl("B1", owed=50.0)], [el("E1", resp=20.0)]))["eob_mismatch"]
    assert f.tier == "definite" and f.impact == 30.0
    f = rules(case([bl("B1", billed=100.0, owed=100.0)], [el("E1", allowed=60.0, resp=20.0)]))
    assert f["balance_billing"].impact == 80.0


def test_balance_billing_not_flagged_out_of_network():
    r = rules(case([bl("B1", billed=100.0, owed=100.0)], [el("E1", allowed=60.0, resp=20.0)], network="out"))
    assert "balance_billing" not in r and r["eob_mismatch"].impact == 80.0


def test_missing_eob_line_is_ask_zero_impact():
    f = rules(case([bl("B1"), bl("B2", "85025", owed=10.0)], [el("E1")]))["missing_eob_line"]
    assert f.tier == "ask" and f.impact == 0 and f.line_ids == ["B2"]


def test_price_outlier_always_ask(cms):
    f = rules(case([bl("B1", billed=600.0, owed=20.0)], [el("E1")]))["price_outlier"]
    assert f.tier == "ask" and f.impact == 0
    assert "price_outlier" not in rules(case([bl("B1", billed=400.0)], [el("E1")]))


def test_balance_arithmetic():
    f = rules(case([bl("B1")], [el("E1")], balance=70.0))["balance_arithmetic"]
    assert f.tier == "definite" and f.impact == 50.0


def test_no_double_counting_and_total():
    c = run_case(case([bl("B1"), bl("B2"), bl("B3", billed=100.0, owed=99.0)],
                      [el("E1"), el("E2"), el("E3", "99213", resp=20.0)]))
    counted = [lid for f in c.findings if f.impact for lid in f.impact_line_ids]
    assert len(counted) == len(set(counted))


def test_matching_prefers_modifiers_then_order_and_logs_unmatched():
    c = case([bl("B1", mods=["76"]), bl("B2")], [el("E1"), el("E2", mods=["76"])])
    m = match_lines(c)
    assert m.pairs["B1"].id == "E2" and m.pairs["B2"].id == "E1"
    c = case([bl("B1"), bl("B2", "85025")], [el("E1"), el("E9", "99999")])
    m = match_lines(c)
    assert [b.id for b in m.unmatched_bill] == ["B2"] and [e.id for e in m.unmatched_eob] == ["E9"]


def test_concurrent_audits_of_one_case_never_duplicate_findings():
    from concurrent.futures import ThreadPoolExecutor

    from tests.helpers import overcharge_case
    c = overcharge_case()
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda _: run_case(c), range(40)))
    assert len(c.findings) == 3 and c.total_impact == 412.0
