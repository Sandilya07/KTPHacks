"""Phase 1 deterministic audit engine.

Plain dicts with the field names from PLAN.md section 4. No LLM is involved:
the rules here alone decide what is a finding. Every finding carries its rule,
tier, line ids, impact, evidence and a citation string.

NCCI_PAIRS and MUE are illustrative samples, replaced by real CMS data in Phase 2.
"""
from __future__ import annotations

import hashlib

# (column1, column2): column 2 is bundled into column 1 when billed together.
NCCI_PAIRS: dict[tuple[str, str], str] = {
    ("80053", "82947"): "Glucose is part of the comprehensive metabolic panel",
    ("80053", "82565"): "Creatinine is part of the comprehensive metabolic panel",
}

# code -> max units per date of service.
MUE: dict[str, int] = {"99213": 1, "99214": 1, "80053": 1, "85025": 1, "82947": 1}


def _fid(rule: str, line_ids: list[str]) -> str:
    return hashlib.sha1(f"{rule}:{','.join(line_ids)}".encode()).hexdigest()[:10]


def _finding(rule, tier, line_ids, impact, evidence, source) -> dict:
    return {
        "id": _fid(rule, line_ids),
        "rule": rule,
        "tier": tier,
        "line_ids": line_ids,
        "impact": round(impact, 2),
        "evidence": evidence,
        "source": source,
    }


def check_duplicates(bill: dict) -> list[dict]:
    findings, seen = [], {}
    for line in bill["lines"]:
        key = (line["code"], line["date"])
        if key in seen:
            first = seen[key]
            findings.append(_finding(
                "duplicate_charge", "definite", [first["id"], line["id"]],
                line["patient_owed"],
                f"Code {line['code']} appears on {line['date']} in lines {first['id']} and {line['id']}.",
                f"Duplicate rule: same code and date of service ({line['code']}, {line['date']})",
            ))
        else:
            seen[key] = line
    return findings


def check_unbundling(bill: dict, skip_ids: set[str] = frozenset()) -> list[dict]:
    findings, flagged_col2 = [], set()
    for a in bill["lines"]:
        for b in bill["lines"]:
            if a is b or a["date"] != b["date"] or a["id"] in skip_ids or b["id"] in flagged_col2:
                continue
            note = NCCI_PAIRS.get((a["code"], b["code"]))
            if note:
                flagged_col2.add(b["id"])
                findings.append(_finding(
                    "unbundling", "likely", [a["id"], b["id"]], b["patient_owed"],
                    f"Codes {a['code']} and {b['code']} were billed on {a['date']}. {note}.",
                    f"NCCI sample pair table: column 1 {a['code']}, column 2 {b['code']}",
                ))
    return findings


def check_excess_units(bill: dict) -> list[dict]:
    findings = []
    for line in bill["lines"]:
        limit = MUE.get(line["code"])
        if limit is not None and line["units"] > limit:
            per_unit = line["patient_owed"] / line["units"]
            findings.append(_finding(
                "excess_units", "likely", [line["id"]],
                per_unit * (line["units"] - limit),
                f"Line {line['id']} bills {line['units']} units of {line['code']}; the limit is {limit}.",
                f"MUE sample table: {line['code']} limit {limit}",
            ))
    return findings


def check_eob_mismatch(bill: dict, eob: dict, skip_ids: set[str]) -> list[dict]:
    findings = []
    for line in bill["lines"]:
        if line["id"] in skip_ids:
            continue
        match = next(
            (e for e in eob["lines"] if e["code"] == line["code"] and e["date"] == line["date"]),
            None,
        )
        if match and line["patient_owed"] > match["patient_resp"]:
            diff = line["patient_owed"] - match["patient_resp"]
            findings.append(_finding(
                "eob_mismatch", "definite", [line["id"], match["id"]], diff,
                f"Bill line {line['id']} asks the patient for {line['patient_owed']:.2f}; "
                f"EOB line {match['id']} says patient responsibility is {match['patient_resp']:.2f}.",
                f"EOB patient responsibility for {line['code']} on {line['date']}",
            ))
    return findings


def check_balance(bill: dict) -> list[dict]:
    total = round(sum(l["patient_owed"] for l in bill["lines"]), 2)
    if round(bill["patient_balance"], 2) != total:
        return [_finding(
            "balance_arithmetic", "definite", [], max(bill["patient_balance"] - total, 0),
            f"Line amounts add up to {total:.2f} but the bill shows a balance of "
            f"{bill['patient_balance']:.2f}.",
            "Arithmetic: sum of patient_owed versus patient_balance",
        )]
    return []


def run_audit(bill: dict, eob: dict) -> dict:
    findings = check_duplicates(bill)
    dup_lines = {f["line_ids"][-1] for f in findings}
    findings += check_unbundling(bill, dup_lines) + check_excess_units(bill)
    # Lines already flagged are excluded from the EOB rule so impact is never double counted.
    flagged = {lid for f in findings for lid in f["line_ids"][-1:]}
    findings += check_eob_mismatch(bill, eob, flagged)
    findings += check_balance(bill)
    return {"findings": findings, "total_impact": round(sum(f["impact"] for f in findings), 2)}
