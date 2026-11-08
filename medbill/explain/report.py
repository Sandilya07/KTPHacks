"""Portable, deterministic evidence packet, including the original source pages.

    Generated in memory from a case snapshot. No LLM calls and no patient files on disk.
"""
from __future__ import annotations

import io
import re
from datetime import UTC, datetime
from html import escape
from typing import TYPE_CHECKING

from audit.cms_data import get_cms_data
from audit.engine import run_case
from audit.reconcile import reconciliation
from audit.rules import load_rules
from .templates import fallback_explanation, money

if TYPE_CHECKING:
    from api.store import Record


def evidence_report(record: Record) -> dict:
    case = run_case(record.case.model_copy(deep=True))
    data = get_cms_data()
    return {
        "version": 1, "case_id": case.case_id, "generated_at": datetime.now(UTC).isoformat(),
        "language": "en", "sample": record.sample, "provider": case.bill.provider,
        "payer": case.eob.payer, "account": case.bill.account_number,
        "total_impact": case.total_impact, "reconciliation": reconciliation(case),
        "findings": [{**finding.model_dump(), "explanation": fallback_explanation(case, finding)}
                     for finding in case.findings],
        "rules_checked": [rule.NAME for rule in load_rules()],
        "rules_data": data.parts or {"all": data.source},
        "limits": ["Potential billing discrepancies are requests for review, not confirmed savings or a final amount due.",
                   "A line match based only on a code or a different modifier needs review against the original documents.",
                   "Some rule tables may be samples; the data sources are listed below. A clean result does not prove every charge is correct.",
                   "Informational only. Not medical or legal advice."],
    }


