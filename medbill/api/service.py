"""Business logic behind the API routes. Routes stay thin; everything here is testable without HTTP."""
from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

from audit.cms_data import get_cms_data
from audit.engine import run_case
from audit.models import Bill, BillLine, Eob, EobLine
from audit.rules import load_rules
from explain.explainer import Explainer
from extraction.cached import CachedExtractor
from extraction.llm import AnthropicExtractor
from extraction.pipeline import extract_case
from extraction.render import IMAGE_SUFFIXES
from extraction.textlayer import TextLayerExtractor
from i18n.demo_cache import load_demo_cache
from i18n.glossary import supported_languages
from i18n.translate import Translator
from llm import LLMClient

from .settings import Settings
from .store import Record

SAMPLES = {"overcharge": "Overcharge (three findings)", "overcharge_photo": "Overcharge, phone photo",
           "clean": "Clean bill", "ask": "Worth asking (careful wording)"}
TIER_LABEL = {"definite": "Definite", "likely": "Likely", "ask": "Worth asking"}
RULE_LABEL = {"duplicate_charge": "Charges billed twice", "unbundling": "Services that should be billed together",
              "excess_units": "Too many units", "eob_mismatch": "Bill versus your insurance statement",
              "balance_billing": "Full price charged instead of the insurance rate", "missing_eob_line": "Charges missing from your EOB",
              "price_outlier": "Prices far above Medicare rates", "balance_arithmetic": "Whether the bill adds up"}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def languages() -> list[dict]:
    from i18n.glossary import load_glossary
    out = [{"code": "en", "name": "English", "speech": "en-US", "reviewed": True}]
    for code in supported_languages():
        g = load_glossary(code)
        out.append({"code": code, "name": g.name, "speech": g.speech_lang, "reviewed": g.reviewed})
    return out


def check_lang(lang: str) -> str:
    if lang != "en" and lang not in supported_languages():
        raise ApiError(422, f"Language '{lang}' is not supported.")
    return lang


def translator_for(llm: LLMClient | None, settings: Settings) -> Translator:
    return Translator(None if settings.demo_mode else llm, cache=load_demo_cache())


def pick_extractor(app_extractor, llm: LLMClient | None, sample: str | None, settings: Settings):
    """Returns (extractor, label). Samples replay their stored extraction in DEMO_MODE or when no model is set up."""
    if sample and (settings.demo_mode or llm is None) and app_extractor is None:
        raw = json.loads((settings.samples_dir / sample / "extraction.json").read_text())
        return CachedExtractor(raw), "demo-sample"
    if app_extractor is not None:
        return app_extractor, "custom"
    if llm is not None:
        return AnthropicExtractor(), "model"
    return TextLayerExtractor(), "text-layer"


def extract_from_bytes(files: dict[str, tuple[str, bytes]], extractor, label: str) -> Record:
    """files: {"bill": (filename, bytes), "eob": (...)}. Temp files live only for this call."""
    if label == "text-layer":
        for name, _ in files.values():
            if Path(name).suffix.lower() in IMAGE_SUFFIXES:
                raise ApiError(422, "Reading photos needs the AI reader, which is not set up here. "
                                    "Try a PDF, or enter the lines by hand.")
    with tempfile.TemporaryDirectory() as td:
        paths = {}
        for kind, (name, data) in files.items():
            p = Path(td) / f"{kind}{Path(name).suffix.lower()}"
            p.write_bytes(data)
            paths[kind] = p
        try:
            res = extract_case(paths["bill"], paths["eob"], extractor)
        except ApiError:
            raise
        except Exception as exc:
            raise ApiError(422, "This file is hard to read. Try again in better light, use a PDF, "
                                f"or enter the lines by hand. ({type(exc).__name__})") from exc
    if not res.case.bill.lines or not res.case.eob.lines:
        raise ApiError(422, "We could not find any charges in that file. Try a clearer photo or enter the lines by hand.")
    return Record(res.case, res.bill_pages, res.eob_pages, extractor=label)


def sample_files(name: str, settings: Settings) -> dict[str, tuple[str, bytes]]:
    d = settings.samples_dir / name
    if name not in SAMPLES or not d.exists():
        raise ApiError(404, "Unknown sample case.")
    pick = lambda stem: next(p for p in sorted(d.iterdir()) if p.stem == stem and p.suffix != ".json")
    return {k: (pick(k).name, pick(k).read_bytes()) for k in ("bill", "eob")}


