import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import Settings
from tests.test_translate import FnLLM, good

SAMPLES = Path(__file__).parent.parent / "data" / "samples"


@pytest.fixture(autouse=True)
def _no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def client():
    with TestClient(create_app(Settings())) as c:
        yield c


def start(client, sample="overcharge"):
    r = client.post("/cases", data={"sample": sample})
    assert r.status_code == 200, r.text
    return r.json()


def confirmed_audit(client, sample="overcharge", **params):
    cid = start(client, sample)["case_id"]
    assert client.post(f"/cases/{cid}/confirm").status_code == 200
    r = client.post(f"/cases/{cid}/audit", params=params)
    assert r.status_code == 200, r.text
    return cid, r.json()


def test_config_lists_languages_and_samples(client):
    c = client.get("/config").json()
    assert {l["code"] for l in c["languages"]} >= {"en", "es", "mn"} and "overcharge" in c["samples"]
    assert c["model_available"] is False and len(c["suggested_questions"]) == 6


def test_sample_flow_totals_412_with_evidence(client):
    _cid, a = confirmed_audit(client)
    assert a["total_impact"] == 412.0 and len(a["findings"]) == 3 and not a["no_errors"]
    for f in a["findings"]:
        assert f["source"] and f["line_ids"] and f["evidence"] and f["explanation"]["headline"]
        assert f["tier_label"] in ("Definite", "Likely", "Worth asking")
    assert a["rules_data"]["ncci"] in ("sample", "cms") and len(a["checked"]) >= 7


def test_clean_and_ask_samples(client):
    _, clean = confirmed_audit(client, "clean")
    assert clean["no_errors"] and clean["total_impact"] == 0 and clean["findings"] == [] and clean["checked"]
    _, ask = confirmed_audit(client, "ask")
    assert ask["only_questions"] and all(f["tier"] == "ask" for f in ask["findings"]) and ask["total_impact"] == 0
    assert all("worth asking" in " ".join(f["explanation"].values()).lower() for f in ask["findings"])


def test_audit_requires_confirmation(client):
    cid = start(client)["case_id"]
    assert client.post(f"/cases/{cid}/audit").status_code == 409
    assert client.post(f"/cases/{cid}/ask", json={"question": "x"}).status_code == 409


def test_photo_sample_flags_low_confidence_line(client):
    d = start(client, "overcharge_photo")
    assert any(l["needs_review"] for l in d["bill"]["lines"]) and d["warnings"]
    assert client.get(f"/cases/{d['case_id']}/source/0?doc=bill").headers["content-type"] == "image/png"


def test_upload_pdfs_use_text_layer_without_a_model(client):
    files = {"bill": ("bill.pdf", (SAMPLES / "overcharge" / "bill.pdf").read_bytes(), "application/pdf"),
             "eob": ("eob.pdf", (SAMPLES / "overcharge" / "eob.pdf").read_bytes(), "application/pdf")}
    d = client.post("/cases", files=files).json()
    assert d["extractor"] == "text-layer" and len(d["bill"]["lines"]) == 5 and d["warnings"] == []
    assert client.post(f"/cases/{d['case_id']}/confirm").status_code == 200
    assert client.post(f"/cases/{d['case_id']}/audit").json()["total_impact"] == 412.0


def test_photo_upload_without_model_gives_a_plain_message(client):
    img = (SAMPLES / "overcharge_photo" / "bill.jpg").read_bytes()
    r = client.post("/cases", files={"bill": ("b.jpg", img, "image/jpeg"), "eob": ("e.jpg", img, "image/jpeg")})
    assert r.status_code == 422 and "AI reader" in r.json()["detail"]


def test_missing_files_and_bad_inputs(client):
    assert client.post("/cases").status_code == 422
    assert client.post("/cases", data={"sample": "nope"}).status_code == 404
    junk = {"bill": ("x.pdf", b"not a pdf", "application/pdf"), "eob": ("y.pdf", b"nope", "application/pdf")}
    r = client.post("/cases", files=junk)
    assert r.status_code == 422 and "hard to read" in r.json()["detail"]
    assert client.get("/cases/deadbeef").status_code == 404
    cid = start(client)["case_id"]
    assert client.post(f"/cases/{cid}/audit?lang=xx").status_code == 422


def test_edits_reset_confirmation_and_change_findings(client):
    cid = start(client)["case_id"]
    client.post(f"/cases/{cid}/confirm")
    r = client.patch(f"/cases/{cid}/lines", json={"bill_lines": {"B5": {"patient_owed": 40.0}}, "bill": {"patient_balance": 295.0}})
    assert r.status_code == 200 and r.json()["confirmed"] is False
    assert not next(l for l in r.json()["bill"]["lines"] if l["id"] == "B5")["needs_review"]
    assert client.post(f"/cases/{cid}/audit").status_code == 409
    client.post(f"/cases/{cid}/confirm")
    assert client.post(f"/cases/{cid}/audit").json()["total_impact"] == 205.0
    assert client.patch(f"/cases/{cid}/lines", json={"bill_lines": {"B99": {}}}).status_code == 404
    assert client.patch(f"/cases/{cid}/lines", json={"bill_lines": {"B1": {"billed": "abc"}}}).status_code == 422
    added = client.patch(f"/cases/{cid}/lines", json={"add_bill_lines": [
        {"date": "2024-05-01", "code": "85025", "billed": 45.0, "patient_owed": 10.0}], "delete_bill_lines": ["B3"]}).json()
    ids = [l["id"] for l in added["bill"]["lines"]]
    assert "B3" not in ids and "B6" in ids