def report_pdf(data: dict, record: Record) -> bytes:
    from PIL import ImageDraw
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ink, teal, mint = colors.HexColor("#183c49"), colors.HexColor("#137c78"), colors.HexColor("#e5f4ef")
    ss = getSampleStyleSheet()
    body = ParagraphStyle("report-body", parent=ss["BodyText"], fontSize=9, leading=13, textColor=ink, spaceAfter=6)
    small = ParagraphStyle("report-small", parent=body, fontSize=8, leading=11)
    heading = ParagraphStyle("report-heading", parent=body, fontName="Helvetica-Bold", fontSize=15, leading=20, spaceBefore=14)
    title = ParagraphStyle("report-title", parent=heading, fontSize=28, leading=32, spaceBefore=4, spaceAfter=12)
    clean = lambda text: escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(text)))
    p = lambda text, style=body: Paragraph(clean(text), style)
    story = [p("MEDBILL / EVIDENCE REPORT", small), p("Clarity you can take with you.", title),
             p("Synthetic example documents" if data["sample"] else "Document-based billing review", heading),
             p(f"Reference: {data['case_id']} | Prepared: {data['generated_at'][:10]} (UTC)", small),
             p(f"Provider: {data['provider'] or 'Not shown'} | Insurance: {data['payer'] or 'Not shown'}"),
             p(f"Account: {data['account'] or 'Not shown'}"), Spacer(1, 9)]

    def table(rows, widths, header=True):
        rendered = [[p(cell, small) for cell in row] for row in rows]
        result = Table(rendered, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        result.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), mint),
            ("LINEBELOW", (0, 0), (-1, -1), .4, colors.HexColor("#dce7e2")),
        ]))
        return result

    rec = data["reconciliation"]
    story.append(table([["Bill balance", "Insurance stated share", "Amount in question"],
                        [money(rec["bill_balance"]), money(rec["eob_total"]) if rec["eob_total"] is not None else "Not shown", money(data["total_impact"])]],
                       [172, 172, 172]))
    story += [Spacer(1, 8), p(data["limits"][0]), p("Bill and insurance, line by line", heading)]
    comparison = [["Bill / EOB", "Date / code", "Bill asks", "EOB share", "Match"]]
    names = {"exact": "Code, date, modifiers", "date": "Different modifiers: review", "code": "Different dates: review", "unmatched": "No match"}
    for row in rec["rows"]:
        comparison.append([f"{row['bill_id']} / {row['eob_id'] or '-'}", f"{row['date']} / {row['code']}",
                           money(row["bill_owed"]), money(row["eob_responsibility"]) if row["eob_responsibility"] is not None else "Not shown",
                           names[row["match_basis"]]])
    story += [table(comparison, [67, 126, 76, 76, 171]), Spacer(1, 8)]
    if not rec["balance_matches_lines"]:
        story.append(p(f"The bill lines add up to {money(rec['bill_line_total'])}; the stated balance is {money(rec['bill_balance'])}."))
    for row in rec["unmatched_eob"]:
        story.append(p(f"Unmatched insurance line {row['id']}: {row['date']}, code {row['code']}, patient share {money(row['patient_responsibility'])}."))
    story.append(p("Findings and supporting rules", heading))
    if not data["findings"]:
        story.append(p("No discrepancies found by the checks listed below. This is not a guarantee that every charge is correct."))
    for index, finding in enumerate(data["findings"], 1):
        explanation = finding["explanation"]
        story.append(KeepTogether([p(f"{index}. {explanation['headline']}", heading),
                                   p(f"{finding['tier'].upper()} | Amount in question: {money(finding['impact'])}", small)]))
        for label, key in (("What happened", "what_happened"), ("Why it matters", "why_it_matters"), ("Next step", "what_you_can_do")):
            story += [p(label, small), p(explanation[key])]
        story += [p(f"Evidence lines: {', '.join(finding['line_ids']) or 'Bill balance and line total'}", small),
                  p(f"Rule: {finding['source']} | Finding reference: {finding['id']}", small)]
    story += [p("How to use this report", heading),
              p("Compare the highlighted pages with your originals. Ask the billing office to review the specific lines and provide an explanation or corrected statement. Keep this report with your review letter and any written reply."),
              p("Checks and data sources", heading), p(", ".join(data["rules_checked"]), small)]
    for name, source in data["rules_data"].items():
        story.append(p(f"{name.upper()}: {source}" + (" - small sample table; not comprehensive" if source == "sample" else ""), small))
    for limit in data["limits"]:
        story.append(p(limit, small))

    # Copy before annotating so exporting never changes the documents shown in the app.
    cited = {line_id for finding in data["findings"] for line_id in finding["line_ids"]}
    for kind, pages in (("bill", record.bill_pages), ("eob", record.eob_pages)):
        lines = getattr(record.case, kind).lines
        for index, source_page in enumerate(pages):
            story.append(PageBreak())
            story.append(p(f"{'Itemized bill' if kind == 'bill' else 'Insurance statement'} / page {index + 1}", heading))
            selected = [line for line in lines if line.id in cited and line.source and line.source.page == index]
            story.append(p("Highlighted evidence: " + (", ".join(line.id for line in selected) or "No flagged lines on this page"), small))
            image = source_page.image.copy().convert("RGB")
            draw = ImageDraw.Draw(image)
            for line in selected:
                box = tuple(coordinate * source_page.scale for coordinate in line.source.bbox)
                draw.rectangle(box, outline="#137c78", width=max(3, round(source_page.scale * 2)))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)
            factor = min(516 / image.width, 600 / image.height)
            story.append(Image(buffer, width=image.width * factor, height=image.height * factor))
    if not record.bill_pages and not record.eob_pages:
        story.append(p("No source images are available for manually entered documents.", small))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(teal)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(48, 28, "MedBill Auditor | Informational billing review")
        canvas.drawRightString(564, 28, f"Page {doc.page}")
        canvas.restoreState()

    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=letter, rightMargin=48, leftMargin=48, topMargin=40, bottomMargin=48,
                                 title="MedBill Evidence Report", author="MedBill Auditor")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
