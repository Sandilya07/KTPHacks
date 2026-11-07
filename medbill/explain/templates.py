"""Deterministic explanations: the fallback when the LLM is unavailable or fails validation.
Every rule type has one, written for a grade 6-8 reader and carrying its tier's required tone."""
from __future__ import annotations

import json
from pathlib import Path

from audit.models import Case, Finding

NOTES: dict[str, str] = {k: v for k, v in json.loads(
    (Path(__file__).parent / "code_notes.json").read_text()).items() if not k.startswith("_")}


def money(v: float) -> str:
    return f"${v:,.2f}"


def code_note(case: Case, code: str) -> str:
    if code in NOTES:
        return NOTES[code]
    desc = next((l.description for l in case.bill.lines if l.code == code and l.description), "")
    return f"Billed as {desc}." if desc else f"Billed under code {code}."


def _lines(case: Case, f: Finding):
    bill = {l.id: l for l in case.bill.lines}
    eob = {l.id: l for l in case.eob.lines}
    return [bill[i] for i in f.line_ids if i in bill], [eob[i] for i in f.line_ids if i in eob]


def fallback_explanation(case: Case, f: Finding) -> dict[str, str]:
    bl, _ = _lines(case, f)
    first = bl[0] if bl else None
    code = first.code if first else ""
    date = first.date if first else ""
    note = code_note(case, code) if code else ""
    impact = money(f.impact)
    ask_close = "It is worth asking the billing office about this."
    likely_close = "This appears to conflict with a billing rule and should be reviewed."

    if f.rule == "duplicate_charge" and f.tier == "definite":
        return {"headline": f"Code {code} was billed twice on {date}",
                "what_happened": f"Your bill lists code {code} two times on {date}, on lines {bl[0].id} and {bl[1].id}. {note} "
                                 f"The second line asks you to pay {money(bl[1].patient_owed)}.",
                "why_it_matters": f"If you received this service once, the second line adds {impact} to what you owe.",
                "what_you_can_do": f"Ask the billing office to remove line {bl[1].id} or show why it was needed."}
    if f.rule == "duplicate_charge":
        return {"headline": f"Code {code} appears twice on {date} with a repeat modifier",
                "what_happened": f"Lines {bl[0].id} and {bl[1].id} both bill code {code} on {date}. One of them carries a "
                                 f"modifier that can mean the service was done again. {note}",
                "why_it_matters": f"Repeat services can be legitimate. {ask_close}",
                "what_you_can_do": "Ask the billing office to confirm the service was done twice. It is worth asking them "
                                   "for the visit notes that show it."}
    if f.rule == "unbundling" and f.tier == "likely":
        c2 = bl[1].code
        return {"headline": f"Codes {code} and {c2} may be billed together by mistake",
                "what_happened": f"Your bill lists code {code} and code {c2} on {date}. {note} {code_note(case, c2)} "
                                 f"Billing rules treat {c2} as normally part of {code}. {likely_close}",
                "why_it_matters": f"If {c2} is already included in {code}, the {impact} charged on line {bl[1].id} may not be owed.",
                "what_you_can_do": f"Ask the billing office to review line {bl[1].id} against the billing rules."}
    if f.rule == "unbundling":
        c2 = bl[1].code
        return {"headline": f"Codes {code} and {c2} were billed together with a modifier",
                "what_happened": f"Your bill lists code {code} and code {c2} on {date}. They are usually billed as one service, "
                                 "but a modifier on the second line can allow both.",
                "why_it_matters": f"The modifier may be correct. {ask_close}",
                "what_you_can_do": f"Ask the billing office why line {bl[1].id} needs the modifier. It is worth asking for the reason."}
    if f.rule == "excess_units":
        return {"headline": f"More units of {code} were billed than usually allowed",
                "what_happened": f"{f.evidence} {note}",
                "why_it_matters": f"{likely_close} The extra units add up to {impact}.",
                "what_you_can_do": "Ask the billing office to review the number of units on this line."}
    if f.rule == "balance_billing":
        return {"headline": "You were charged the full price instead of the insurance rate",
                "what_happened": f"{f.evidence} {note}",
                "why_it_matters": f"Your plan has an agreed allowed amount for this service. The bill asks for {impact} more than your share on the EOB.",
                "what_you_can_do": f"Ask the billing office to change line {f.line_ids[0]} to the amount on your EOB."}
    if f.rule == "eob_mismatch":
        return {"headline": "Your bill is higher than your insurance statement says you owe",
                "what_happened": f"{f.evidence} {note}",
                "why_it_matters": f"Your EOB shows what you owe for this service. The bill asks for {impact} more.",
                "what_you_can_do": f"Ask the billing office to match line {f.line_ids[0]} to your EOB, or explain the difference."}
    if f.rule == "missing_eob_line":
        return {"headline": f"Line {f.line_ids[0]} is not on your insurance statement",
                "what_happened": f"{f.evidence} {note}",
                "why_it_matters": f"Without a matching EOB line, it is unclear what your insurance decided. {ask_close}",
                "what_you_can_do": "Ask the billing office whether this service was sent to your insurance, and for the claim details."}
    if f.rule == "price_outlier":
        return {"headline": f"The price on line {f.line_ids[0]} is high compared with Medicare",
                "what_happened": f"{f.evidence} {note}",
                "why_it_matters": f"A high price is not always wrong. {ask_close}",
                "what_you_can_do": "Ask the billing office how this price was set. It is worth asking for the fee schedule they used."}
    if f.rule == "balance_arithmetic":
        return {"headline": "The bill total does not match its lines",
                "what_happened": f.evidence,
                "why_it_matters": f"The balance should equal the sum of the line amounts. The difference is {impact}.",
                "what_you_can_do": "Ask the billing office for a corrected statement that adds up."}
    return {"headline": "A charge needs a closer look",
            "what_happened": f.evidence,
            "why_it_matters": ask_close if f.tier == "ask" else likely_close if f.tier == "likely" else "This differs from your documents.",
            "what_you_can_do": "Ask the billing office to review this line with you."}
