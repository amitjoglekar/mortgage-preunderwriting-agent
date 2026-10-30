"""Extraction schemas for each supported document type.

Each schema doubles as (1) the JSON schema handed to Claude as a tool definition,
so the model returns exactly these fields, and (2) the validator for whatever
comes back. Every field is optional: a document that lacks a value should leave
it null rather than guess.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Money = Optional[float]
DateStr = Optional[str]  # ISO 8601 (YYYY-MM-DD)


class _Base(BaseModel):
    model_config = {"extra": "ignore"}


# --------------------------------------------------------------------------- paystub
class Paystub(_Base):
    employee_name: Optional[str] = None
    employer_name: Optional[str] = None
    pay_period_start: DateStr = Field(None, description="YYYY-MM-DD")
    pay_period_end: DateStr = Field(None, description="YYYY-MM-DD")
    pay_date: DateStr = Field(None, description="YYYY-MM-DD")
    pay_frequency: Optional[Literal["weekly", "biweekly", "semimonthly", "monthly"]] = None
    pay_type: Optional[Literal["hourly", "salary"]] = None
    hourly_rate: Money = None
    regular_hours: Optional[float] = Field(None, description="Regular hours this period")
    annual_salary: Money = Field(None, description="Only if printed on the stub")
    current_base_pay: Money = Field(None, description="Regular/base earnings this period")
    current_overtime: Money = None
    current_bonus: Money = None
    current_commission: Money = None
    current_gross_pay: Money = None
    ytd_base_pay: Money = None
    ytd_overtime: Money = None
    ytd_bonus: Money = None
    ytd_commission: Money = None
    ytd_gross_pay: Money = None
    current_net_pay: Money = None


# --------------------------------------------------------------------------- W-2
class W2(_Base):
    tax_year: Optional[int] = None
    employee_name: Optional[str] = None
    employee_ssn_last4: Optional[str] = Field(None, description="Last 4 digits only")
    employer_name: Optional[str] = None
    employer_ein: Optional[str] = None
    box1_wages: Money = Field(None, description="Wages, tips, other compensation")
    box5_medicare_wages: Money = None


# --------------------------------------------------------------------------- 1003
class AssetItem(_Base):
    institution: Optional[str] = None
    account_type: Optional[str] = None
    balance: Money = None


class LiabilityItem(_Base):
    creditor: Optional[str] = None
    liability_type: Optional[Literal["revolving", "installment", "mortgage", "auto", "student", "lease", "other"]] = None
    monthly_payment: Money = None
    unpaid_balance: Money = None
    months_remaining: Optional[int] = None
    to_be_paid_off: Optional[bool] = Field(None, description="Paid off at or before closing")


class LoanApplication(_Base):
    application_date: DateStr = None
    borrower_name: Optional[str] = None
    borrower_ssn_last4: Optional[str] = None
    borrower_dob: DateStr = None
    current_address: Optional[str] = None
    current_housing: Optional[Literal["own", "rent", "no_expense"]] = None
    current_housing_payment: Money = None
    first_time_homebuyer: Optional[bool] = None
    employer_name: Optional[str] = None
    position_title: Optional[str] = None
    employment_start_date: DateStr = None
    years_in_line_of_work: Optional[float] = None
    prior_employer_name: Optional[str] = None
    prior_employment_months: Optional[int] = None
    self_employed: Optional[bool] = None
    base_monthly_income: Money = None
    overtime_monthly_income: Money = None
    bonus_monthly_income: Money = None
    commission_monthly_income: Money = None
    other_monthly_income: Money = None
    total_monthly_income: Money = None
    assets: list[AssetItem] = Field(default_factory=list)
    liabilities: list[LiabilityItem] = Field(default_factory=list)
    loan_purpose: Optional[Literal["purchase", "limited_cash_out_refinance", "cash_out_refinance"]] = None
    property_address: Optional[str] = None
    occupancy: Optional[Literal["primary_residence", "second_home", "investment"]] = None
    number_of_units: Optional[int] = None
    property_type: Optional[str] = Field(None, description="e.g. single family, condo, PUD")
    purchase_price: Money = None
    estimated_value: Money = Field(None, description="For refinances")
    loan_amount: Money = None
    subordinate_financing_amount: Money = None
    note_rate_percent: Optional[float] = None
    loan_term_months: Optional[int] = None
    amortization_type: Optional[Literal["fixed", "arm"]] = None
    proposed_principal_interest: Money = None
    proposed_homeowners_insurance: Money = None
    proposed_property_taxes: Money = None
    proposed_mortgage_insurance: Money = None
    proposed_hoa_dues: Money = None
    estimated_closing_costs: Money = None
    earnest_money_deposit: Money = None
    gift_funds: Money = None
    declares_bankruptcy_past_7_years: Optional[bool] = None
    declares_foreclosure_past_7_years: Optional[bool] = None
    declares_outstanding_judgments: Optional[bool] = None
    us_citizen: Optional[bool] = None


# --------------------------------------------------------------------------- appraisal
class Appraisal(_Base):
    form_type: Optional[str] = Field(None, description="e.g. 1004 URAR, 1073 condo")
    subject_address: Optional[str] = None
    borrower_name: Optional[str] = None
    property_type: Optional[str] = None
    number_of_units: Optional[int] = None
    occupancy: Optional[Literal["owner", "tenant", "vacant"]] = None
    contract_price: Money = None
    contract_date: DateStr = None
    appraised_value: Money = None
    effective_date: DateStr = Field(None, description="Effective date of the appraisal")
    report_signature_date: DateStr = None
    condition_rating: Optional[str] = Field(None, description="UAD C1-C6")
    quality_rating: Optional[str] = Field(None, description="UAD Q1-Q6")
    appraised_as: Optional[Literal["as_is", "subject_to_completion", "subject_to_repairs", "subject_to_inspection"]] = None
    gross_living_area_sqft: Optional[float] = None
    year_built: Optional[int] = None
    comparables_count: Optional[int] = None
    neighborhood_value_trend: Optional[Literal["increasing", "stable", "declining"]] = None
    flood_zone: Optional[str] = None
    appraiser_name: Optional[str] = None


# --------------------------------------------------------------------------- bank statement
class LargeDeposit(_Base):
    date: DateStr = None
    amount: Money = None
    description: Optional[str] = None


class BankStatement(_Base):
    account_holder: Optional[str] = None
    institution: Optional[str] = None
    account_type: Optional[str] = None
    account_last4: Optional[str] = None
    statement_period_start: DateStr = None
    statement_period_end: DateStr = None
    beginning_balance: Money = None
    ending_balance: Money = None
    deposits: list[LargeDeposit] = Field(default_factory=list, description="Every deposit listed")


# --------------------------------------------------------------------------- credit report
class Tradeline(_Base):
    creditor: Optional[str] = None
    account_type: Optional[Literal["revolving", "installment", "mortgage", "auto", "student", "lease", "other"]] = None
    balance: Money = None
    monthly_payment: Money = None
    months_remaining: Optional[int] = None
    status: Optional[str] = None
    late_30_last_12mo: Optional[int] = None
    late_60_plus_last_12mo: Optional[int] = None


class DerogatoryEvent(_Base):
    event_type: Optional[Literal["chapter7_bankruptcy", "chapter13_bankruptcy", "foreclosure", "deed_in_lieu", "short_sale", "charge_off", "collection", "judgment"]] = None
    date: DateStr = Field(None, description="Discharge/completion date")
    amount: Money = None


class CreditReport(_Base):
    borrower_name: Optional[str] = None
    report_date: DateStr = None
    score_equifax: Optional[int] = None
    score_experian: Optional[int] = None
    score_transunion: Optional[int] = None
    tradelines: list[Tradeline] = Field(default_factory=list)
    derogatory_events: list[DerogatoryEvent] = Field(default_factory=list)
    inquiries_last_120_days: Optional[int] = None


DOC_TYPES: dict[str, dict] = {
    "loan_application": {"label": "Loan Application (URLA / Form 1003)", "model": LoanApplication,
                          "hint": "Uniform Residential Loan Application, borrower info, employment, assets, liabilities, loan & property info."},
    "paystub": {"label": "Paystub", "model": Paystub,
                "hint": "Earnings statement for one pay period with current and year-to-date earnings."},
    "w2": {"label": "W-2", "model": W2,
           "hint": "IRS Form W-2 Wage and Tax Statement for a tax year."},
    "appraisal": {"label": "Appraisal (URAR / Form 1004)", "model": Appraisal,
                  "hint": "Uniform Residential Appraisal Report giving market value of the subject property."},
    "bank_statement": {"label": "Bank Statement", "model": BankStatement,
                       "hint": "Depository account statement (checking, savings, money market)."},
    "credit_report": {"label": "Credit Report", "model": CreditReport,
                      "hint": "Tri-merge credit report with scores, tradelines and public records."},
}

DOC_LABELS = {k: v["label"] for k, v in DOC_TYPES.items()} | {"other": "Other / Unrecognized"}


def _inline_refs(schema: dict) -> dict:
    """Pydantic emits $defs/$ref; inline them so the tool schema is self-contained."""
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"].split("/")[-1]
                return walk(dict(defs[ref]))
            return {k: walk(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


def tool_schema(doc_type: str) -> dict:
    schema = _inline_refs(DOC_TYPES[doc_type]["model"].model_json_schema())
    # Every tool also carries the classifier's confidence and rationale.
    schema.setdefault("properties", {})
    schema["properties"]["classification_confidence"] = {
        "type": "number", "description": "0-1 confidence that the document is this type"}
    schema["properties"]["classification_rationale"] = {
        "type": "string", "description": "One sentence on why this document is this type"}
    schema["required"] = ["classification_confidence", "classification_rationale"]
    return schema


def validate_fields(doc_type: str, data: dict) -> dict:
    model = DOC_TYPES[doc_type]["model"]
    return model.model_validate(data).model_dump()
