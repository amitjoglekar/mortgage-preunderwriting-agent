"""Tests: offline extraction on the samples, rule outcomes, and the Claude request/response contract (mocked).

Run:  python -m pytest -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app import llm, offline, rules
from app.models import DOC_TYPES, tool_schema

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
SETTINGS = {"underwriting_method": "du", "note_date": "2026-11-29"}

EXPECTED_TYPES = {
    "loan_A_clean": {"Gonzalez_1003_application.pdf": "loan_application", "Gonzalez_W2_2025.pdf": "w2",
                     "Gonzalez_appraisal_1004.pdf": "appraisal", "Gonzalez_checking_Sep2026.pdf": "bank_statement",
                     "Gonzalez_credit_report.pdf": "credit_report", "Gonzalez_paystub_Oct.pdf": "paystub",
                     "Gonzalez_savings_Sep2026.pdf": "bank_statement"},
    "loan_B_issues": {"Document (4).pdf": "appraisal", "IMG_2041.pdf": "paystub", "Scan_contract.pdf": "other",
                      "credit_10-03.pdf": "credit_report", "scan_0003.pdf": "loan_application",
                      "scan_0007.pdf": "w2", "statement_july.pdf": "bank_statement"},
}


def load(folder: str) -> list[dict]:
    out = []
    for p in sorted((SAMPLES / folder).glob("*.pdf")):
        r = offline.classify_and_extract(str(p), p.name)
        out.append({"id": p.stem, "filename": p.name, "status": "processed", **r})
    return out


@pytest.fixture(scope="module")
def docs_a():
    return load("loan_A_clean")


@pytest.fixture(scope="module")
def docs_b():
    return load("loan_B_issues")


def by_id(ev):
    return {r["id"]: r for r in ev["results"]}


# ---------------------------------------------------------------- classification / extraction
@pytest.mark.parametrize("folder", list(EXPECTED_TYPES))
def test_classification(folder):
    got = {d["filename"]: d["doc_type"] for d in load(folder)}
    assert got == EXPECTED_TYPES[folder]


def test_extraction_values(docs_a):
    app = next(d for d in docs_a if d["doc_type"] == "loan_application")["fields"]
    assert app["loan_amount"] == 472_500 and app["purchase_price"] == 525_000
    assert app["occupancy"] == "primary_residence" and app["first_time_homebuyer"] is True
    assert len(app["liabilities"]) == 3 and len(app["assets"]) == 2
    cr = next(d for d in docs_a if d["doc_type"] == "credit_report")["fields"]
    assert (cr["score_equifax"], cr["score_experian"], cr["score_transunion"]) == (742, 755, 738)


# ---------------------------------------------------------------- rules
def test_clean_file_meets_checks(docs_a):
    ev = rules.evaluate(docs_a, SETTINGS)
    assert ev["decision"]["code"] == "eligible"
    m = ev["metrics"]
    assert m["qualifying_income"] == pytest.approx(11_250)
    assert m["back_dti"] == pytest.approx(39.72, abs=0.05)
    assert m["ltv"] == pytest.approx(90.0)
    assert m["representative_score"] == 742


def test_manual_mode_tightens(docs_a):
    ev = rules.evaluate(docs_a, {**SETTINGS, "underwriting_method": "manual"})
    r = by_id(ev)
    assert r["DTI-TOTAL"]["status"] == "warn"          # 39.7% > 36% manual
    assert r["DOC-W2-YEARS"]["status"] == "warn"       # manual needs 2 years
    assert r["CR-SCORE"]["status"] == "pass"


def test_problem_file_failures(docs_b):
    ev = rules.evaluate(docs_b, SETTINGS)
    r = by_id(ev)
    assert ev["decision"]["code"] == "ineligible"
    for rid in ("DTI-TOTAL", "COL-LTV", "CR-DEROG-chapter7_bankruptcy", "CR-DECLARATION", "AST-FUNDS", "DOC-AGE"):
        assert r[rid]["status"] == "fail", rid
    for rid in ("DTI-UNDISCLOSED", "AST-LARGE-DEP", "COL-APPR-AGE", "COL-SUBJECT-TO", "COL-MI", "INC-STATED", "INC-EMPLOYMENT"):
        assert r[rid]["status"] == "warn", rid
    # The 6-payment furniture loan is excluded from DTI; the undisclosed Upstart loan is included.
    sched = {row["creditor"]: row for row in ev["metrics"]["debt_schedule"]}
    assert not sched["Ashley Furniture"]["included"]
    assert sched["Upstart Personal Loan"]["included"]
    assert sched["Discover"]["payment"] == pytest.approx(160)  # 5% of balance when no payment reported


def test_note_date_moves_waiting_period(docs_b):
    later = rules.evaluate(docs_b, {**SETTINGS, "note_date": "2027-03-15"})
    assert by_id(later)["CR-DEROG-chapter7_bankruptcy"]["status"] == "pass"


def test_empty_file():
    ev = rules.evaluate([], SETTINGS)
    assert ev["decision"]["code"] == "empty"


def test_offline_advice_has_specific_fix(docs_b):
    ev = rules.evaluate(docs_b, SETTINGS)
    adv = offline.advise(ev)
    dti = next(b for b in adv["blockers"] if b["issue"] == "Total debt-to-income ratio")
    assert "$" in dti["fix"] and "50%" in dti["fix"]


# ---------------------------------------------------------------- Claude contract (mocked HTTP)
def test_tool_schemas_are_self_contained():
    for t in DOC_TYPES:
        s = tool_schema(t)
        assert "$defs" not in str(s) and "$ref" not in str(s)
        assert "classification_confidence" in s["properties"]


def test_claude_classify_extract(monkeypatch):
    captured = {}

    def fake_post(payload, timeout=180):
        captured.update(payload)
        return {"content": [{"type": "tool_use", "name": "record_paystub", "input": {
            "classification_confidence": 0.97, "classification_rationale": "Earnings statement",
            "employee_name": "Pat Doe", "pay_frequency": "biweekly", "annual_salary": 104000, "bogus": 1}}],
            "usage": {"input_tokens": 1000, "output_tokens": 200}}

    monkeypatch.setattr(llm, "_post", fake_post)
    out = llm.classify_and_extract(b"%PDF-1.4 test", "x.pdf")
    assert out["doc_type"] == "paystub" and out["confidence"] == 0.97
    assert out["fields"]["annual_salary"] == 104000 and "bogus" not in out["fields"]
    block = captured["messages"][0]["content"][0]
    assert block["type"] == "document" and block["source"]["media_type"] == "application/pdf"
    assert captured["tool_choice"] == {"type": "any"}
    assert {t["name"] for t in captured["tools"]} >= {"record_paystub", "record_w2", "record_other_document"}


def test_claude_forced_type(monkeypatch):
    captured = {}

    def fake_post(payload, timeout=180):
        captured.update(payload)
        return {"content": [{"type": "tool_use", "name": "record_w2", "input": {
            "classification_confidence": 1, "classification_rationale": "forced", "tax_year": 2025}}]}

    monkeypatch.setattr(llm, "_post", fake_post)
    out = llm.classify_and_extract(b"%PDF", "x.pdf", force_type="w2")
    assert out["doc_type"] == "w2" and captured["tool_choice"] == {"type": "tool", "name": "record_w2"}
    assert len(captured["tools"]) == 1


def test_claude_advise(monkeypatch, docs_b):
    ev = rules.evaluate(docs_b, SETTINGS)
    captured = {}

    def fake_post(payload, timeout=180):
        captured.update(payload)
        return {"content": [{"type": "tool_use", "name": "record_advice", "input": {
            "headline": "Not eligible as structured", "summary": "s", "blockers": [], "conditions": [],
            "compensating_factors": [], "questions_for_underwriter": []}}]}

    monkeypatch.setattr(llm, "_post", fake_post)
    adv = llm.advise(docs_b, ev)
    assert adv["headline"] == "Not eligible as structured"
    text = " ".join(c["text"] for c in captured["messages"][0]["content"])
    assert "B3-6-02" in text and "DTI-TOTAL" in text
