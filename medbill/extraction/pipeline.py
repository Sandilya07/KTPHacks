"""Extraction pipeline: load -> (preprocess) -> model call -> validate -> second pass -> flag.

Output: a Case-ready Bill, Eob and a list of warnings. Low-confidence or failing lines are flagged
(`needs_review`) so the UI makes the user confirm them; nothing is silently trusted."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from audit.models import Bill, Case, Eob

from .llm import Extractor
from .render import Page, load_pages
from .validate import LOW_CONF, check_totals, make_line, needs_second_pass, parse_money


@dataclass
class DocResult:
    model: Bill | Eob
    warnings: list[str] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)


@dataclass
class ExtractionResult:
    case: Case
    bill_pages: list[Page]
    eob_pages: list[Page]


def _build(kind: str, raw: dict, pages: list[Page], extractor: Extractor, warnings: list[str]):
    printed = parse_money(raw.get("patient_balance" if kind == "bill" else "total_patient_responsibility"))
    lines, failures = [], {}
    for i, rl in enumerate(raw.get("lines", []), 1):
        line, fails = make_line(kind, rl, i)
        lines.append(line)
        failures[line.id] = fails
        warnings.extend(f"{line.id}: {f}" for f in fails)
    if check_totals(kind, lines, printed):
        # We cannot tell which line is wrong: send every line through the second pass.
        for line in lines:
            line.confidence["amounts"] = min(line.confidence.get("amounts", 1.0), LOW_CONF - 0.01)

    by_page = {p.number: p for p in pages}
    for i, line in enumerate(lines):  # second pass: re-crop and re-extract once
        if not needs_second_pass(line, failures[line.id]) or line.source is None:
            continue
        page = by_page.get(line.source.page)
        redo = extractor.reextract_region(kind, page, line.source.bbox) if page else None
        if redo:
            new, new_fails = make_line(kind, redo, i + 1)
            if not new_fails and new.min_confidence >= line.min_confidence:
                lines[i], failures[new.id] = new, new_fails
                warnings[:] = [w for w in warnings if not w.startswith(f"{line.id}:")]
    # Re-check totals on the corrected lines, then flag whatever still fails.
    totals = check_totals(kind, lines, printed)
    warnings.extend(totals)
    for line in lines:
        if line.min_confidence < LOW_CONF or failures[line.id] or totals:
            line.needs_review = True
            if not any(w.startswith(f"{line.id}:") for w in warnings):
                warnings.append(f"{line.id}: please check this line against your document")
    if kind == "bill":
        return Bill(provider=raw.get("provider") or "", account_number=raw.get("account_number") or "",
                    patient_balance=printed or 0.0, lines=lines)
    return Eob(payer=raw.get("payer") or "", network_status=raw.get("network_status") or "in",
               total_patient_responsibility=printed or 0.0, lines=lines)


def extract_document(path: str | Path, kind: str, extractor: Extractor) -> DocResult:
    pages = load_pages(path)
    raw = extractor.extract(kind, pages)
    warnings: list[str] = []
    model = _build(kind, raw, pages, extractor, warnings)
    return DocResult(model, warnings, pages)


def extract_case(bill_path, eob_path, extractor: Extractor) -> ExtractionResult:
    bill = extract_document(bill_path, "bill", extractor)
    eob = extract_document(eob_path, "eob", extractor)
    case = Case(bill=bill.model, eob=eob.model, warnings=bill.warnings + eob.warnings)
    return ExtractionResult(case, bill.pages, eob.pages)
