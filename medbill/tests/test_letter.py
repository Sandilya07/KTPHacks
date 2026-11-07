from datetime import date
from pathlib import Path

from explain.letter import build_letter
from tests.helpers import ScriptedLLM, overcharge_case

SNAP = Path(__file__).parent / "snapshots" / "letter_412.txt"
TODAY = date(2026, 1, 15)


def test_412_letter_lists_exactly_three_lines_and_correct_total():
    letter = build_letter(overcharge_case(), today=TODAY)
    assert len(letter.rows) == 3 and letter.total == 412.0
    assert sorted(r.amount for r in letter.rows) == [95.0, 110.0, 207.0]
    assert "Total amount in question: $412.00" in letter.to_text()


def test_letter_snapshot():
    text = build_letter(overcharge_case(), today=TODAY).to_text()
    if not SNAP.exists():
        SNAP.write_text(text)
    assert text == SNAP.read_text()


def test_letter_has_required_requests_and_no_accusations():
    text = build_letter(overcharge_case(), today=TODAY).to_text().lower()
    for needle in ("corrected statement", "itemized bill", "collections and credit reporting", "within 30 days",
                   "not making an accusation"):
        assert needle in text
    assert not any(w in text for w in ("fraud", "illegal", "scam", "lawsuit"))


def test_llm_paragraphs_validated_and_fallback():
    c = overcharge_case()
    good = {"opening": "Please review my account. The amount in question is $412.00.", "closing": "Thank you for your help."}
    assert build_letter(c, ScriptedLLM(good), today=TODAY).paragraph_source == "llm"
    bad = {"opening": "You owe me $999.00 for this fraud.", "closing": "Thanks."}
    lt = build_letter(c, ScriptedLLM(bad), today=TODAY)
    assert lt.paragraph_source == "fallback" and lt.warnings and "$412.00" in lt.opening
    assert build_letter(c, ScriptedLLM(RuntimeError("down")), today=TODAY).paragraph_source == "fallback"


def test_placeholders_and_user_fields_and_pdf():
    c = overcharge_case()
    assert "[Your name]" in build_letter(c, today=TODAY).to_text()
    t = build_letter(c, user={"name": "Ana Diaz", "address": "1 Main St", "account": "A-77"}, today=TODAY).to_text()
    assert "Ana Diaz" in t and "A-77" in t and "[Your" not in t
    assert build_letter(c, today=TODAY).to_pdf()[:4] == b"%PDF"


def test_clean_case_has_no_disputed_rows():
    import json

    from audit.engine import run_case
    from audit.models import Bill, Case, Eob
    d = json.loads((Path(__file__).parent.parent / "data" / "clean.json").read_text())
    lt = build_letter(run_case(Case(bill=Bill.model_validate(d["bill"]), eob=Eob.model_validate(d["eob"]))), today=TODAY)
    assert lt.rows == [] and lt.total == 0
