"""FastAPI app. Cases live in memory only and are wiped on DELETE or after a TTL. Long operations can
stream progress as server-sent events (add ?stream=1)."""
from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from audit.models import Bill, Case, Eob
from explain.letter import build_letter
from i18n.letter import translate_letter
from i18n.qa import QA, SUGGESTED
from llm import LLMClient, llm_from_env

from . import service
from .service import ApiError
from .settings import Settings
from .store import CaseNotFound, CaseStore, Record

Event = tuple[str, dict]


class EditBody(BaseModel):
    bill: dict | None = None
    eob: dict | None = None
    bill_lines: dict[str, dict] | None = None
    eob_lines: dict[str, dict] | None = None
    delete_bill_lines: list[str] | None = None
    delete_eob_lines: list[str] | None = None
    add_bill_lines: list[dict] | None = None
    add_eob_lines: list[dict] | None = None


class AskBody(BaseModel):
    question: str
    language: str = "auto"


class ManualBody(BaseModel):
    bill: dict
    eob: dict


def sse(events: AsyncIterator[Event]) -> StreamingResponse:
    async def body():
        async for name, data in events:
            yield f"event: {name}\ndata: {json.dumps(data)}\n\n"
    return StreamingResponse(body(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


async def collect(events: AsyncIterator[Event]) -> dict:
    result: dict = {}
    async for name, data in events:
        if name == "error":
            raise HTTPException(data["status"], data["message"])
        if name == "result":
            result = data
    return result


def create_app(settings: Settings | None = None, llm: LLMClient | None = None, extractor=None) -> FastAPI:
    settings = settings or Settings()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        async def sweeper():
            while True:
                await asyncio.sleep(60)
                app.state.store.sweep(settings.ttl_seconds)
        task = asyncio.create_task(sweeper())
        yield
        task.cancel()

    app = FastAPI(title="MedBill Auditor", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])
    app.state.store, app.state.settings, app.state.extractor = CaseStore(), settings, extractor
    app.state.llm = llm if llm is not None else (None if settings.demo_mode else llm_from_env())

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.exception_handler(CaseNotFound)
    async def not_found(_: Request, exc: CaseNotFound):
        return JSONResponse({"detail": "That case was not found. It may have expired."}, status_code=404)

    def rec(cid: str) -> Record:
        return app.state.store.get(cid)

    async def step(name: str, message: str) -> Event:
        await asyncio.sleep(0)  # let the event flush before the blocking work starts
        return "progress", {"step": name, "message": message}

    # ---- config ----------------------------------------------------------------------------------
    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/config")
    def config():
        return {"demo_mode": settings.demo_mode, "model_available": app.state.llm is not None,
                "languages": service.languages(), "samples": service.SAMPLES, "suggested_questions": SUGGESTED,
                "ttl_seconds": settings.ttl_seconds}

    # ---- create / extract --------------------------------------------------------------------------
    async def extraction_events(files, sample: str | None) -> AsyncIterator[Event]:
        try:
            yield await step("reading", "Reading your bill")
            ex, label = service.pick_extractor(app.state.extractor, app.state.llm, sample, settings)
            record = await asyncio.to_thread(service.extract_from_bytes, files, ex, label)
            record.sample = sample
            cid = app.state.store.add(record)
            yield await step("checking_lines", "Checking the lines we read")
            yield "result", service.case_view(record) | {"case_id": cid}
        except ApiError as e:
            yield "error", {"status": e.status, "message": e.message}

    @app.post("/cases")
    async def create_case(bill: UploadFile | None = File(None), eob: UploadFile | None = File(None),  # noqa: B008
                          sample: str | None = Form(None), stream: bool = Query(False)):
        if sample:
            files = service.sample_files(sample, settings)
        else:
            if bill is None or eob is None:
                raise HTTPException(422, "Please add both your bill and your EOB.")
            files = {}
            for kind, up in (("bill", bill), ("eob", eob)):
                data = await up.read()
                if len(data) > settings.max_upload_bytes:
                    raise HTTPException(413, "That file is too large. Please use a file under 15 MB.")
                files[kind] = (up.filename or kind, data)
        events = extraction_events(files, sample)
        return sse(events) if stream else await collect(events)

    @app.post("/cases/manual")
    def manual_case(body: ManualBody):
        try:
            case = Case(bill=Bill.model_validate(body.bill), eob=Eob.model_validate(body.eob))
        except Exception as exc:
            raise HTTPException(422, f"Those values do not look right: {exc}") from exc
        record = Record(case, extractor="manual")
        cid = app.state.store.add(record)
        return service.case_view(record) | {"case_id": cid}

    @app.get("/cases/{cid}")
    def get_case(cid: str):
        return service.case_view(rec(cid))

    # ---- corrections / confirm -----------------------------------------------------------------
    @app.patch("/cases/{cid}/lines")
    def patch_lines(cid: str, body: EditBody):
        r = rec(cid)
        service.apply_edits(r, body.model_dump(exclude_none=True))
        return service.case_view(r)

    @app.post("/cases/{cid}/confirm")
    def confirm(cid: str):
        r = rec(cid)
        if not r.case.bill.lines:
            raise HTTPException(422, "Add at least one charge before continuing.")
        r.case.confirmed = True
        return service.case_view(r)

    # ---- audit -----------------------------------------------------------------------------------
    async def audit_events(cid: str, lang: str) -> AsyncIterator[Event]:
        try:
            r = rec(cid)
            if not r.case.confirmed:
                raise ApiError(409, "Please confirm the lines first, so the audit uses numbers you have checked.")
            yield await step("rules", "Checking billing rules")
            payload = await asyncio.to_thread(service.audit_payload, r, app.state.llm, settings, lang)
            yield await step("explaining", "Writing explanations")
            yield "result", payload
        except ApiError as e:
            yield "error", {"status": e.status, "message": e.message}
        except CaseNotFound:
            yield "error", {"status": 404, "message": "That case was not found. It may have expired."}

    @app.post("/cases/{cid}/audit")
    async def audit(cid: str, lang: str = Query("en"), stream: bool = Query(False)):
        service.check_lang(lang)
        rec(cid)
        events = audit_events(cid, lang)
        return sse(events) if stream else await collect(events)

    # ---- ask -------------------------------------------------------------------------------------
    @app.post("/cases/{cid}/ask")
    async def ask(cid: str, body: AskBody):
        r = rec(cid)
        if not r.case.confirmed:
            raise HTTPException(409, "Please confirm the lines first.")
        if body.language != "auto":
            service.check_lang(body.language)
        if not r.case.findings and not r.explanations:
            from audit.engine import run_case
            run_case(r.case)
        qa = QA(service.translator_for(app.state.llm, settings), None if settings.demo_mode else app.state.llm)
        res = await asyncio.to_thread(qa.ask, r.case, body.question, body.language)
        return {"answer": res.answer, "language": res.language, "kind": res.kind, "citations": res.citations,
                "deferred": res.deferred, "verified": res.verified, "notice": res.notice,
                "answer_en": res.answer_en}

    # ---- letter ----------------------------------------------------------------------------------
    @app.get("/cases/{cid}/letter")
    async def letter(cid: str, lang: str = Query("en"), format: str = Query("json", pattern="^(pdf|txt|json)$"),
                     name: str = "", address: str = "", account: str = ""):
        service.check_lang(lang)
        r = rec(cid)
        if not r.case.confirmed:
            raise HTTPException(409, "Please confirm the lines first.")
        from audit.engine import run_case
        run_case(r.case)
        lt = build_letter(r.case, None if settings.demo_mode else app.state.llm,
                          {"name": name, "address": address, "account": account})
        if format == "pdf":
            return Response(lt.to_pdf(), media_type="application/pdf",
                            headers={"Content-Disposition": 'attachment; filename="billing-review-request.pdf"'})
        if format == "txt":
            return Response(lt.to_text(), media_type="text/plain; charset=utf-8",
                            headers={"Content-Disposition": 'attachment; filename="billing-review-request.txt"'})
        segs = []
        if lang != "en":
            tr = service.translator_for(app.state.llm, settings)
            segs = [s.__dict__ for s in await asyncio.to_thread(translate_letter, lt, tr, lang)]
        return {"english": lt.to_text(), "language": lang, "segments": segs, "total": lt.total,
                "rows": len(lt.rows), "paragraph_source": lt.paragraph_source,
                "note": "The English version is the one to send."}

    # ---- source page / delete ------------------------------------------------------------------------
    @app.get("/cases/{cid}/source/{page}")
    def source(cid: str, page: int, doc: str = Query("bill", pattern="^(bill|eob)$")):
        return Response(service.page_png(rec(cid), doc, page), media_type="image/png",
                        headers={"Cache-Control": "private, max-age=600"})

    @app.delete("/cases/{cid}")
    def delete(cid: str):
        if not app.state.store.delete(cid):
            raise CaseNotFound(cid)
        return {"deleted": True}

    return app


def app_factory() -> FastAPI:
    """Run with: uvicorn api.main:app_factory --factory"""
    return create_app()
