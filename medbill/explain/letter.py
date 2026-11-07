"""3B. Dispute letter. The skeleton (table, citations, total, requests) is built deterministically in
code. The LLM may only write a short opening and closing paragraph, validated like explanations.
Output: plain text and PDF (DOCX was cut per the plan's cut line 4). Always English."""
from __future__ import annotations

import io
import json
import textwrap
from dataclasses import dataclass, field
from datetime import date

from audit.matching import match_lines
from audit.models import Case, Finding
from llm import LLMClient

from .templates import money
from .validator import BANNED, facts_for_case, validate_text

PLACEHOLDERS = {"name": "[Your name]", "address": "[Your address]", "account": "[Account number]"}
REQUESTS = [
    "A corrected statement that reflects the review of the lines above.",
    "An itemized bill that lists every charge with its code.",
    "A hold on collections and credit reporting for this account while the review is open.",
    "A written response within 30 days.",
]
NOTE = ("This letter is a request for review. I am not making an accusation, and I understand the "
        "charges above may have an explanation I have not seen.")
LETTER_TOOL = {
    "name": "write_letter_paragraphs",
    "description": "Write a short, polite opening and closing paragraph for a billing review request.",
    "input_schema": {"type": "object", "required": ["opening", "closing"],
                     "properties": {"opening": {"type": "string"}, "closing": {"type": "string"}}},
}
SYSTEM = (
    "You write two short, polite paragraphs for a patient's letter asking a medical billing office to review "
    "their bill. Use ONLY the facts provided; never invent or compute numbers, never cite laws, never accuse "
    "anyone, and never use the words fraud, illegal, scam or lawsuit. The patient is requesting review."
)


@dataclass
class DisputeRow:
    date: str
    code: str
    billed: str
    patient_owed: str
    eob_says: str
    reason: str
    amount: float


@dataclass
class Letter:
    date: str
    sender: dict[str, str]
    recipient: str
    subject: str
    opening: str
    rows: list[DisputeRow]
    total: float
    citations: list[str]
    questions: list[str]
    requests: list[str]
    closing: str
    note: str = NOTE
    paragraph_source: str = "fallback"
    warnings: list[str] = field(default_factory=list)

    # ---- renderers -----------------------------------------------------------------------
    def to_text(self, width: int = 92) -> str:
        w = lambda s, ind="": textwrap.fill(s, width, initial_indent=ind, subsequent_indent=" " * len(ind))
        out = [self.sender["name"], self.sender["address"], "", self.date, "", self.recipient, f"Re: {self.subject}", "",
               w(self.opening), "", "Disputed charges"]
        for i, r in enumerate(self.rows, 1):
            out.append(w(f"{r.date} | code {r.code} | billed {r.billed} | patient owed {r.patient_owed} | "
                         f"EOB says: {r.eob_says} | reason: {r.reason} | amount in question {money(r.amount)}", f"{i}. "))
        out += ["", f"Total amount in question: {money(self.total)}", "", "Rules and limits used"]
        out += [w(c, "- ") for c in self.citations]
        if self.questions:
            out += ["", "Items I would also like explained (no amount disputed)"] + [w(q, "- ") for q in self.questions]
        out += ["", "I am requesting:"] + [w(r, f"{i}. ") for i, r in enumerate(self.requests, 1)]
        out += ["", w(self.closing), "", w(self.note), "", "Sincerely,", self.sender["name"]]
        return "\n".join(out) + "\n"

    def to_pdf(self) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter as page
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        ss = getSampleStyleSheet()
        body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=10, leading=13)
        small = ParagraphStyle("s", parent=body, fontSize=8.5, leading=10.5)
        h = ParagraphStyle("h", parent=body, fontName="Helvetica-Bold", spaceBefore=8)
        esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;")
        story = [Paragraph(esc(self.sender["name"]), body), Paragraph(esc(self.sender["address"]), body), Spacer(1, 10),
                 Paragraph(self.date, body), Spacer(1, 6), Paragraph(esc(self.recipient), body),
                 Paragraph(f"<b>Re: {esc(self.subject)}</b>", body), Spacer(1, 8), Paragraph(esc(self.opening), body),
                 Paragraph("Disputed charges", h)]
        data = [[Paragraph(f"<b>{t}</b>", small) for t in
                 ("Date", "Code", "Billed", "Patient owed", "What the EOB says", "Reason", "In question")]]
        for r in self.rows:
            data.append([Paragraph(esc(c), small) for c in (r.date, r.code, r.billed, r.patient_owed, r.eob_says, r.reason, money(r.amount))])
        t = Table(data, colWidths=[52, 38, 46, 50, 120, 150, 50], repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf3")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [t, Spacer(1, 6), Paragraph(f"<b>Total amount in question: {money(self.total)}</b>", body),
                  Paragraph("Rules and limits used", h)] + [Paragraph("&bull; " + esc(c), small) for c in self.citations]
        if self.questions:
            story += [Paragraph("Items I would also like explained (no amount disputed)", h)] + \
                     [Paragraph("&bull; " + esc(q), small) for q in self.questions]
        story += [Paragraph("I am requesting:", h)] + [Paragraph(f"{i}. {esc(r)}", body) for i, r in enumerate(self.requests, 1)]
        story += [Spacer(1, 8), Paragraph(esc(self.closing), body), Spacer(1, 6), Paragraph(esc(self.note), small),
                  Spacer(1, 10), Paragraph("Sincerely,", body), Paragraph(esc(self.sender["name"]), body)]
        buf = io.BytesIO()
        SimpleDocTemplate(buf, pagesize=page, leftMargin=40, rightMargin=40, topMargin=44, bottomMargin=44).build(story)
        return buf.getvalue()


