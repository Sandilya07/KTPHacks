"""Data contracts (PLAN.md section 4). Import these everywhere; never redefine them."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

Tier = Literal["definite", "likely", "ask"]
EobStatus = Literal["processed", "denied-duplicate", "denied-bundled", "denied-other"]


class Source(BaseModel):
    """Where a line was read from: page number (0-based) and bbox in page coordinates."""

    page: int
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1


class _Line(BaseModel):
    id: str = ""
    date: str  # ISO yyyy-mm-dd
    code: str
    modifiers: list[str] = Field(default_factory=list)
    source: Source | None = None
    # confidence (0 to 1) per field group, e.g. {"code": .9, "amounts": .7}
    confidence: dict[str, float] = Field(default_factory=dict)
    needs_review: bool = False

    @property
    def min_confidence(self) -> float:
        return min(self.confidence.values(), default=1.0)


class BillLine(_Line):
    description: str = ""
    units: int = 1
    billed: float
    patient_owed: float


class Bill(BaseModel):
    provider: str = ""
    account_number: str = ""
    patient_balance: float
    lines: list[BillLine]


class EobLine(_Line):
    allowed: float = 0.0
    plan_paid: float = 0.0
    patient_resp: float = 0.0
    status: EobStatus = "processed"
    adjustment_reason: str = ""


class Eob(BaseModel):
    payer: str = ""
    network_status: Literal["in", "out"] = "in"
    total_patient_responsibility: float = 0.0
    lines: list[EobLine]


class Finding(BaseModel):
    id: str
    rule: str
    tier: Tier
    line_ids: list[str]  # every bill and EOB line this finding cites
    impact_line_ids: list[str] = Field(default_factory=list)  # bill lines whose dollars are counted
    impact: float  # dollars; always 0 for tier "ask"
    evidence: str
    source: str  # citation: rule name, code pair or limit used

    @staticmethod
    def make_id(rule: str, line_ids: list[str]) -> str:
        return hashlib.sha1(f"{rule}:{','.join(line_ids)}".encode()).hexdigest()[:10]


class Case(BaseModel):
    case_id: str = ""
    bill: Bill
    eob: Eob
    confirmed: bool = False
    findings: list[Finding] = Field(default_factory=list)
    total_impact: float = 0.0
    language: str = "en"
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
