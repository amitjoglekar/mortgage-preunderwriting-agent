"""Tiny JSON-file persistence for loan files (one JSON per loan + its uploaded PDFs)."""
from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import config

_locks: dict[str, threading.RLock] = {}
_global = threading.Lock()


def _lock(loan_id: str) -> threading.RLock:
    with _global:
        return _locks.setdefault(loan_id, threading.RLock())


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _path(loan_id: str) -> Path:
    if not loan_id.replace("-", "").isalnum():
        raise KeyError(loan_id)
    return config.LOANS_DIR / f"{loan_id}.json"


def create(name: str) -> dict:
    loan_id = uuid.uuid4().hex[:12]
    loan = {
        "id": loan_id, "name": name or "Untitled loan", "created_at": now(), "updated_at": now(),
        "settings": {"underwriting_method": "du", "note_date": (date.today() + timedelta(days=30)).isoformat()},
        "documents": [], "advice": None, "advice_status": "none", "advice_error": None, "chat": [],
    }
    save(loan)
    return loan


def save(loan: dict) -> None:
    loan["updated_at"] = now()
    p = _path(loan["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(loan, indent=1, default=str))
    tmp.replace(p)


def get(loan_id: str) -> dict:
    p = _path(loan_id)
    if not p.exists():
        raise KeyError(loan_id)
    return json.loads(p.read_text())


def update(loan_id: str, fn: Callable[[dict], None]) -> dict:
    """Read-modify-write under the loan's lock."""
    with _lock(loan_id):
        loan = get(loan_id)
        fn(loan)
        save(loan)
        return loan


def list_all() -> list[dict]:
    loans = []
    for p in config.LOANS_DIR.glob("*.json"):
        try:
            loans.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            continue
    return sorted(loans, key=lambda l: l.get("created_at", ""), reverse=True)


def delete(loan_id: str) -> None:
    with _lock(loan_id):
        _path(loan_id).unlink(missing_ok=True)
        shutil.rmtree(config.UPLOAD_DIR / loan_id, ignore_errors=True)


def add_document(loan_id: str, filename: str, content: bytes) -> dict:
    doc_id = uuid.uuid4().hex[:10]
    folder = config.UPLOAD_DIR / loan_id
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{doc_id}.pdf"
    stored.write_bytes(content)
    doc = {"id": doc_id, "filename": filename, "stored_path": str(stored), "size": len(content),
           "uploaded_at": now(), "status": "queued", "doc_type": None, "confidence": None,
           "rationale": None, "fields": {}, "engine": None, "error": None, "edited": False}

    def fn(loan):
        loan["documents"].append(doc)
        loan["advice_status"] = "stale" if loan.get("advice") else "none"
    update(loan_id, fn)
    return doc


def find_doc(loan: dict, doc_id: str) -> dict:
    for d in loan["documents"]:
        if d["id"] == doc_id:
            return d
    raise KeyError(doc_id)
