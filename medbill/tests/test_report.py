import hashlib

import pymupdf
from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import Settings


def test_evidence_report_is_complete_and_does_not_change_case_or_source_images():
    class NoModel:
        def complete_tool(self, *args):
            raise AssertionError("Export must not need a model")
    with TestClient(create_app(Settings(demo_mode=True), llm=NoModel())) as client:
        cid = client.post("/cases", data={"sample": "overcharge"}).json()["case_id"]
        url = f"/cases/{cid}"
        assert client.get(url + "/report").status_code == 409
        client.post(url + "/confirm")
        before = client.get(url).json()
        source = client.get(url + "/source/0?doc=bill").content
        report = client.get(url + "/report?format=json")
        assert report.status_code == 200 and report.headers["cache-control"] == "no-store"
        data = report.json()
        assert data["total_impact"] == 412 and data["sample"] == "overcharge"
        assert len(data["findings"]) == 3 and len(data["reconciliation"]["rows"]) == 5
        assert data["rules_data"]["ncci"] == "sample"
        pdf = client.get(url + "/report")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        assert "medbill-evidence-report.pdf" in pdf.headers["content-disposition"]
        with pymupdf.open(stream=pdf.content, filetype="pdf") as document:
            text = " ".join(page.get_text() for page in document)
            assert all(value in text for value in ("$412.00", "$502.00", "$90.00", "80053", "B5", "E4", "sample"))
            assert "Synthetic example" in text and "not confirmed savings" in text
            assert len(document) >= 3
            assert sum(len(page.get_images()) for page in document) >= 2
        assert client.get(url).json() == before
        assert hashlib.sha256(client.get(url + "/source/0?doc=bill").content).digest() == hashlib.sha256(source).digest()
        client.delete(url)
        assert client.get(url + "/report").status_code == 404


def test_clean_report_and_untrusted_document_text_are_exportable():
    with TestClient(create_app(Settings(demo_mode=True))) as client:
        cid = client.post("/cases", data={"sample": "clean"}).json()["case_id"]
        url = f"/cases/{cid}"
        client.patch(url + "/lines", json={"bill": {"provider": "Clinic <b> & friends\x01"}})
        client.post(url + "/confirm")
        result = client.get(url + "/report")
        assert result.status_code == 200
        with pymupdf.open(stream=result.content, filetype="pdf") as document:
            text = " ".join(page.get_text() for page in document)
        assert "No discrepancies found" in text and "Clinic <b> & friends" in text
