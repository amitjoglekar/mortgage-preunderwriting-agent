"""Claude integration: document classification + extraction, underwriter advice, Q&A.

Calls the Anthropic Messages API directly over HTTPS (no SDK dependency). PDFs are
sent natively as `document` content blocks, so Claude reads layout, tables and
scanned pages without a separate OCR step.

Classification and extraction happen in ONE call: Claude is offered one tool per
document type (record_paystub, record_w2, ...) with that type's field schema and
must call exactly one. The tool it picks is the classification; its arguments are
the extracted fields.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import requests

from . import config
from .guidelines import guideline_context
from .models import DOC_TYPES, tool_schema, validate_fields

log = logging.getLogger("llm")


class LLMError(RuntimeError):
    pass


def _post(payload: dict, timeout: int = 180) -> dict:
    headers = {
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": config.ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    last_err = None
    for attempt in range(4):
        try:
            resp = requests.post(config.ANTHROPIC_API_URL, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as e:  # network trouble
            last_err = str(e)
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 529):
            last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
            time.sleep(int(resp.headers.get("retry-after", 2 ** (attempt + 1))))
            continue
        raise LLMError(f"Anthropic API error {resp.status_code}: {resp.text[:500]}")
    raise LLMError(f"Anthropic API unavailable after retries: {last_err}")


def _tool_input(resp: dict) -> tuple[str, dict]:
    for block in resp.get("content", []):
        if block.get("type") == "tool_use":
            return block["name"], block.get("input") or {}
    raise LLMError("Model did not return a tool call")


def _text(resp: dict) -> str:
    return "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text").strip()


# ------------------------------------------------------------------ classification + extraction
EXTRACT_SYSTEM = """You are the document intake specialist for a mortgage pre-underwriting team that sells conventional loans to Fannie Mae.

For the document you receive:
1. Decide which document type it is, and call the matching record_* tool exactly once. If it is none of the supported types (e.g. a purchase contract, ID, tax return, letter of explanation), call record_other_document.
2. Fill in every field you can read directly from the document. Rules:
   - Leave a field null if the document does not show it. Never infer or invent values.
   - Dates as YYYY-MM-DD. Money as plain numbers (no $ or commas). Percent as a number (6.5 for 6.5%).
   - Record only the last 4 digits of any SSN or account number.
   - For lists (assets, liabilities, tradelines, deposits) include every row shown.
   - For the URLA, map the 'Loan Purpose' section to purchase / limited_cash_out_refinance / cash_out_refinance and occupancy to primary_residence / second_home / investment.
3. Set classification_confidence (0-1) and a one-sentence classification_rationale."""


def _extraction_tools() -> list[dict]:
    tools = []
    for key, meta in DOC_TYPES.items():
        tools.append({
            "name": f"record_{key}",
            "description": f"Record a {meta['label']}. {meta['hint']}",
            "input_schema": tool_schema(key),
        })
    tools.append({
        "name": "record_other_document",
        "description": "Use when the document is not one of the supported types.",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_description": {"type": "string", "description": "What the document appears to be"},
                "classification_confidence": {"type": "number"},
                "classification_rationale": {"type": "string"},
            },
            "required": ["document_description", "classification_confidence", "classification_rationale"],
        },
    })
    return tools


def classify_and_extract(pdf_bytes: bytes, filename: str, force_type: str | None = None) -> dict:
    """Classify + extract. `force_type` (set when an underwriter corrects the type) skips classification."""
    tools = _extraction_tools()
    tool_choice: dict = {"type": "any"}
    if force_type:
        name = "record_other_document" if force_type == "other" else f"record_{force_type}"
        tools = [t for t in tools if t["name"] == name]
        tool_choice = {"type": "tool", "name": name}
    payload = {
        "model": config.ANTHROPIC_MODEL,
        "max_tokens": 8000,
        "system": EXTRACT_SYSTEM,
        "tools": tools,
        "tool_choice": tool_choice,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf",
                            "data": base64.standard_b64encode(pdf_bytes).decode()},
                 "title": filename},
                {"type": "text", "text": f"File name: {filename}. Classify this document and extract its data."},
            ],
        }],
    }
    resp = _post(payload)
    name, data = _tool_input(resp)
    confidence = float(data.pop("classification_confidence", 0) or 0)
    rationale = data.pop("classification_rationale", "")
    doc_type = name.removeprefix("record_")
    if doc_type == "other_document":
        return {"doc_type": "other", "confidence": confidence, "rationale": rationale,
                "fields": {"document_description": data.get("document_description")},
                "usage": resp.get("usage", {}), "engine": f"claude:{config.ANTHROPIC_MODEL}"}
    if doc_type not in DOC_TYPES:
        raise LLMError(f"Unknown tool returned: {name}")
    return {"doc_type": doc_type, "confidence": confidence, "rationale": rationale,
            "fields": validate_fields(doc_type, data), "usage": resp.get("usage", {}),
            "engine": f"claude:{config.ANTHROPIC_MODEL}"}


# ------------------------------------------------------------------ advisor
ADVISOR_SYSTEM = """You are a senior Fannie Mae conventional-loan underwriter acting as a pre-underwriting advisor to a human underwriter.