def _dims(page) -> dict:
    return {"width": page.image.width / page.scale, "height": page.image.height / page.scale}


def case_view(rec: Record) -> dict:
    c = rec.case
    return {"case_id": c.case_id, "confirmed": c.confirmed, "language": c.language, "warnings": c.warnings,
            "extractor": rec.extractor, "sample": rec.sample,
            "bill": c.bill.model_dump(mode="json"), "eob": c.eob.model_dump(mode="json"),
            # page size in the same coordinates as line bounding boxes, so the UI can place highlights
            "pages": {"bill": [_dims(p) for p in rec.bill_pages], "eob": [_dims(p) for p in rec.eob_pages]}}


def page_png(rec: Record, doc: str, page: int) -> bytes:
    pages = rec.bill_pages if doc == "bill" else rec.eob_pages
    if doc not in ("bill", "eob") or not 0 <= page < len(pages):
        raise ApiError(404, "That page does not exist.")
    buf = io.BytesIO()
    pages[page].image.save(buf, format="PNG")
    return buf.getvalue()


# ---- editing ---------------------------------------------------------------------------------------
def _next_id(prefix: str, lines) -> str:
    nums = [int(l.id[1:]) for l in lines if l.id[1:].isdigit()]
    return f"{prefix}{max(nums, default=0) + 1}"


def apply_edits(rec: Record, body: dict) -> None:
    """Apply user corrections. Edited lines are re-validated and count as user-confirmed."""
    c = rec.case
    try:
        bill, eob = c.bill.model_dump(), c.eob.model_dump()
        for key, doc in (("bill", bill), ("eob", eob)):
            doc.update({k: v for k, v in (body.get(key) or {}).items() if k != "lines"})
        for key, doc, prefix in (("bill_lines", bill, "B"), ("eob_lines", eob, "E")):
            lines = doc["lines"]
            for lid, patch in (body.get(key) or {}).items():
                target = next((l for l in lines if l["id"] == lid), None)
                if target is None:
                    raise ApiError(404, f"Line {lid} does not exist.")
                target.update(patch)
                target["needs_review"] = False
                target["confidence"] = {k: 1.0 for k in target["confidence"]} or {"amounts": 1.0}
            gone = set(body.get(f"delete_{key}") or [])
            lines[:] = [l for l in lines if l["id"] not in gone]
            for new in body.get(f"add_{key}") or []:
                cls = BillLine if prefix == "B" else EobLine
                holder = [cls.model_validate(l) for l in lines]
                lines.append({**new, "id": _next_id(prefix, holder), "needs_review": False, "confidence": {"amounts": 1.0}})
        new_bill, new_eob = Bill.model_validate(bill), Eob.model_validate(eob)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(422, f"Those values do not look right: {exc}") from exc
    c.bill, c.eob = new_bill, new_eob
    c.confirmed, c.findings, c.total_impact = False, [], 0.0
    rec.explanations.clear()


# ---- audit -----------------------------------------------------------------------------------------
def audit_payload(rec: Record, llm: LLMClient | None, settings: Settings, lang: str) -> dict:
    case = run_case(rec.case)
    case.language = lang
    explainer = Explainer(None if settings.demo_mode else llm)
    translator = translator_for(llm, settings)
    items = []
    for f in case.findings:
        e = explainer.explain(case, f)
        rec.explanations[f.id] = e
        item = {**f.model_dump(), "tier_label": TIER_LABEL[f.tier],
                "explanation": {k: getattr(e, k) for k in ("headline", "what_happened", "why_it_matters", "what_you_can_do")},
                "explanation_source": e.source, "translated": None, "translation_notice": ""}
        if lang != "en":
            tr = {k: translator.translate(v, lang) for k, v in item["explanation"].items()}
            item["translated"] = {k: t.text for k, t in tr.items()}
            item["translation_notice"] = next((t.notice for t in tr.values() if not t.verified), "")
        items.append(item)
    data = get_cms_data()
    return {"case_id": case.case_id, "total_impact": case.total_impact, "findings": items,
            "no_errors": not case.findings, "only_questions": bool(case.findings) and case.total_impact == 0,
            "checked": [RULE_LABEL.get(r.NAME, r.NAME) for r in load_rules()],
            "rules_data": data.parts or {"all": data.source},
            "explainer": {"total": explainer.stats.total, "llm_ok": explainer.stats.llm_ok,
                          "fallbacks": explainer.stats.fallbacks}}
