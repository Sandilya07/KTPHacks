import pymupdf
import pytest
from PIL import Image

from extraction.pipeline import extract_case, extract_document
from extraction.preprocess import estimate_skew, preprocess_photo
from extraction.render import load_pages
from extraction.textlayer import TextLayerExtractor
from extraction.validate import normalize_date, parse_money


def line(i, code="99213", owed=20.0, billed=100.0, conf=None, **kw):
    d = {"page": 0, "bbox": [10, 10 + i * 20, 300, 25 + i * 20], "date": "2024-03-05", "code": code,
         "modifiers": [], "description": "Visit", "units": 1, "billed": billed, "patient_owed": owed,
         "confidence": conf or {"date": .95, "code": .95, "amounts": .95}}
    d.update(kw)
    return d


class FakeExtractor:
    """Mocked LLM: returns canned raw dicts. No network."""

    def __init__(self, raw, redo=None):
        self.raw, self.redo, self.redo_calls = raw, redo, 0

    def extract(self, kind, pages):
        return self.raw

    def reextract_region(self, kind, page, bbox):
        self.redo_calls += 1
        return self.redo


@pytest.fixture
def blank_pdf(tmp_path):
    p = tmp_path / "x.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "hello")
    doc.save(p)
    return p


def test_clean_extraction_has_no_warnings(blank_pdf):
    raw = {"patient_balance": 40.0, "lines": [line(1, owed=30.0), line(2, "85025", owed=10.0)]}
    r = extract_document(blank_pdf, "bill", FakeExtractor(raw))
    assert r.warnings == [] and [l.id for l in r.model.lines] == ["B1", "B2"]
    assert not any(l.needs_review for l in r.model.lines)


def test_validation_failures_lower_confidence_and_warn(blank_pdf):
    bad = line(1, code="ABC", owed=500.0, billed=100.0, date="2099-01-01")
    r = extract_document(blank_pdf, "bill", FakeExtractor({"patient_balance": 500.0, "lines": [bad]}))
    l = r.model.lines[0]
    assert l.needs_review and l.confidence["code"] <= 0.5 and l.confidence["amounts"] <= 0.5
    text = " ".join(r.warnings)
    assert "5-character" in text and "higher than billed" in text and "not plausible" in text


def test_null_values_are_flagged_not_guessed(blank_pdf):
    r = extract_document(blank_pdf, "bill", FakeExtractor({"lines": [line(1, billed=None)]}))
    assert r.model.lines[0].needs_review and any("billed could not be read" in w for w in r.warnings)


def test_totals_mismatch_triggers_second_pass_and_flags(blank_pdf):
    ex = FakeExtractor({"patient_balance": 99.0, "lines": [line(1, owed=30.0)]})
    r = extract_document(blank_pdf, "bill", ex)
    assert ex.redo_calls == 1  # re-extracted once, never more
    assert r.model.lines[0].needs_review and any("does not match the sum" in w for w in r.warnings)


def test_second_pass_fixes_low_confidence_line(blank_pdf):
    weak = line(1, owed=30.0, conf={"date": .95, "code": .5, "amounts": .95})
    fixed = line(1, owed=30.0)
    r = extract_document(blank_pdf, "bill", FakeExtractor({"patient_balance": 30.0, "lines": [weak]}, redo=fixed))
    assert not r.model.lines[0].needs_review and r.warnings == []


def test_second_pass_still_failing_flags_for_review(blank_pdf):
    weak = line(1, owed=30.0, conf={"date": .95, "code": .5, "amounts": .95})
    r = extract_document(blank_pdf, "bill", FakeExtractor({"patient_balance": 30.0, "lines": [weak]}, redo=weak))
    assert r.model.lines[0].needs_review and any(w.startswith("B1:") for w in r.warnings)


def test_extract_case_combines_warnings(blank_pdf):
    bill = {"patient_balance": 20.0, "lines": [line(1)]}
    eob = {"lines": [{"page": 0, "bbox": [0, 0, 5, 5], "date": "2024-03-05", "code": "99213",
                      "allowed": 60.0, "plan_paid": 40.0, "patient_resp": 20.0, "status": "processed",
                      "confidence": {"date": 1, "code": 1, "amounts": 1, "status": 1}}]}

    class Both(FakeExtractor):
        def extract(self, kind, pages):
            return bill if kind == "bill" else eob

    res = extract_case(blank_pdf, blank_pdf, Both({}))
    assert res.case.eob.lines[0].id == "E1" and res.case.warnings == []


def test_helpers():
    assert normalize_date("03/05/2024") == "2024-03-05" and normalize_date("nope") is None
    assert parse_money("$1,234.50") == 1234.5 and parse_money("(12.00)") == -12.0 and parse_money("") is None


def test_text_layer_pdf_roundtrip(tmp_path):
    p = tmp_path / "bill.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    y = 100
    page.insert_text((40, 60), "Provider: Test Clinic")
    page.insert_text((40, 80), "Account: ACCT-9")
    xs = [40, 110, 160, 200, 330, 390, 450]
    for x, h in zip(xs, ["Date", "Code", "Mod", "Description", "Units", "Billed", "Patient Owed"], strict=True):
        page.insert_text((x, y), h)
    for x, v in zip(xs, ["2024-03-05", "99213", "25", "Office visit", "1", "$150.00", "$30.00"], strict=True):
        page.insert_text((x, y + 20), v)
    page.insert_text((40, y + 60), "Patient Balance Due: $30.00")
    doc.save(p)
    raw = TextLayerExtractor().extract("bill", load_pages(p))
    ln = raw["lines"][0]
    assert (ln["code"], ln["modifiers"], ln["billed"], ln["patient_owed"], ln["units"]) == ("99213", ["25"], 150.0, 30.0, 1)
    assert raw["patient_balance"] == 30.0 and raw["account_number"] == "ACCT-9" and raw["provider"] == "Test Clinic"


def test_preprocess_deskews_and_loads_image(tmp_path):
    img = Image.new("RGB", (400, 300), "white")
    for y in range(20, 280, 24):
        for x in range(20, 380):
            if (x // 6) % 2:
                img.putpixel((x, y), (0, 0, 0))
                img.putpixel((x, y + 1), (0, 0, 0))
    tilted = img.rotate(4, expand=True, fillcolor="white")
    assert abs(estimate_skew(tilted) + 4) <= 1.5  # recovers the tilt
    assert preprocess_photo(tilted).size[0] > 0
    f = tmp_path / "p.png"
    tilted.save(f)
    pages = load_pages(f)
    assert len(pages) == 1 and pages[0].scale == 1.0 and not pages[0].has_text_layer
