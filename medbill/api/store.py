"""In-memory case store with a TTL sweep. No PHI is ever written to disk: uploads are parsed in memory
and the temporary files are removed straight after extraction."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from audit.models import Case
from explain.explainer import Explanation
from extraction.render import Page


@dataclass
class Record:
    case: Case
    bill_pages: list[Page] = field(default_factory=list)
    eob_pages: list[Page] = field(default_factory=list)
    explanations: dict[str, Explanation] = field(default_factory=dict)
    sample: str | None = None
    extractor: str = ""
    touched: float = field(default_factory=time.time)


class CaseNotFound(KeyError):
    pass


class CaseStore:
    def __init__(self) -> None:
        self._cases: dict[str, Record] = {}

    def add(self, rec: Record) -> str:
        cid = uuid.uuid4().hex
        rec.case.case_id = cid
        self._cases[cid] = rec
        return cid

    def get(self, cid: str) -> Record:
        rec = self._cases.get(cid)
        if rec is None:
            raise CaseNotFound(cid)
        rec.touched = time.time()
        return rec

    def delete(self, cid: str) -> bool:
        return self._cases.pop(cid, None) is not None

    def sweep(self, ttl: float, now: float | None = None) -> int:
        now = time.time() if now is None else now
        dead = [c for c, r in self._cases.items() if now - r.touched > ttl]
        for c in dead:
            del self._cases[c]
        return len(dead)

    def __len__(self) -> int:
        return len(self._cases)