def test_manual_entry_fallback(client):
    body = {"bill": {"patient_balance": 20.0, "lines": [{"id": "B1", "date": "2024-01-02", "code": "99213", "billed": 100.0, "patient_owed": 20.0}]},
            "eob": {"lines": [{"id": "E1", "date": "2024-01-02", "code": "99213", "allowed": 60.0, "plan_paid": 40.0, "patient_resp": 20.0}]}}
    cid = client.post("/cases/manual", json=body).json()["case_id"]
    client.post(f"/cases/{cid}/confirm")
    assert client.post(f"/cases/{cid}/audit").json()["no_errors"]
    assert client.post("/cases/manual", json={"bill": {}, "eob": {}}).status_code == 422


def test_sse_streams_progress_then_result(client):
    with client.stream("POST", "/cases?stream=1", data={"sample": "clean"}) as r:
        text = "".join(r.iter_text())
    events = [b.split("\n")[0] for b in text.strip().split("\n\n")]
    assert events[0] == "event: progress" and events[-1] == "event: result" and "Reading your bill" in text
    cid = json.loads(text.strip().split("\n\n")[-1].split("data: ")[1])["case_id"]
    client.post(f"/cases/{cid}/confirm")
    with client.stream("POST", f"/cases/{cid}/audit?stream=1") as r:
        text = "".join(r.iter_text())
    assert "Checking billing rules" in text and "Writing explanations" in text and text.rstrip().endswith("}")


def test_ask_english_and_deferral(client):
    cid, _ = confirmed_audit(client)
    a = client.post(f"/cases/{cid}/ask", json={"question": "How much do I owe?", "language": "en"}).json()
    assert not a["deferred"] and "$412.00" in a["answer"] and a["citations"]
    d = client.post(f"/cases/{cid}/ask", json={"question": "Will my insurance cover surgery?", "language": "en"}).json()
    assert d["deferred"]
    assert client.post(f"/cases/{cid}/ask", json={"question": "x", "language": "zz"}).status_code == 422


def test_spanish_end_to_end_with_mocked_model():
    def fn(system, user, tool, n):
        if tool == "write_explanation":
            return {}
        if tool == "to_english" and "[[" not in user:
            return {"english": "How much do I owe?"}
        return good(system, user, tool, n)
    from extraction.cached import CachedExtractor
    cached = CachedExtractor(json.loads((SAMPLES / "overcharge" / "extraction.json").read_text()))
    with TestClient(create_app(Settings(), llm=FnLLM(fn), extractor=cached)) as c:
        cid, a = confirmed_audit(c, lang="es")
        f0 = a["findings"][0]
        assert f0["translated"]["headline"] != f0["explanation"]["headline"] and "[[" not in f0["translated"]["headline"]
        assert f0["explanation_source"] == "fallback" and not f0["translation_notice"]
        ans = c.post(f"/cases/{cid}/ask", json={"question": "¿Cuánto debo?", "language": "es"}).json()
        assert ans["verified"] and ans["answer"] != ans["answer_en"] and "$412.00" in ans["answer"]
        lt = c.get(f"/cases/{cid}/letter", params={"lang": "es"}).json()
        assert lt["segments"] and all("$412.00" in s["translated"] for s in lt["segments"] if s["section"] == "total")


def test_letter_formats_and_user_fields(client):
    cid, _ = confirmed_audit(client)
    j = client.get(f"/cases/{cid}/letter", params={"name": "Ana Diaz", "address": "1 Main St"}).json()
    assert j["total"] == 412.0 and j["rows"] == 3 and "Ana Diaz" in j["english"] and j["segments"] == []
    pdf = client.get(f"/cases/{cid}/letter", params={"format": "pdf"})
    assert pdf.content[:4] == b"%PDF" and "attachment" in pdf.headers["content-disposition"]
    txt = client.get(f"/cases/{cid}/letter", params={"format": "txt"})
    assert "Total amount in question: $412.00" in txt.text
    assert client.get(f"/cases/{cid}/letter?format=docx").status_code == 422


def test_delete_wipes_case_and_ttl_sweep(client):
    cid = start(client)["case_id"]
    assert client.delete(f"/cases/{cid}").json() == {"deleted": True}
    assert client.get(f"/cases/{cid}").status_code == 404 and client.delete(f"/cases/{cid}").status_code == 404
    other = start(client)["case_id"]
    store = client.app.state.store
    assert store.sweep(ttl=3600) == 0 and len(store) == 1
    assert store.sweep(ttl=3600, now=time.time() + 7200) == 1
    assert client.get(f"/cases/{other}").status_code == 404


def test_demo_mode_never_uses_a_model():
    class Boom:
        def complete_tool(self, *a):
            raise AssertionError("model must not be called in DEMO_MODE")
    with TestClient(create_app(Settings(demo_mode=True), llm=Boom())) as c:
        cid, a = confirmed_audit(c)
        assert a["total_impact"] == 412.0
        assert c.post(f"/cases/{cid}/ask", json={"question": "What is an EOB?", "language": "en"}).status_code == 200


def test_double_audit_request_does_not_double_count(client):
    from concurrent.futures import ThreadPoolExecutor
    cid = start(client)["case_id"]
    client.post(f"/cases/{cid}/confirm")
    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(lambda _: client.post(f"/cases/{cid}/audit").json(), range(8)))
    assert all(r["total_impact"] == 412.0 and len(r["findings"]) == 3 for r in results)
