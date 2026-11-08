import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import Settings
from audit.reconcile import preview_correction, reconciliation
from tests.helpers import bl, case, el, overcharge_case


def test_reconciliation_explains_every_bill_line_and_certainty_totals():
    result = reconciliation(overcharge_case())
    assert result["bill_balance"] == 502 and result["eob_total"] == 90
    assert result["statement_difference"] == 412
    assert len(result["rows"]) == 5 and result["matched_lines"] == 4
    assert result["tiers"]["definite"]["impact"] == 302
    assert result["tiers"]["likely"]["impact"] == 110
    assert sum(tier["impact"] for tier in result["tiers"].values()) == 412
    row = next(row for row in result["rows"] if row["bill_id"] == "B5")
    assert row["eob_id"] == "E4" and row["difference"] == 207 and row["match_basis"] == "exact"


def test_missing_insurance_total_is_not_presented_as_zero():
    sample = case([bl("B1")], [el("E1")])
    assert reconciliation(sample)["eob_total"] is None
    sample.eob.total_patient_responsibility = 0
    assert reconciliation(sample)["eob_total"] == 0


def test_partial_matches_and_unmatched_insurance_lines_are_visible():
    sample = case([bl("B1", date="2024-01-01"), bl("B2", code="93000", mods=["76"])],
                  [el("E1", date="2024-02-01"), el("E2", code="93000"), el("E3", code="85025")])
    result = reconciliation(sample)
    assert [row["match_basis"] for row in result["rows"]] == ["code", "date"]
    assert result["unmatched_eob"][0]["id"] == "E3"


def test_correction_preview_reruns_rules_without_modifying_the_original():
    sample = overcharge_case()
    before = sample.model_dump()
    result = preview_correction(sample, "B5", 40)
    assert result["preview_only"]
    assert result["original_impact"] == 412 and result["proposed_impact"] == 205
    assert result["proposed_balance"] == 295 and result["impact_change"] == 207
    assert len(result["resolved_finding_ids"]) == 1 and not result["new_finding_ids"]
    assert sample.model_dump() == before


def test_preview_uses_cents_and_does_not_hide_existing_arithmetic_differences():
    sample = case([bl("B1", owed=20.10)], [el("E1", resp=20.10)], balance=21.10)
    result = preview_correction(sample, "B1", 20.20)
    assert result["proposed_balance"] == 21.20
    assert result["original_impact"] == 1 and result["proposed_impact"] == 1.10
    assert len(result["new_finding_ids"]) == 1  # the extra ten cents now also conflicts with the EOB


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan")])
def test_preview_rejects_invalid_amounts(value):
    with pytest.raises(ValueError):
        preview_correction(overcharge_case(), "B5", value)


def test_preview_rejects_unknown_lines_and_impossible_balances():
    with pytest.raises(ValueError, match="not found"):
        preview_correction(overcharge_case(), "B99", 0)
    with pytest.raises(ValueError, match="negative"):
        preview_correction(case([bl("B1", owed=100)], [el("E1")], balance=0), "B1", 0)


def test_preview_api_preserves_confirmation_results_and_original_documents():
    with TestClient(create_app(Settings(demo_mode=True))) as client:
        cid = client.post("/cases", data={"sample": "overcharge"}).json()["case_id"]
        url = f"/cases/{cid}"
        assert client.post(url + "/preview", json={"line_id": "B5", "patient_owed": 40}).status_code == 409
        client.post(url + "/confirm")
        before = client.get(url).json()
        preview = client.post(url + "/preview", json={"line_id": "B5", "patient_owed": 40})
        assert preview.status_code == 200 and preview.json()["proposed_impact"] == 205
        assert client.get(url).json() == before
        assert client.post(url + "/audit").json()["total_impact"] == 412
        assert client.post(url + "/preview", json={"line_id": "E4", "patient_owed": 40}).status_code == 422
        assert client.post(url + "/preview", json={"line_id": "B5", "patient_owed": -1}).status_code == 422
        client.delete(url)
        assert client.post(url + "/preview", json={"line_id": "B5", "patient_owed": 40}).status_code == 404
