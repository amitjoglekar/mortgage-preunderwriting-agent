"""Orchestration: classify/extract uploaded PDFs in the background, run rules, produce advice."""
from __future__ import annotations

import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from . import config, offline, rules, store

log = logging.getLogger("pipeline")
_pool = ThreadPoolExecutor(max_workers=config.WORKERS, thread_name_prefix="extract")


def engine_mode() -> str:
    return "demo" if config.DEMO_MODE else "claude"


def _extract(path: str, filename: str, force_type: Optional[str]) -> dict:
    if config.DEMO_MODE:
        result = offline.classify_and_extract(path, filename)
        if force_type and force_type != result["doc_type"]:
            if force_type == "other":
                return {**result, "doc_type": "other", "fields": {}, "rationale": "Set manually by underwriter."}
            text = offline.pdf_text(path)
            from .models import validate_fields
            result = {"doc_type": force_type, "confidence": 1.0, "rationale": "Set manually by underwriter.",
                      "fields": validate_fields(force_type, offline.EXTRACTORS[force_type](text)), "engine": "offline-demo"}
        return result
    from . import llm
    return llm.classify_and_extract(Path(path).read_bytes(), filename, force_type=force_type)


def _process(loan_id: str, doc_id: str, force_type: Optional[str] = None) -> None:
    def start(loan):
        d = store.find_doc(loan, doc_id)
        d["status"], d["error"] = "processing", None
    try:
        loan = store.update(loan_id, start)
        doc = store.find_doc(loan, doc_id)
        result = _extract(doc["stored_path"], doc["filename"], force_type)

        def done(loan):
            d = store.find_doc(loan, doc_id)
            d.update(status="processed", doc_type=result["doc_type"], confidence=result.get("confidence"),
                     rationale=result.get("rationale"), fields=result.get("fields") or {},
                     engine=result.get("engine"), usage=result.get("usage"), edited=False)
            _flag_if_last(loan)
        store.update(loan_id, done)
    except KeyError:
        return  # loan or document deleted meanwhile
    except Exception as e:  # noqa: BLE001
        log.error("Extraction failed for %s/%s: %s", loan_id, doc_id, traceback.format_exc())

        def fail(loan):
            d = store.find_doc(loan, doc_id)
            d.update(status="error", error=str(e)[:500])
            _flag_if_last(loan)
        try:
            store.update(loan_id, fail)
        except KeyError:
            return
    _maybe_autoadvise(loan_id)


def _flag_if_last(loan: dict) -> None:
    """If this was the last pending document, mark advice as generating in the same write,
    so pollers never see a 'done but no memo yet' gap."""
    if not any(d["status"] in ("queued", "processing") for d in loan["documents"]):
        loan["advice_status"] = "generating"


def submit(loan_id: str, doc_id: str, force_type: Optional[str] = None) -> None:
    _pool.submit(_process, loan_id, doc_id, force_type)


def _maybe_autoadvise(loan_id: str) -> None:
    """When the last document finishes, refresh the advisor narrative automatically."""
    try:
        loan = store.get(loan_id)
    except KeyError:
        return
    if any(d["status"] in ("queued", "processing") for d in loan["documents"]):
        return
    if loan.get("advice_status") != "generating":
        return  # another worker already wrote the memo
    generate_advice(loan_id)


def evaluate(loan: dict) -> dict:
    return rules.evaluate(loan["documents"], loan["settings"])


def generate_advice(loan_id: str) -> dict:
    def mark(loan):
        loan["advice_status"], loan["advice_error"] = "generating", None
    loan = store.update(loan_id, mark)
    try:
        evaluation = evaluate(loan)
        if config.DEMO_MODE:
            advice = offline.advise(evaluation)
        else:
            from . import llm
            advice = llm.advise(loan["documents"], evaluation)
        advice["generated_at"] = store.now()

        def ok(loan):
            loan["advice"], loan["advice_status"] = advice, "ready"
        return store.update(loan_id, ok)
    except Exception as e:  # noqa: BLE001
        log.error("Advice failed: %s", traceback.format_exc())

        def fail(loan):
            loan["advice_status"], loan["advice_error"] = "error", str(e)[:500]
        return store.update(loan_id, fail)


def ask(loan_id: str, question: str) -> str:
    loan = store.get(loan_id)
    if config.DEMO_MODE:
        answer = offline.ask(question)
    else:
        from . import llm
        answer = llm.ask(question, loan["documents"], evaluate(loan), loan.get("chat", []))

    def add(loan):
        loan.setdefault("chat", []).extend([
            {"role": "user", "content": question, "at": store.now()},
            {"role": "assistant", "content": answer, "at": store.now()}])
    store.update(loan_id, add)
    return answer
