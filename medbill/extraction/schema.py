"""Tool schemas for model extraction. They mirror BillLine/EobLine from audit/models.py.

Every value may be null: the model must return null instead of guessing an unreadable value."""
from __future__ import annotations

_NUM = {"type": ["number", "null"]}
_STR = {"type": ["string", "null"]}
_BBOX = {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4,
         "description": "x0,y0,x1,y1 of the whole row in the image's pixel coordinates"}


def _conf(*groups: str) -> dict:
    return {"type": "object", "properties": {g: {"type": "number", "minimum": 0, "maximum": 1} for g in groups},
            "description": "Your confidence 0-1 for each field group of this line"}


BILL_TOOL = {
    "name": "record_bill",
    "description": "Record the itemized bill exactly as printed. Use null for anything unreadable; never guess.",
    "input_schema": {"type": "object", "required": ["lines"], "properties": {
        "provider": _STR, "account_number": _STR, "patient_balance": _NUM,
        "lines": {"type": "array", "items": {"type": "object", "required": ["page", "bbox"], "properties": {
            "page": {"type": "integer", "description": "0-based page index"}, "bbox": _BBOX,
            "date": {**_STR, "description": "date of service, yyyy-mm-dd"},
            "code": {**_STR, "description": "CPT/HCPCS code, 5 characters"},
            "modifiers": {"type": "array", "items": {"type": "string"}},
            "description": _STR, "units": {"type": ["integer", "null"]},
            "billed": _NUM, "patient_owed": _NUM,
            "confidence": _conf("date", "code", "description", "units", "amounts"),
        }}},
    }},
}

EOB_TOOL = {
    "name": "record_eob",
    "description": "Record the explanation of benefits exactly as printed. Use null for anything unreadable; never guess.",
    "input_schema": {"type": "object", "required": ["lines"], "properties": {
        "payer": _STR, "network_status": {"type": ["string", "null"], "enum": ["in", "out", None]},
        "total_patient_responsibility": _NUM,
        "lines": {"type": "array", "items": {"type": "object", "required": ["page", "bbox"], "properties": {
            "page": {"type": "integer"}, "bbox": _BBOX,
            "date": {**_STR, "description": "yyyy-mm-dd"}, "code": _STR,
            "modifiers": {"type": "array", "items": {"type": "string"}},
            "allowed": _NUM, "plan_paid": _NUM, "patient_resp": _NUM,
            "status": {"type": ["string", "null"],
                       "enum": ["processed", "denied-duplicate", "denied-bundled", "denied-other", None]},
            "adjustment_reason": _STR,
            "confidence": _conf("date", "code", "amounts", "status"),
        }}},
    }},
}

TOOLS = {"bill": BILL_TOOL, "eob": EOB_TOOL}

SYSTEM_PROMPT = (
    "You read scanned or photographed medical bills and explanation-of-benefits (EOB) documents. "
    "Transcribe each line item exactly as printed. Return null for any value that is unreadable or "
    "missing; never guess or infer a value. Give a per-field-group confidence from 0 to 1 and the "
    "bounding box of each line in the image's pixel coordinates. Convert dates to yyyy-mm-dd. "
    "Do not judge whether anything is an error."
)