You receive: the extracted loan data, the output of a deterministic rule engine (each rule cites a Selling Guide section), and summaries of the relevant Fannie Mae Selling Guide sections.

Your job is to advise, not decide. Do NOT re-compute or overturn rule outcomes; explain them, connect them, and tell the underwriter what to do next.
- Ground every point in the data provided. Cite Selling Guide section IDs like [B3-6-02].
- Prioritize: eligibility blockers first, then conditions that could change the decision, then routine conditions.
- Suggest realistic fixes (e.g. pay off a debt, larger down payment, updated documents, MI quote) with the numbers where you can.
- Point out data that looks extracted wrongly or inconsistent between documents.
- Be concise and specific. No generic advice. Never state a final approval; the human underwriter and DU make that call.
Call record_advice exactly once."""

ADVICE_TOOL = {
    "name": "record_advice",
    "description": "Record pre-underwriting advice for the underwriter.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "One-sentence bottom line"},
            "summary": {"type": "string", "description": "3-5 sentence narrative of the file's strengths and risks"},
            "blockers": {"type": "array", "items": {"type": "object", "properties": {
                "issue": {"type": "string"}, "detail": {"type": "string"}, "fix": {"type": "string"},
                "citations": {"type": "array", "items": {"type": "string"}}}, "required": ["issue", "detail"]}},
            "conditions": {"type": "array", "description": "Prior-to-approval / prior-to-closing conditions", "items": {
                "type": "object", "properties": {
                    "condition": {"type": "string"}, "reason": {"type": "string"},
                    "timing": {"type": "string", "enum": ["prior_to_approval", "prior_to_closing", "prior_to_funding"]},
                    "citations": {"type": "array", "items": {"type": "string"}}}, "required": ["condition", "reason"]}},
            "compensating_factors": {"type": "array", "items": {"type": "string"}},
            "questions_for_underwriter": {"type": "array", "items": {"type": "string"}},
            "data_quality_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["headline", "summary", "blockers", "conditions", "compensating_factors", "questions_for_underwriter"],
    },
}


def _compact_docs(documents: list[dict]) -> list[dict]:
    return [{"file": d["filename"], "type": d.get("doc_type"), "confidence": d.get("confidence"), "fields": d.get("fields")}
            for d in documents if d.get("status") == "processed"]


def advise(documents: list[dict], evaluation: dict) -> dict:
    cited = sorted({c for r in evaluation["results"] for c in r.get("citations", [])} | {"B3-6-02", "B3-4.1-01", "ELIG-MATRIX"})
    context = {
        "settings": evaluation["settings"],
        "decision_from_rules": evaluation["decision"],
        "metrics": {k: v for k, v in evaluation["metrics"].items() if k != "debt_schedule"},
        "debt_schedule": evaluation["metrics"].get("debt_schedule"),
        "rule_results": [{k: r[k] for k in ("id", "category", "name", "status", "message", "citations")} for r in evaluation["results"]],
        "documents": _compact_docs(documents),
    }
    payload = {
        "model": config.ANTHROPIC_MODEL,
        "max_tokens": 4000,
        "system": ADVISOR_SYSTEM,
        "tools": [ADVICE_TOOL],
        "tool_choice": {"type": "tool", "name": "record_advice"},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Fannie Mae Selling Guide reference:\n" + guideline_context(cited)},
            {"type": "text", "text": "Loan file:\n" + json.dumps(context, default=str, indent=1)},
            {"type": "text", "text": "Give your pre-underwriting advice."},
        ]}],
    }
    _, data = _tool_input(_post(payload))
    data["engine"] = f"claude:{config.ANTHROPIC_MODEL}"
    return data


# ------------------------------------------------------------------ Q&A
QA_SYSTEM = """You are a Fannie Mae conventional underwriting expert embedded in a pre-underwriting tool. Answer the underwriter's question about this loan file or about Fannie Mae guidelines.
- Use the loan data and rule results provided; quote actual numbers.
- Cite Selling Guide sections like [B3-6-02]. If the provided guideline summaries don't cover the question, say so, give your best understanding of the current Selling Guide, and recommend verifying at selling-guide.fanniemae.com.
- Be direct and brief (under 200 words unless the question needs more). Plain text, short paragraphs or a short list."""


def ask(question: str, documents: list[dict], evaluation: dict, history: list[dict]) -> str:
    context = {
        "settings": evaluation["settings"], "decision": evaluation["decision"],
        "metrics": evaluation["metrics"],
        "rule_results": [{k: r[k] for k in ("id", "name", "status", "message")} for r in evaluation["results"]],
        "documents": _compact_docs(documents),
    }
    messages: list[dict[str, Any]] = [{"role": "user", "content": [
        {"type": "text", "text": "Fannie Mae Selling Guide reference:\n" + guideline_context()},
        {"type": "text", "text": "Loan file:\n" + json.dumps(context, default=str)},
        {"type": "text", "text": "I'll ask questions about this file."}]},
        {"role": "assistant", "content": "Understood. I have the loan file and guideline references. What would you like to know?"}]
    for turn in history[-10:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})
    resp = _post({"model": config.ANTHROPIC_MODEL, "max_tokens": 1500, "system": QA_SYSTEM, "messages": messages})
    return _text(resp)
