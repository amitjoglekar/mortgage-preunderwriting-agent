"""Fannie Mae Selling Guide knowledge base used by the rule engine and the advisor.

Thresholds and summaries are paraphrased from the Fannie Mae Single-Family Selling
Guide and Eligibility Matrix as published in 2026 (the guide PDF in use was
published October 7, 2026). Section dates are the topic's last-revised date.

IMPORTANT: The Selling Guide changes frequently. Before relying on this prototype,
re-verify every threshold below against https://selling-guide.fanniemae.com and the
current Eligibility Matrix, and layer in your own investor/lender overlays.
"""
from __future__ import annotations

GUIDE_BASE = "https://selling-guide.fanniemae.com/sel"

GUIDELINES: dict[str, dict] = {
    "B1-1-03": {
        "title": "Allowable Age of Credit Documents and Federal Income Tax Returns",
        "revised": "2025-04-02",
        "url": f"{GUIDE_BASE}/b1-1-03/allowable-age-credit-documents-and-federal-income-tax-returns",
        "summary": "Credit documents (credit reports and employment, income and asset documentation) may be "
                   "no more than four months old on the note date. With consecutive statements, the most "
                   "recent one controls. Older documents must be updated.",
    },
    "B2-1.2-01": {
        "title": "Loan-to-Value (LTV) Ratios",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b2-1.2-01/loan-value-ltv-ratios",
        "summary": "LTV is the loan amount divided by the property value. For purchases the value is the "
                   "lower of the sales price or the appraised value. Maximum LTV/CLTV/HCLTV by transaction "
                   "is set in the Eligibility Matrix.",
    },
    "ELIG-MATRIX": {
        "title": "Eligibility Matrix (LTV, credit score and reserve limits)",
        "revised": "2026-04-01",
        "url": "https://singlefamily.fanniemae.com/media/document/pdf/eligibility-matrix-current",
        "summary": "Standard DU limits for a principal residence: purchase / limited cash-out up to 97% LTV "
                   "on a 1-unit fixed-rate loan (above 95% at least one borrower must be a first-time "
                   "homebuyer on a purchase), 95% for 1-unit ARMs and 2-4 units; cash-out refinance 80% on "
                   "1 unit. Second home purchase 90%. Investment purchase 85% (1 unit). Manually underwritten "
                   "loans have tighter credit-score and reserve grids tied to LTV and DTI.",
    },
    "B2-1.5-01": {
        "title": "Loan Limits",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b2-1.5-01/loan-limits",
        "summary": "FHFA 2026 conforming loan limit for one-unit properties is $832,750 in most areas. "
                   "High-cost areas allow high-balance loans up to $1,249,125 (1 unit).",
    },
    "B3-3.2-01": {
        "title": "Standards for Employment and Income Documentation",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b3-3.2-01/standards-employment-and-income-documentation",
        "summary": "Salaried/hourly income is typically documented with a recent paystub showing year-to-date "
                   "earnings (dated no earlier than 30 days before the initial application date) plus W-2s "
                   "covering the most recent one year (DU) or two years (manual). Employment history should "
                   "cover the most recent two years.",
    },
    "B3-3.3-01": {
        "title": "Base Income",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b3-3.3-01/base-income",
        "summary": "Base pay is calculated from the current rate of pay (hourly rate x hours, or salary) and "
                   "should be supported by year-to-date and prior-year earnings. Declining income must be "
                   "analyzed and the lower, stable amount used.",
    },
    "B3-3.3-02": {
        "title": "Bonus, Commission, Overtime, and Tip Income",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b3-3.3-02/bonus-commission-overtime-and-tip-income",
        "summary": "Variable income needs a documented history (generally two years, with a shorter period of "
                   "at least 12 months acceptable when justified) and is averaged; declining trends require "
                   "analysis.",
    },
    "B3-4.1-01": {
        "title": "Minimum Reserve Requirements",
        "revised": "2024-08-07",
        "url": f"{GUIDE_BASE}/b3-4.1-01/minimum-reserve-requirements",
        "summary": "Reserves are measured in months of the subject PITIA after funds to close are subtracted. "
                   "DU: no minimum for a 1-unit principal residence; 2 months for a second home; 6 months for "
                   "2-4 unit principal residences, investment properties, and cash-out refinances with DTI "
                   "over 45%; additional reserves for other financed properties. Manual: per Eligibility Matrix.",
    },
    "B3-4.2-02": {
        "title": "Depository Accounts",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b3-4.2-02/depository-accounts",
        "summary": "Bank statements must cover the most recent two months (one month for DU where allowed). "
                   "On purchases, large deposits - a single deposit over 50% of total monthly qualifying "
                   "income - must be sourced and documented.",
    },
    "B3-4.3-04": {
        "title": "Personal Gifts",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b3-4.3-04/personal-gifts",
        "summary": "Gift funds from an acceptable donor require a signed gift letter and evidence of transfer.",
    },
    "B3-5.1-01": {
        "title": "General Requirements for Credit Scores",
        "revised": "2026-04-22",
        "url": f"{GUIDE_BASE}/b3-5.1-01/general-requirements-credit-scores",
        "summary": "DU loan casefiles have no minimum credit score (removed for casefiles created on or after "
                   "Nov 16, 2025); DU assesses credit risk directly. Manually underwritten loans require a "
                   "minimum of 620 (fixed) or 640 (ARM) using the representative score (one borrower) or the "
                   "average median score (multiple borrowers).",
    },
    "B3-5.1-02": {
        "title": "Determining the Credit Score for a Mortgage Loan",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b3-5.1-02/determining-credit-score-mortgage-loan",
        "summary": "Representative score: the middle of three bureau scores, or the lower of two.",
    },
    "B3-5.3-07": {
        "title": "Significant Derogatory Credit Events - Waiting Periods",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b3-5.3-07/significant-derogatory-credit-events-waiting-periods-and-re-establishing-credit",
        "summary": "Standard waiting periods from discharge/completion: Chapter 7 bankruptcy 4 years; Chapter 13 "
                   "2 years from discharge (4 from dismissal); foreclosure 7 years; deed-in-lieu, preforeclosure "
                   "or short sale 4 years. Shorter periods may apply with documented extenuating circumstances.",
    },
    "B3-6-02": {
        "title": "Debt-to-Income Ratios",
        "revised": "2025-04-02",
        "url": f"{GUIDE_BASE}/b3-6-02/debt-income-ratios",
        "summary": "Manual underwriting: maximum total DTI 36%, up to 45% if the credit score and reserve "
                   "requirements of the Eligibility Matrix are met. DU: maximum 50%. Total obligations include "
                   "the subject PITIA, installment debts with more than ten months remaining, all revolving "
                   "payments, lease payments, alimony/child support, and other recurring obligations.",
    },
    "B3-6-05": {
        "title": "Monthly Debt Obligations",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b3-6-05/monthly-debt-obligations",
        "summary": "All debts on the credit report and application must be considered. Installment debts with "
                   "ten or fewer months remaining may be excluded unless they significantly affect ability to "
                   "pay. Debts paid off at or before closing can be excluded.",
    },
    "B4-1.2-04": {
        "title": "Appraisal Age and Use Requirements",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b4-1.2-04/appraisal-age-and-use-requirements",
        "summary": "The appraisal effective date must be within 12 months of the note date. If it is more than "
                   "four months old on the note date, an appraisal update (Form 1004D) is required.",
    },
    "B4-1.2-05": {
        "title": "Requirements for Verifying Completion and Postponed Improvements",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b4-1.2-05/requirements-verifying-completion-and-postponed-improvements",
        "summary": "Appraisals made 'subject to' completion, repairs or inspection require a certification of "
                   "completion (Form 1004D) before delivery.",
    },
    "B4-1.3-06": {
        "title": "Property Condition and Quality of Construction",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b4-1.3-06/property-condition-and-quality-construction-improvements",
        "summary": "Properties rated C5 or C6 (or Q6) have deficiencies affecting safety, soundness or "
                   "structural integrity; they are ineligible until repaired and re-rated C4 or better.",
    },
    "B7-1-01": {
        "title": "Provision of Mortgage Insurance",
        "revised": "2026",
        "url": f"{GUIDE_BASE}/b7-1-01/provision-mortgage-insurance",
        "summary": "Conventional first mortgages with LTV above 80% require mortgage insurance (or another "
                   "acceptable credit enhancement).",
    },
}

