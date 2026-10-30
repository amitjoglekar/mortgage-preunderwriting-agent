"""Offline demo engine: used only when no ANTHROPIC_API_KEY is configured (or DEMO_MODE=1).

It lets the app run end-to-end without network access. Classification is keyword
scoring and extraction is label/regex parsing tuned to text-based PDFs like the
bundled synthetic samples. It is NOT meant for real-world documents (scans,
varied layouts) - that is what the Claude engine is for.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import pdfplumber

from . import guidelines as G
from .models import validate_fields

KEYWORDS = {
    "loan_application": ["uniform residential loan application", "form 1003", "declarations", "loan purpose", "borrower information"],
    "paystub": ["earnings statement", "pay period", "net pay", "year-to-date", "pay date"],
    "w2": ["w-2", "wage and tax statement", "medicare wages", "employer identification number"],
    "appraisal": ["uniform residential appraisal report", "appraised value", "sales comparison", "form 1004", "condition rating"],
    "bank_statement": ["statement period", "beginning balance", "ending balance", "account statement", "transaction detail"],
    "credit_report": ["credit report", "tradelines", "credit scores", "beacon", "public records", "inquiries"],
}


def pdf_text(path: str) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def classify(text: str) -> tuple[str, float, str]:
    low = text.lower()
    scores = {t: sum(1 for k in kws if k in low) for t, kws in KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] < 2:
        return "other", 0.5, "No strong keyword match for a supported document type."
    conf = min(0.55 + 0.1 * scores[best], 0.95)
    hits = [k for k in KEYWORDS[best] if k in low][:3]
    return best, conf, f"Keyword match: {', '.join(hits)}."


# ----------------------------------------------------------------------------- parsing helpers
def to_money(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    m = re.search(r"-?\$?\s*([\d,]+(?:\.\d+)?)", s)
    return float(m.group(1).replace(",", "")) if m else None


def to_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if not m:
        return None
    return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))).date().isoformat()


def to_int(s: Optional[str]) -> Optional[int]:
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else None


def yes_no(s: Optional[str]) -> Optional[bool]:
    if not s:
        return None
    s = s.strip().lower()
    return True if s.startswith("y") else False if s.startswith("n") else None


def kv(text: str, labels: list[str]) -> dict[str, str]:
    """Find 'Label: value' pairs on each line, where a value runs until the next known label."""
    out: dict[str, str] = {}
    pats = sorted(labels, key=len, reverse=True)
    for line in text.splitlines():
        hits = []
        for lab in pats:
            for m in re.finditer(r"(?:(?<=\s)|^)" + re.escape(lab) + r":", line):
                if not any(h[0] <= m.start() < h[1] for h in hits):
                    hits.append((m.start(), m.end(), lab))
        hits.sort()
        for i, (s, e, lab) in enumerate(hits):
            end = hits[i + 1][0] if i + 1 < len(hits) else len(line)
            out.setdefault(lab, line[e:end].strip())
    return out


def last4(s: Optional[str]) -> Optional[str]:
    m = re.findall(r"\d", s or "")
    return "".join(m[-4:]) if len(m) >= 4 else None


# ----------------------------------------------------------------------------- extractors
def ex_paystub(text: str) -> dict:
    f = kv(text, ["Employee", "Employee ID", "Pay Period Start", "Pay Period End", "Pay Date", "Pay Frequency",
                  "Pay Type", "Rate", "Net Pay", "Direct Deposit"])
    rate = f.get("Rate", "")
    d = {
        "employer_name": text.splitlines()[0].strip(),
        "employee_name": f.get("Employee"),
        "pay_period_start": to_date(f.get("Pay Period Start")), "pay_period_end": to_date(f.get("Pay Period End")),
        "pay_date": to_date(f.get("Pay Date")),
        "pay_frequency": (f.get("Pay Frequency") or "").lower() or None,
        "pay_type": (f.get("Pay Type") or "").lower() or None,
        "current_net_pay": to_money(f.get("Net Pay")),
    }
    if "annual" in rate.lower():
        d["annual_salary"] = to_money(rate)
    elif "hour" in rate.lower():
        d["hourly_rate"] = to_money(rate)
    for line in text.splitlines():
        amounts = re.findall(r"\$[\d,]+\.\d{2}", line)
        hours = re.findall(r"(?<!\$)\b(\d{1,3}\.\d{2})\b(?!\d)", line)
        key = line.split(" ")[0].lower()
        if len(amounts) >= 2 and key in ("regular", "overtime", "bonus", "commission", "gross"):
            cur, ytd = to_money(amounts[-2]), to_money(amounts[-1])
            if key == "regular":
                d["current_base_pay"], d["ytd_base_pay"] = cur, ytd
                if hours:
                    d["regular_hours"] = float(hours[0])
            elif key == "gross":
                d["current_gross_pay"], d["ytd_gross_pay"] = cur, ytd
            else:
                d[f"current_{key}"], d[f"ytd_{key}"] = cur, ytd
    return d


def ex_w2(text: str) -> dict:
    d: dict = {}
    for line in text.splitlines():
        low = line.lower()
        if low.startswith("1 wages"):
            d["box1_wages"] = to_money(line.split("compensation")[-1])
        elif low.startswith("5 medicare wages"):
            d["box5_medicare_wages"] = to_money(line.split("tips")[-1])
        elif "social security number" in low:
            d["employee_ssn_last4"] = last4(line)
        elif "employer identification number" in low:
            m = re.search(r"\d{2}-\d{7}", line)
            d["employer_ein"] = m.group() if m else None
        elif "employer's name" in low:
            d["employer_name"] = line.split("ZIP code", 1)[-1].strip().split(",")[0]
        elif low.startswith("e employee's first name"):
            d["employee_name"] = line.split("last name", 1)[-1].strip()
    m = re.search(r"Tax Year:\s*(\d{4})", text) or re.search(r"Statement\s+(\d{4})", text)
    d["tax_year"] = int(m.group(1)) if m else None
    return d


def _section(text: str, start_pat: str, end_pat: str) -> list[str]:
    lines, on = [], False
    for line in text.splitlines():
        if re.search(start_pat, line):
            on = True
            continue
        if on and re.search(end_pat, line):
            break
        if on:
            lines.append(line)
    return lines


LIAB_TYPES = {"installment": "installment", "revolving": "revolving", "mortgage": "mortgage", "auto": "auto",
              "student": "student", "lease": "lease"}


def ex_urla(text: str) -> dict:
    f = kv(text, ["Application Date", "Borrower Name", "Social Security Number", "Date of Birth", "Current Address",
                  "Housing", "Monthly Housing Payment", "First-Time Homebuyer", "Employer Name", "Position or Title",
                  "Start Date", "Years in Line of Work", "Self-Employed", "Base", "Overtime", "Bonus", "Commission",
                  "Other Income", "Total Monthly Income", "Previous Employer", "Months Employed", "Earnest Money Deposit",
                  "Gift Funds", "Loan Purpose", "Loan Amount", "Property Address", "Number of Units",
                  "Property Value / Sales Price", "Occupancy", "Property Type", "Subordinate Financing", "Note Rate",
                  "Loan Term", "Amortization Type", "First Mortgage (P&I)", "Homeowner's Insurance", "Property Taxes",
                  "Mortgage Insurance", "HOA Dues", "Estimated Closing Costs", "Citizenship",
                  "I. Declared bankruptcy within the past 7 years?", "J. Property foreclosed upon in the last 7 years?",
                  "H. Outstanding judgments against you?"])
    purpose = (f.get("Loan Purpose") or "").lower()
    occ = (f.get("Occupancy") or "").lower()
    assets = []
    for line in _section(text, r"^Account Type Financial Institution", r"Earnest Money|^2c\."):
        m = re.match(r"^(\S+)\s+(.+?)\s+(\*+\d{4})\s+(\$[\d,.]+)$", line.strip())
        if m:
            assets.append({"account_type": m.group(1), "institution": m.group(2), "balance": to_money(m.group(4))})
    liabs = []
    for line in _section(text, r"^Creditor Type Unpaid", r"^Section 4"):
        m = re.match(r"^(.+?)\s+(Installment|Revolving|Mortgage|Auto|Student|Lease)\s+(\$[\d,.]+)\s+(\$[\d,.]+)(?:\s+(\d+))?\s+(Yes|No)$", line.strip(), re.I)
        if m:
            liabs.append({"creditor": m.group(1), "liability_type": LIAB_TYPES[m.group(2).lower()],
                          "unpaid_balance": to_money(m.group(3)), "monthly_payment": to_money(m.group(4)),
                          "months_remaining": int(m.group(5)) if m.group(5) else None,
                          "to_be_paid_off": yes_no(m.group(6))})
    return {
        "application_date": to_date(f.get("Application Date")), "borrower_name": f.get("Borrower Name"),
        "borrower_ssn_last4": last4(f.get("Social Security Number")), "borrower_dob": to_date(f.get("Date of Birth")),
        "current_address": f.get("Current Address"),
        "current_housing": (f.get("Housing") or "").lower() or None,
        "current_housing_payment": to_money(f.get("Monthly Housing Payment")),
        "first_time_homebuyer": yes_no(f.get("First-Time Homebuyer")),
        "employer_name": f.get("Employer Name"), "position_title": f.get("Position or Title"),
        "employment_start_date": to_date(f.get("Start Date")),
        "years_in_line_of_work": to_money(f.get("Years in Line of Work")),
        "prior_employer_name": f.get("Previous Employer"), "prior_employment_months": to_int(f.get("Months Employed")),
        "self_employed": yes_no(f.get("Self-Employed")),
        "base_monthly_income": to_money(f.get("Base")), "overtime_monthly_income": to_money(f.get("Overtime")),
        "bonus_monthly_income": to_money(f.get("Bonus")), "commission_monthly_income": to_money(f.get("Commission")),
        "other_monthly_income": to_money(f.get("Other Income")), "total_monthly_income": to_money(f.get("Total Monthly Income")),
        "assets": assets, "liabilities": liabs,
        "earnest_money_deposit": to_money(f.get("Earnest Money Deposit")), "gift_funds": to_money(f.get("Gift Funds")),
        "loan_purpose": "purchase" if "purchase" in purpose else "cash_out_refinance" if "cash" in purpose else
                        "limited_cash_out_refinance" if "refi" in purpose else None,
        "loan_amount": to_money(f.get("Loan Amount")), "property_address": f.get("Property Address"),
        "number_of_units": to_int(f.get("Number of Units")), "purchase_price": to_money(f.get("Property Value / Sales Price")),
        "occupancy": "primary_residence" if "primary" in occ else "second_home" if "second" in occ else
                     "investment" if "invest" in occ else None,
        "property_type": f.get("Property Type"), "subordinate_financing_amount": to_money(f.get("Subordinate Financing")),
        "note_rate_percent": to_money(f.get("Note Rate")), "loan_term_months": to_int(f.get("Loan Term")),
        "amortization_type": "arm" if "adjust" in (f.get("Amortization Type") or "").lower() else "fixed",
        "proposed_principal_interest": to_money(f.get("First Mortgage (P&I)")),
        "proposed_homeowners_insurance": to_money(f.get("Homeowner's Insurance")),
        "proposed_property_taxes": to_money(f.get("Property Taxes")),
        "proposed_mortgage_insurance": to_money(f.get("Mortgage Insurance")),
        "proposed_hoa_dues": to_money(f.get("HOA Dues")),
        "estimated_closing_costs": to_money(f.get("Estimated Closing Costs")),
        "declares_bankruptcy_past_7_years": yes_no(f.get("I. Declared bankruptcy within the past 7 years?")),
        "declares_foreclosure_past_7_years": yes_no(f.get("J. Property foreclosed upon in the last 7 years?")),
        "declares_outstanding_judgments": yes_no(f.get("H. Outstanding judgments against you?")),
        "us_citizen": "citizen" in (f.get("Citizenship") or "").lower() or None,
    }


def ex_appraisal(text: str) -> dict:
    f = kv(text, ["Property Address", "Borrower", "Occupant", "Contract Price", "Date of Contract", "Property Values",
                  "Number of Units", "Year Built", "Gross Living Area", "Condition Rating", "Quality Rating",
                  "FEMA Flood Zone", "Property Type", "Appraised Value of Subject Property", "Effective Date of Appraisal",
                  "Date of Signature and Report", "Appraiser", "Indicated Value by Sales Comparison"])
    low = text.lower()
    made = re.search(r"this appraisal is made (.+?)\.", low)
    made_s = made.group(1) if made else ""
    appraised_as = ("as_is" if "as is" in made_s else "subject_to_repairs" if "repair" in made_s else
                    "subject_to_completion" if "complet" in made_s else "subject_to_inspection" if "inspect" in made_s else None)
    trend = (f.get("Property Values") or "").lower()
    occupant = (f.get("Occupant") or "").lower()
    comps = len(re.findall(r"Comparable \d", text.split("SALES COMPARISON")[-1].splitlines()[1] if "SALES COMPARISON" in text else ""))
    return {
        "form_type": "1004 URAR" if "1004" in text else None,
        "subject_address": f.get("Property Address"), "borrower_name": f.get("Borrower"),
        "occupancy": "owner" if "owner" in occupant else "tenant" if "tenant" in occupant else "vacant" if "vacant" in occupant else None,
        "contract_price": to_money(f.get("Contract Price")), "contract_date": to_date(f.get("Date of Contract")),
        "appraised_value": to_money(f.get("Appraised Value of Subject Property") or f.get("Indicated Value by Sales Comparison")),
        "effective_date": to_date(f.get("Effective Date of Appraisal")),
        "report_signature_date": to_date(f.get("Date of Signature and Report")),
        "condition_rating": f.get("Condition Rating"), "quality_rating": f.get("Quality Rating"),
        "appraised_as": appraised_as, "number_of_units": to_int(f.get("Number of Units")),
        "property_type": f.get("Property Type"), "year_built": to_int(f.get("Year Built")),
        "gross_living_area_sqft": to_money(f.get("Gross Living Area")),
        "neighborhood_value_trend": trend if trend in ("increasing", "stable", "declining") else None,
        "flood_zone": f.get("FEMA Flood Zone"), "appraiser_name": f.get("Appraiser"),
        "comparables_count": comps or None,
    }


def ex_bank(text: str) -> dict:
    f = kv(text, ["Account Holder", "Account Type", "Account Number", "Statement Period", "Beginning Balance", "Ending Balance"])
    period = f.get("Statement Period") or ""
    dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", period)
    year = dates[-1][-4:] if dates else str(datetime.now().year)
    prev = to_money(f.get("Beginning Balance")) or 0.0
    deposits = []
    for line in text.splitlines():
        m = re.match(r"^(\d{2}/\d{2})\s+(.+?)\s+(\$[\d,.]+)\s+(\$[\d,.]+)$", line.strip())
        if m:
            amt, bal = to_money(m.group(3)), to_money(m.group(4))
            if bal > prev:
                deposits.append({"date": to_date(f"{m.group(1)}/{year}"), "amount": amt, "description": m.group(2)})
            prev = bal
    lines = text.splitlines()
    return {
        "institution": lines[0].strip() if lines else None, "account_holder": f.get("Account Holder"),
        "account_type": f.get("Account Type"), "account_last4": last4(f.get("Account Number")),
        "statement_period_start": to_date(dates[0]) if dates else None,
        "statement_period_end": to_date(dates[-1]) if dates else None,
        "beginning_balance": to_money(f.get("Beginning Balance")), "ending_balance": to_money(f.get("Ending Balance")),
        "deposits": deposits,
    }


TL_TYPE = {"auto": "auto", "revolving": "revolving", "student": "student", "installment": "installment",
           "mortgage": "mortgage", "lease": "lease"}


def ex_credit(text: str) -> dict:
    f = kv(text, ["Borrower", "Report Date", "SSN", "Report ID", "Total Inquiries"])
    d: dict = {"borrower_name": f.get("Borrower"), "report_date": to_date(f.get("Report Date")),
               "inquiries_last_120_days": to_int(f.get("Total Inquiries")), "tradelines": [], "derogatory_events": []}
    if d["borrower_name"] and "," in d["borrower_name"]:
        last, first = [x.strip() for x in d["borrower_name"].split(",", 1)]
        d["borrower_name"] = f"{first} {last}".title()
    for bureau, key in (("Equifax", "score_equifax"), ("Experian", "score_experian"), ("TransUnion", "score_transunion")):
        m = re.search(rf"^{bureau}\b.*?\b(\d{{3}})$", text, re.M)
        d[key] = int(m.group(1)) if m else None
    for line in _section(text, r"^Creditor Type Balance", r"^PUBLIC RECORDS"):
        m = re.match(r"^(.+?)\s+(Auto|Revolving|Student|Installment|Mortgage|Lease)\s+(\$[\d,.]+)\s+(\$[\d,.]+)(?:\s+(\d+))?\s+(\S+)\s+(\d+)$", line.strip(), re.I)
        if m:
            d["tradelines"].append({"creditor": m.group(1), "account_type": TL_TYPE[m.group(2).lower()],
                                    "balance": to_money(m.group(3)), "monthly_payment": to_money(m.group(4)),
                                    "months_remaining": int(m.group(5)) if m.group(5) else None,
                                    "status": m.group(6), "late_30_last_12mo": int(m.group(7))})
    for line in _section(text, r"^Type Filed Discharged", r"^INQUIRIES"):
        low = line.lower()
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", line)
        et = ("chapter7_bankruptcy" if "chapter 7" in low else "chapter13_bankruptcy" if "chapter 13" in low else
              "foreclosure" if "foreclos" in low else "short_sale" if "short sale" in low else None)
        if et:
            d["derogatory_events"].append({"event_type": et, "date": to_date(dates[-1]) if dates else None})
    return d


EXTRACTORS = {"paystub": ex_paystub, "w2": ex_w2, "loan_application": ex_urla, "appraisal": ex_appraisal,
              "bank_statement": ex_bank, "credit_report": ex_credit}


def classify_and_extract(path: str, filename: str) -> dict:
    text = pdf_text(path)
    if not text.strip():
        return {"doc_type": "other", "confidence": 0.2, "fields": {"document_description": "No text layer (scanned image?)"},
                "rationale": "Offline demo engine cannot read image-only PDFs; configure an Anthropic API key.",
                "engine": "offline-demo"}
    doc_type, conf, why = classify(text)
    if doc_type == "other":
        first = next((l for l in text.splitlines() if l.strip()), "")
        return {"doc_type": "other", "confidence": conf, "rationale": why,
                "fields": {"document_description": first[:120]}, "engine": "offline-demo"}
    raw = EXTRACTORS[doc_type](text)
    return {"doc_type": doc_type, "confidence": conf, "rationale": why,
            "fields": validate_fields(doc_type, raw), "engine": "offline-demo"}


# ----------------------------------------------------------------------------- advisor / Q&A fallbacks
CONDITION_TEXT = {
    "DOC-": "Obtain: {name}",
    "DOC-AGE": "Obtain updated credit documents dated within 4 months of the note date",
    "DOC-PAYSTUB-RECENCY": "Obtain the most recent 30 days of paystubs",
    "COL-APPR-AGE": "Order appraisal update (Form 1004D) or a new appraisal",
    "COL-SUBJECT-TO": "Obtain Form 1004D certification of completion",
    "COL-MI": "Obtain mortgage insurance certificate and add the premium to PITIA",
    "COL-VALUE": "Revise contract or increase down payment to address the appraisal shortfall",
    "AST-LARGE-DEP": "Source large deposit(s) with documentation or gift letter",
    "AST-GIFT": "Obtain signed gift letter and evidence of transfer",
    "DTI-UNDISCLOSED": "Update the 1003 with all credit report liabilities",
    "CR-LATES": "Obtain letter of explanation for recent late payments",
    "INC-EMPLOYMENT": "Document a full two-year employment history (prior VOE / transcripts)",
    "INC-STATED": "Correct base income on the 1003 to the documented amount",
    "CON-EMPLOYER": "Complete a verbal verification of employment",
    "CON-NAME": "Resolve borrower name discrepancy (AKA statement)",
    "CON-OCCUPANCY": "Obtain lease termination / occupancy explanation",
    "CON-PRICE": "Obtain final executed purchase contract and addenda",
}


def _fix_for(r: dict, m: dict, method: str) -> str:
    """Concrete remedy for a failed rule, with numbers where the metrics allow."""
    rid = r["id"]
    income, pitia, debts = m.get("qualifying_income"), m.get("pitia"), m.get("monthly_debts") or 0
    if rid == "DTI-TOTAL" and income and pitia:
        limit = 50 if method == "du" else 45
        excess = pitia + debts - income * limit / 100
        need_income = (pitia + debts) / (limit / 100)
        return (f"Cut monthly obligations by about ${excess:,.0f} (pay off revolving/installment debt or lower the "
                f"loan amount), or document qualifying income of about ${need_income:,.0f}/mo to reach {limit}%.")
    if rid == "COL-LTV" and m.get("property_value"):
        mx = re.search(r"([\d.]+)%", r.get("threshold") or "")
        if mx:
            max_loan = m["property_value"] * float(mx.group(1)) / 100
            return (f"Reduce the loan amount to ${max_loan:,.0f} or less (about ${m['loan_amount'] - max_loan:,.0f} more down), "
                    "renegotiate the price, or confirm first-time homebuyer status if it applies.")
    if rid == "AST-FUNDS":
        short = (m.get("cash_to_close") or 0) - (m.get("verified_assets") or 0) - (m.get("gift_funds") or 0)
        return f"Verify at least ${short:,.0f} in additional assets (other accounts, documented gift) or reduce cash to close."
    if rid == "AST-RESERVES":
        return "Document additional liquid assets (savings, vested retirement) to meet the reserve requirement."
    if rid == "DOC-AGE":
        return "Obtain updated statements/paystubs/credit dated within 4 months of the note date, or move the closing date."
    if rid.startswith("CR-DEROG"):
        return "Wait until the waiting period is met, or document extenuating circumstances under B3-5.3-08."
    if rid == "CR-DECLARATION":
        return "Correct the Section 5 declarations on the 1003 and obtain a signed letter of explanation."
    if rid == "CR-SCORE":
        return "Manual underwriting cannot proceed below the minimum score; consider DU submission or credit repair."
    if rid == "COL-CONDITION":
        return "Require repairs and a re-inspection (Form 1004D) showing condition C4 or better."
    if rid == "COL-APPR-AGE":
        return "Order a new appraisal."
    if rid == "COL-LIMIT":
        return "Reduce the loan amount to the county conforming limit or move the loan to a jumbo program."
    if rid == "CON-ADDRESS":
        return "Obtain an appraisal of the subject property named on the application."
    return "Resolve the underlying issue, then re-run the checks."


def advise(evaluation: dict) -> dict:
    res = evaluation["results"]
    m = evaluation["metrics"]
    method = evaluation["settings"]["underwriting_method"]
    blockers = [{"issue": r["name"], "detail": r["message"], "citations": r["citations"], "fix": _fix_for(r, m, method)}
                for r in res if r["status"] == "fail"]
    conds = []
    for r in res:
        if r["status"] in ("warn", "missing"):
            tmpl = CONDITION_TEXT.get(r["id"]) or next((v for k, v in CONDITION_TEXT.items() if r["id"].startswith(k) and k.endswith("-")), None)
            conds.append({"condition": (tmpl or "Underwriter review: {name}").format(name=r["name"].replace(" received", "")),
                          "reason": r["message"], "timing": "prior_to_approval", "citations": r["citations"]})
    comp = []
    if (m.get("representative_score") or 0) >= 720:
        comp.append(f"Strong credit: representative score {m['representative_score']}.")
    if (m.get("reserves_months") or 0) >= 6:
        comp.append(f"Healthy reserves: {m['reserves_months']:.1f} months of PITIA after closing.")
    if m.get("back_dti") and m["back_dti"] <= 36:
        comp.append(f"Conservative DTI of {m['back_dti']:.1f}%.")
    if m.get("ltv") and m["ltv"] <= 80:
        comp.append(f"Low LTV of {m['ltv']:.1f}%.")
    d = evaluation["decision"]
    return {
        "headline": f"{d['label']}: {d['detail']}",
        "summary": ("Template summary (offline demo mode). The rule engine found "
                    f"{evaluation['counts']['fail']} failure(s), {evaluation['counts']['warn']} warning(s) and "
                    f"{evaluation['counts']['missing']} missing item(s). Qualifying income "
                    f"${(m.get('qualifying_income') or 0):,.0f}/mo, DTI {m.get('back_dti') or 0:.1f}%, LTV {m.get('ltv') or 0:.1f}%. "
                    "Add an Anthropic API key for Claude-written analysis that connects findings and proposes fixes."),
        "blockers": blockers, "conditions": conds, "compensating_factors": comp,
        "questions_for_underwriter": [], "data_quality_notes": [], "engine": "offline-template",
    }


def ask(question: str) -> str:
    words = {w for w in re.findall(r"[a-z]{4,}", question.lower())}
    scored = []
    for sid, g in G.GUIDELINES.items():
        hay = (g["title"] + " " + g["summary"]).lower()
        s = sum(1 for w in words if w in hay)
        if s:
            scored.append((s, sid, g))
    scored.sort(reverse=True)
    if not scored:
        return ("Offline demo mode: free-form Q&A needs an Anthropic API key. "
                "No matching guideline topic was found in the local knowledge base.")
    top = scored[:2]
    parts = [f"[{sid}] {g['title']}: {g['summary']}" for _, sid, g in top]
    return ("Offline demo mode (keyword lookup, not Claude). Closest guideline topics:\n\n" + "\n\n".join(parts) +
            "\n\nAdd ANTHROPIC_API_KEY to get answers that reason about this specific loan file.")
