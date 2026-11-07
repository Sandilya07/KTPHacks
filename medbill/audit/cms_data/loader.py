"""Loaders that turn CMS files into in-memory lookups.

NCCI: dict keyed by (column1, column2) -> list of edits with effective/deletion dates and the
modifier indicator. An edit applies on a date of service when effective <= dos and the deletion
date is blank or on/after dos (CMS publishes the deletion date as the last day in effect).
MUE: code -> limit + adjudication indicator (MAI). PFS: code -> national non-facility payment.

If no downloaded files exist, a small illustrative SAMPLE table is used and `source == "sample"`.
Say so openly: sample coverage is not real coverage."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import config

CODE_RE = re.compile(r"^[A-Z0-9]{5}$")
DATE8 = re.compile(r"^\d{8}$")


def _iso(d: str) -> str:
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


@dataclass(frozen=True)
class NcciEdit:
    effective: str  # ISO date
    deletion: str | None  # ISO date or None when still active
    indicator: str  # "0", "1" or "9"

    def active_on(self, dos: str) -> bool:
        return self.effective <= dos and (self.deletion is None or dos <= self.deletion)


@dataclass
class NcciTable:
    edits: dict[tuple[str, str], list[NcciEdit]] = field(default_factory=dict)

    def add(self, c1: str, c2: str, edit: NcciEdit) -> None:
        self.edits.setdefault((c1, c2), []).append(edit)

    def lookup(self, c1: str, c2: str, dos: str) -> NcciEdit | None:
        for e in self.edits.get((c1, c2), []):
            if e.active_on(dos):
                return e
        return None

    def __len__(self) -> int:
        return len(self.edits)


@dataclass(frozen=True)
class MueEntry:
    limit: int
    mai: str  # "1" line edit, "2" absolute date-of-service, "3" clinical date-of-service


@dataclass
class CmsData:
    ncci: NcciTable = field(default_factory=NcciTable)
    mue: dict[str, MueEntry] = field(default_factory=dict)
    pfs: dict[str, float] = field(default_factory=dict)
    source: str = "sample"  # "cms" or "sample"
    manifest: dict = field(default_factory=dict)


def parse_ncci(text: str, table: NcciTable | None = None) -> NcciTable:
    """Parse an NCCI PTP file (tab- or comma-delimited, with preamble lines)."""
    table = table if table is not None else NcciTable()
    for raw in text.splitlines():
        delim = "\t" if "\t" in raw else ","
        cells = [c.strip().strip('"') for c in raw.split(delim)]
        if len(cells) < 5 or not (CODE_RE.match(cells[0]) and CODE_RE.match(cells[1])):
            continue
        rest = cells[2:]
        if rest and rest[0] in ("*", ""):
            rest = rest[1:]  # "in existence prior to 1996" flag
        if len(rest) < 3 or not DATE8.match(rest[0]) or rest[2] not in ("0", "1", "9"):
            continue
        deletion = _iso(rest[1]) if DATE8.match(rest[1]) else None
        table.add(cells[0], cells[1], NcciEdit(_iso(rest[0]), deletion, rest[2]))
    return table


def parse_mue(text: str, out: dict[str, MueEntry] | None = None) -> dict[str, MueEntry]:
    out = out if out is not None else {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 3 or not CODE_RE.match(row[0].strip()):
            continue
        try:
            limit = int(row[1].strip())
        except ValueError:
            continue
        mai = row[2].strip()[:1]
        if mai in ("1", "2", "3"):
            out[row[0].strip()] = MueEntry(limit, mai)
    return out


def parse_pfs(text: str, out: dict[str, float] | None = None) -> dict[str, float]:
    """Parse the PPRRVU file: payment = NON-FAC TOTAL RVU x conversion factor (no-modifier rows)."""
    out = out if out is not None else {}
    rows = list(csv.reader(io.StringIO(text)))
    header = next((i for i, r in enumerate(rows) if "HCPCS" in [c.strip().upper() for c in r]), None)
    if header is None:
        return out
    names = [c.strip().upper() for c in rows[header]]
    ix = {n: i for i, n in enumerate(names)}
    nonfac = next((i for n, i in ix.items() if n.startswith("NON-FAC") and "TOTAL" in n), None)
    cf = next((i for n, i in ix.items() if "CONV" in n), None)
    mod = ix.get("MOD")
    if nonfac is None or cf is None:
        return out
    for r in rows[header + 1:]:
        if len(r) <= max(nonfac, cf) or not CODE_RE.match(r[0].strip()):
            continue
        if mod is not None and r[mod].strip():
            continue
        try:
            out[r[0].strip()] = round(float(r[nonfac]) * float(r[cf]), 2)
        except ValueError:
            continue
    return out


def _read(p: Path) -> str:
    return p.read_text(encoding="latin-1")


def load_cms_data(files_dir: Path | None = None) -> CmsData:
    """Load downloaded CMS files; fall back to the sample table when none are present."""
    files_dir = Path(files_dir or config.CMS_FILES_DIR)
    manifest_path = config.CMS_DIR / "manifest.json"
    data = CmsData(source="cms")
    if manifest_path.exists():
        data.manifest = json.loads(manifest_path.read_text())
    for p in sorted(files_dir.glob("ncci*/**/*")):
        if p.suffix.lower() in (".txt", ".csv"):
            parse_ncci(_read(p), data.ncci)
    for p in sorted(files_dir.glob("mue*/**/*.csv")):
        parse_mue(_read(p), data.mue)
    for p in sorted(files_dir.glob("pfs/**/PPRRVU*.csv")) + sorted(files_dir.glob("pfs/**/pprrvu*.csv")):
        parse_pfs(_read(p), data.pfs)
    if not len(data.ncci) and not data.mue:
        return sample_cms_data()
    return data


def sample_cms_data() -> CmsData:
    """Illustrative sample only (documented fallback). Not a substitute for the real files."""
    d = CmsData(source="sample")
    d.ncci.add("80053", "82947", NcciEdit("1996-01-01", None, "1"))
    d.ncci.add("80053", "82565", NcciEdit("1996-01-01", None, "1"))
    for code in ("99213", "99214", "80053", "85025", "82947"):
        d.mue[code] = MueEntry(1, "3")
    return d


_cache: CmsData | None = None


def get_cms_data() -> CmsData:
    global _cache
    if _cache is None:
        _cache = load_cms_data()
    return _cache


def set_cms_data(data: CmsData | None) -> None:
    """Inject data (tests) or reset the cache with None."""
    global _cache
    _cache = data