# ----------------------------------------------------------------- numeric thresholds
CONFORMING_LIMIT_1UNIT = 832_750
HIGH_BALANCE_CEILING_1UNIT = 1_249_125

DTI_MAX_DU = 50.0
DTI_MAX_MANUAL = 36.0
DTI_MAX_MANUAL_WITH_COMP = 45.0

MIN_SCORE_MANUAL_FIXED = 620
MIN_SCORE_MANUAL_ARM = 640

CREDIT_DOC_MAX_MONTHS = 4
APPRAISAL_UPDATE_MONTHS = 4
APPRAISAL_MAX_MONTHS = 12
PAYSTUB_MAX_DAYS_BEFORE_APP = 30

WAITING_PERIOD_YEARS = {
    "chapter7_bankruptcy": 4,
    "chapter13_bankruptcy": 2,
    "foreclosure": 7,
    "deed_in_lieu": 4,
    "short_sale": 4,
}

LARGE_DEPOSIT_PCT_OF_MONTHLY_INCOME = 0.50


def max_ltv(occupancy: str, purpose: str, units: int, amortization: str, first_time_buyer: bool | None) -> tuple[float, str]:
    """Return (max LTV %, explanation) for standard (non-HomeReady) DU loans."""
    units = units or 1
    amort = amortization or "fixed"
    occ = occupancy or "primary_residence"
    purpose = purpose or "purchase"
    if purpose == "cash_out_refinance":
        if occ == "primary_residence":
            return (80.0 if units == 1 else 75.0), "Cash-out refinance, principal residence"
        if occ == "second_home":
            return 75.0, "Cash-out refinance, second home"
        return (75.0 if units == 1 else 70.0), "Cash-out refinance, investment property"
    if occ == "primary_residence":
        if units == 1 and amort == "fixed":
            if purpose == "purchase" and not first_time_buyer:
                return 95.0, "1-unit fixed purchase; 95.01-97% requires a first-time homebuyer"
            return 97.0, "1-unit fixed-rate principal residence"
        return 95.0, "Principal residence (ARM or 2-4 units)"
    if occ == "second_home":
        return 90.0, "Second home, 1 unit"
    return (85.0 if purpose == "purchase" and units == 1 else 75.0), "Investment property"


