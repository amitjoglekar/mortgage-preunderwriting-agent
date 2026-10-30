"""HTTP API + static UI for the pre-underwriting agent.

Run:  uvicorn app.main:app --reload   (then open http://localhost:8000)
"""
from __future__ import annotations

import logging
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import config, guidelines, pipeline, store
from .models import DOC_LABELS, DOC_TYPES, validate_fields

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
SAMPLES = ROOT / "samples"


def err(msg: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=code)


def public_doc(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "stored_path"}


def loan_payload(loan: dict) -> dict:
    evaluation = pipeline.evaluate(loan)
    return {
        "id": loan["id"], "name": loan["name"], "created_at": loan["created_at"], "updated_at": loan["updated_at"],
        "settings": loan["settings"], "documents": [public_doc(d) for d in loan["documents"]],
        "processing": any(d["status"] in ("queued", "processing") for d in loan["documents"]),
        "evaluation": evaluation, "advice": loan.get("advice"), "advice_status": loan.get("advice_status"),
        "advice_error": loan.get("advice_error"), "chat": loan.get("chat", []),
    }


# ----------------------------------------------------------------------------- routes
async def index(request: Request):
    return FileResponse(STATIC / "index.html")


async def status(request: Request):
    return JSONResponse({
        "mode": pipeline.engine_mode(), "model": None if config.DEMO_MODE else config.ANTHROPIC_MODEL,
        "doc_types": DOC_LABELS,
        "samples": sorted(p.name for p in SAMPLES.glob("loan_*") if p.is_dir()),
    })


async def list_loans(request: Request):
    out = []
    for loan in store.list_all():
        ev = pipeline.evaluate(loan)
        out.append({"id": loan["id"], "name": loan["name"], "created_at": loan["created_at"],
                    "documents": len(loan["documents"]), "decision": ev["decision"], "borrower": ev["borrower"]})
    return JSONResponse(out)


async def create_loan(request: Request):
    body = await request.json() if await request.body() else {}
    loan = store.create((body.get("name") or "").strip()[:120] or "New loan file")
    return JSONResponse(loan_payload(loan), status_code=201)


async def get_loan(request: Request):
    try:
        return JSONResponse(loan_payload(store.get(request.path_params["loan_id"])))
    except KeyError:
        return err("Loan not found", 404)


async def patch_loan(request: Request):
    body = await request.json()
    loan_id = request.path_params["loan_id"]

    def fn(loan):
        if "name" in body:
            loan["name"] = str(body["name"]).strip()[:120] or loan["name"]
        s = body.get("settings") or {}
        if s.get("underwriting_method") in ("du", "manual"):
            loan["settings"]["underwriting_method"] = s["underwriting_method"]
        if s.get("note_date"):
            loan["settings"]["note_date"] = str(s["note_date"])[:10]
        if s and loan.get("advice"):
            loan["advice_status"] = "stale"
    try:
        return JSONResponse(loan_payload(store.update(loan_id, fn)))
    except KeyError:
        return err("Loan not found", 404)


async def delete_loan(request: Request):
    store.delete(request.path_params["loan_id"])
    return JSONResponse({"ok": True})


async def upload(request: Request):
    loan_id = request.path_params["loan_id"]
    try:
        store.get(loan_id)
    except KeyError:
        return err("Loan not found", 404)
    form = await request.form(max_files=50, max_part_size=config.MAX_UPLOAD_MB * 1024 * 1024)
    accepted, rejected = [], []
    for f in form.getlist("files"):
        content = await f.read()
        name = Path(f.filename or "document.pdf").name
        if not content.startswith(b"%PDF"):
            rejected.append({"filename": name, "reason": "Not a PDF"})
            continue
        doc = store.add_document(loan_id, name, content)
        pipeline.submit(loan_id, doc["id"])
        accepted.append(public_doc(doc))
    return JSONResponse({"accepted": accepted, "rejected": rejected}, status_code=202)


async def patch_document(request: Request):
    loan_id, doc_id = request.path_params["loan_id"], request.path_params["doc_id"]
    body = await request.json()
    try:
        loan = store.get(loan_id)
        doc = store.find_doc(loan, doc_id)
    except KeyError:
        return err("Not found", 404)
    if "doc_type" in body:
        t = body["doc_type"]
        if t not in DOC_TYPES and t != "other":
            return err("Unknown document type")
        pipeline.submit(loan_id, doc_id, force_type=t)
        return JSONResponse({"ok": True, "reprocessing": True}, status_code=202)
    if "fields" in body:
        if doc.get("doc_type") not in DOC_TYPES:
            return err("Only classified documents can be edited")
        try:
            merged = validate_fields(doc["doc_type"], {**doc.get("fields", {}), **body["fields"]})
        except Exception as e:  # noqa: BLE001
            return err(f"Invalid value: {e}")

        def fn(loan):
            d = store.find_doc(loan, doc_id)
            d["fields"], d["edited"] = merged, True
            if loan.get("advice"):
                loan["advice_status"] = "stale"
        return JSONResponse(loan_payload(store.update(loan_id, fn)))
    return err("Nothing to update")