# ---- deterministic skeleton ------------------------------------------------------------------
def _row(case: Case, f: Finding, matches) -> DisputeRow:
    bill = {l.id: l for l in case.bill.lines}
    line = bill[f.impact_line_ids[0]] if f.impact_line_ids else None
    if line is None:
        return DisputeRow("-", "-", "-", "-", "Not applicable", f.evidence, f.impact)
    e = matches.get(line.id)
    if e is None:
        twin = next((x for x in case.eob.lines if x.code == line.code and x.date == line.date), None)
        eob_says = (f"Lists this service once on this date; patient responsibility {money(twin.patient_resp)}"
                    if twin else "No matching line")
    elif e.status != "processed":
        eob_says = f"{e.status.replace('-', ' ').title()}; patient responsibility {money(e.patient_resp)}"
    else:
        eob_says = f"Allowed {money(e.allowed)}; patient responsibility {money(e.patient_resp)}"
    return DisputeRow(line.date, line.code, money(line.billed), money(line.patient_owed), eob_says, f.evidence, f.impact)


def default_paragraphs(case: Case) -> tuple[str, str]:
    n = sum(1 for f in case.findings if f.impact > 0)
    opening = (f"I am writing to ask your billing department to review my account. After comparing my itemized "
               f"bill with my insurance statement, I found {n} charge{'s' if n != 1 else ''} that I would like you "
               f"to look at. The total amount in question is {money(case.total_impact)}.")
    closing = ("Thank you for your time. I would appreciate a written reply and, if the charges are correct, "
               "a short explanation so I can understand them.")
    return opening, closing


def build_letter(case: Case, llm: LLMClient | None = None, user: dict[str, str] | None = None,
                 today: date | None = None) -> Letter:
    user = user or {}
    matches = match_lines(case).pairs
    disputed = [f for f in case.findings if f.impact > 0]
    asks = [f for f in case.findings if f.impact == 0 and f.tier == "ask"]
    opening, closing = default_paragraphs(case)
    source, warnings = "fallback", []
    if llm is not None and disputed:
        facts = facts_for_case(case)
        payload = json.dumps({"total": case.total_impact, "provider": case.bill.provider,
                              "findings": [{"rule": f.rule, "tier": f.tier, "impact": f.impact, "evidence": f.evidence}
                                           for f in disputed]}, indent=1)
        for _ in range(3):
            try:
                draft = llm.complete_tool(SYSTEM, payload, LETTER_TOOL)
            except Exception as exc:  # noqa: BLE001 - any LLM failure falls back to the fixed paragraphs
                warnings.append(f"letter paragraphs fell back: {exc}")
                break
            text = f"{draft.get('opening', '')} {draft.get('closing', '')}"
            if draft.get("opening") and draft.get("closing") and validate_text(text, facts).ok and not BANNED.search(text):
                opening, closing, source = draft["opening"], draft["closing"], "llm"
                break
        else:
            warnings.append("letter paragraphs failed validation three times; fixed text used")
    return Letter(
        date=(today or date.today()).isoformat(),
        sender={"name": user.get("name") or PLACEHOLDERS["name"], "address": user.get("address") or PLACEHOLDERS["address"]},
        recipient=f"{case.bill.provider or '[Provider]'} - Billing Department",
        subject=f"Request for review of account {user.get('account') or case.bill.account_number or PLACEHOLDERS['account']}",
        opening=opening, rows=[_row(case, f, matches) for f in disputed],
        total=round(sum(f.impact for f in disputed), 2),
        citations=[f"{f.rule.replace('_', ' ')}: {f.source}" for f in disputed],
        questions=[f.evidence for f in asks], requests=list(REQUESTS), closing=closing,
        paragraph_source=source, warnings=warnings,
    )