def required_reserves_months(method: str, occupancy: str, units: int, purpose: str, dti: float | None) -> tuple[float, str]:
    occ = occupancy or "primary_residence"
    units = units or 1
    if method == "manual":
        # Manual reserves come from the Eligibility Matrix grid; 2 months is a common floor
        # for higher-DTI manual files. Treated as advisory.
        return (2.0 if (dti or 0) > DTI_MAX_MANUAL else 0.0), "Manual: per Eligibility Matrix grid (advisory)"
    if occ == "second_home":
        return 2.0, "DU: 2 months for a second home"
    if occ == "investment" or units > 1:
        return 6.0, "DU: 6 months for investment / 2-4 units"
    if purpose == "cash_out_refinance" and (dti or 0) > 45:
        return 6.0, "DU: 6 months for cash-out refinance with DTI over 45%"
    return 0.0, "DU: no minimum for a 1-unit principal residence"


def guideline_context(section_ids: list[str] | None = None) -> str:
    """Plain-text block of guideline summaries for LLM prompts."""
    ids = section_ids or list(GUIDELINES)
    lines = []
    for sid in ids:
        g = GUIDELINES.get(sid)
        if g:
            lines.append(f"[{sid}] {g['title']} (rev. {g['revised']}): {g['summary']}")
    return "\n".join(lines)