async def delete_document(request: Request):
    loan_id, doc_id = request.path_params["loan_id"], request.path_params["doc_id"]

    def fn(loan):
        d = store.find_doc(loan, doc_id)
        Path(d["stored_path"]).unlink(missing_ok=True)
        loan["documents"] = [x for x in loan["documents"] if x["id"] != doc_id]
        if loan.get("advice"):
            loan["advice_status"] = "stale"
    try:
        return JSONResponse(loan_payload(store.update(loan_id, fn)))
    except KeyError:
        return err("Not found", 404)


async def document_file(request: Request):
    try:
        loan = store.get(request.path_params["loan_id"])
        d = store.find_doc(loan, request.path_params["doc_id"])
    except KeyError:
        return err("Not found", 404)
    return FileResponse(d["stored_path"], media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{d["filename"]}"'})


async def advice(request: Request):
    loan_id = request.path_params["loan_id"]
    try:
        store.get(loan_id)
    except KeyError:
        return err("Loan not found", 404)
    loan = await run_in_threadpool(pipeline.generate_advice, loan_id)
    return JSONResponse(loan_payload(loan))


async def ask(request: Request):
    loan_id = request.path_params["loan_id"]
    body = await request.json()
    q = (body.get("question") or "").strip()
    if not q:
        return err("Question is empty")
    try:
        answer = await run_in_threadpool(pipeline.ask, loan_id, q[:2000])
    except KeyError:
        return err("Loan not found", 404)
    except Exception as e:  # noqa: BLE001
        return err(f"Agent error: {e}", 502)
    return JSONResponse({"answer": answer, "chat": store.get(loan_id).get("chat", [])})


async def load_sample(request: Request):
    name = request.path_params["name"]
    folder = SAMPLES / name
    if not folder.is_dir() or not name.startswith("loan_"):
        return err("Sample not found", 404)
    label = {"loan_A_clean": "Sample A — Gonzalez (clean purchase)",
             "loan_B_issues": "Sample B — Thompson (problem file)"}.get(name, name)
    loan = store.create(label)
    for pdf in sorted(folder.glob("*.pdf")):
        doc = store.add_document(loan["id"], pdf.name, pdf.read_bytes())
        pipeline.submit(loan["id"], doc["id"])
    return JSONResponse(loan_payload(store.get(loan["id"])), status_code=201)


async def get_guidelines(request: Request):
    return JSONResponse({"sections": guidelines.GUIDELINES, "thresholds": {
        "conforming_limit_1unit": guidelines.CONFORMING_LIMIT_1UNIT,
        "high_balance_ceiling_1unit": guidelines.HIGH_BALANCE_CEILING_1UNIT,
        "dti_max_du": guidelines.DTI_MAX_DU, "dti_max_manual": guidelines.DTI_MAX_MANUAL,
        "dti_max_manual_with_compensating": guidelines.DTI_MAX_MANUAL_WITH_COMP,
        "min_score_manual_fixed": guidelines.MIN_SCORE_MANUAL_FIXED, "min_score_manual_arm": guidelines.MIN_SCORE_MANUAL_ARM,
        "credit_doc_max_months": guidelines.CREDIT_DOC_MAX_MONTHS,
    }})


routes = [
    Route("/", index),
    Route("/api/status", status),
    Route("/api/guidelines", get_guidelines),
    Route("/api/loans", list_loans, methods=["GET"]),
    Route("/api/loans", create_loan, methods=["POST"]),
    Route("/api/loans/{loan_id}", get_loan, methods=["GET"]),
    Route("/api/loans/{loan_id}", patch_loan, methods=["PATCH"]),
    Route("/api/loans/{loan_id}", delete_loan, methods=["DELETE"]),
    Route("/api/loans/{loan_id}/documents", upload, methods=["POST"]),
    Route("/api/loans/{loan_id}/documents/{doc_id}", patch_document, methods=["PATCH"]),
    Route("/api/loans/{loan_id}/documents/{doc_id}", delete_document, methods=["DELETE"]),
    Route("/api/loans/{loan_id}/documents/{doc_id}/file", document_file),
    Route("/api/loans/{loan_id}/advice", advice, methods=["POST"]),
    Route("/api/loans/{loan_id}/ask", ask, methods=["POST"]),
    Route("/api/samples/{name}", load_sample, methods=["POST"]),
    Mount("/static", StaticFiles(directory=STATIC), name="static"),
]

app = Starlette(routes=routes)
logging.getLogger("app").info("Engine mode: %s", pipeline.engine_mode())
