"""Deterministic Fannie Mae pre-underwriting rule engine.

Input: the extracted data of every classified document in a loan file plus the
underwriter's settings (DU vs manual, expected note date).
Output: derived metrics (income, DTI, LTV, reserves...) and a list of rule
results, each citing the Selling Guide section it implements.

Rules are plain Python on purpose: an underwriter (or examiner) can read exactly
why a rule passed or failed, and results are reproducible. The LLM never decides
a rule outcome; it only extracts data and explains results.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Optional

from dateutil.relativedelta import relativedelta

from . import guidelines as G

PASS, FAIL, WARN, INFO, MISSING = "pass", "fail", "warn", "info", "missing"
EVENT_LABELS = {"chapter7_bankruptcy": "Chapter 7 bankruptcy", "chapter13_bankruptcy": "Chapter 13 bankruptcy",
                "foreclosure": "Foreclosure", "deed_in_lieu": "Deed-in-lieu", "short_sale": "Short sale"}
PERIODS_PER_YEAR = {"weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12}

CATEGORIES = [
    "Documents",
    "Data Consistency",
    "Income & Employment",
    "Credit",
    "Liabilities & DTI",
    "Collateral & LTV",
    "Assets & Reserves",
]


# ----------------------------------------------------------------------------- helpers
def parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def months_between(earlier: date, later: date) -> float:
    rd = relativedelta(later, earlier)
    return rd.years * 12 + rd.months + rd.days / 30.4375


def norm_name(s: Optional[str]) -> str:
    s = (s or "").lower()
    s = re.sub(r"\b(inc|llc|corp|corporation|co|company|ltd|the|jr|sr|ii|iii)\b\.?", " ", s)
    return re.sub(r"[^a-z0-9 ]", " ", re.sub(r"\s+", " ", s)).strip()


def norm_addr(s: Optional[str]) -> str:
    s = (s or "").lower()
    repl = {r"\bstreet\b": "st", r"\bavenue\b": "ave", r"\broad\b": "rd", r"\bdrive\b": "dr",
            r"\blane\b": "ln", r"\bcourt\b": "ct", r"\bboulevard\b": "blvd", r"\bplace\b": "pl",
            r"\bcircle\b": "cir", r"\bapartment\b": "apt", r"\bunit\b": "apt", r"#": " apt "}
    for pat, rep in repl.items():
        s = re.sub(pat, rep, s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def similar(a: Optional[str], b: Optional[str], normalizer=norm_name) -> float:
    a2, b2 = normalizer(a), normalizer(b)
    if not a2 or not b2:
        return 0.0
    if a2 == b2 or a2 in b2 or b2 in a2:
        return 1.0
    # Order-insensitive token comparison handles "Last, First" vs "First Last".
    ta, tb = set(a2.split()), set(b2.split())
    token = len(ta & tb) / max(len(ta | tb), 1)
    return max(SequenceMatcher(None, a2, b2).ratio(), token)


def money(v: Optional[float]) -> str:
    return "—" if v is None else f"${v:,.0f}"


def pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.2f}%"


def amortized_payment(principal: float, annual_rate_pct: float, months: int) -> float:
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return principal / months
    return principal * r / (1 - (1 + r) ** -months)


@dataclass
class RuleResult:
    id: str
    category: str
    name: str
    status: str
    message: str
    value: Optional[str] = None
    threshold: Optional[str] = None
    citations: list[str] = field(default_factory=list)
    docs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["citation_links"] = [
            {"id": c, "title": G.GUIDELINES[c]["title"], "url": G.GUIDELINES[c]["url"]}
            for c in self.citations if c in G.GUIDELINES
        ]
        return d


# ----------------------------------------------------------------------------- engine
class LoanFileEvaluator:
    def __init__(self, documents: list[dict], settings: dict):
        self.docs = [d for d in documents if d.get("status") == "processed"]
        self.settings = settings or {}
        self.method = self.settings.get("underwriting_method", "du")
        self.note_date = parse_date(self.settings.get("note_date")) or (date.today() + timedelta(days=30))
        self.results: list[RuleResult] = []
        self.metrics: dict[str, Any] = {}

    # ---- document access
    def of_type(self, t: str) -> list[dict]:
        return [d for d in self.docs if d.get("doc_type") == t]

    def latest(self, t: str, date_field: str) -> Optional[dict]:
        docs = self.of_type(t)
        if not docs:
            return None
        return max(docs, key=lambda d: parse_date(d["fields"].get(date_field)) or date.min)

    def add(self, *args, **kwargs):
        self.results.append(RuleResult(*args, **kwargs))

    # ---- main
    def evaluate(self) -> dict:
        self.app = self.of_type("loan_application")[0]["fields"] if self.of_type("loan_application") else {}
        self.app_doc = self.of_type("loan_application")[0] if self.of_type("loan_application") else None
        self.paystub_doc = self.latest("paystub", "pay_date")
        self.paystub = self.paystub_doc["fields"] if self.paystub_doc else {}
        self.w2_docs = sorted(self.of_type("w2"), key=lambda d: d["fields"].get("tax_year") or 0, reverse=True)
        self.appraisal_doc = self.latest("appraisal", "effective_date")
        self.appraisal = self.appraisal_doc["fields"] if self.appraisal_doc else {}
        self.credit_doc = self.latest("credit_report", "report_date")
        self.credit = self.credit_doc["fields"] if self.credit_doc else {}
        self.bank_docs = self.of_type("bank_statement")

        self.rule_documents()
        self.rule_consistency()
        self.rule_income()
        self.rule_credit()
        self.rule_dti()
        self.rule_collateral()
        self.rule_assets()
        return self.summary()

    # =========================================================== Documents
    def rule_documents(self):
        purpose = self.app.get("loan_purpose") or "purchase"
        required = [
            ("loan_application", "Loan application (Form 1003)", ["B3-3.2-01"]),
            ("paystub", "Recent paystub with YTD earnings", ["B3-3.2-01"]),
            ("w2", "W-2 (most recent year)", ["B3-3.2-01"]),
            ("credit_report", "Tri-merge credit report", ["B3-5.1-01"]),
            ("appraisal", "Appraisal report", ["B4-1.2-04"]),
            ("bank_statement", "Bank statement(s) for funds to close / reserves", ["B3-4.2-02"]),
        ]
        for t, label, cites in required:
            found = self.of_type(t)
            if found:
                self.add(f"DOC-{t}", "Documents", f"{label} received", PASS,
                         f"{len(found)} document(s) on file: " + ", ".join(d["filename"] for d in found) + ".",
                         citations=cites, docs=[d["filename"] for d in found])
            else:
                optional = t == "bank_statement" and purpose != "purchase"
                self.add(f"DOC-{t}", "Documents", f"{label} received", INFO if optional else MISSING,
                         f"No {label.lower()} in the file. Request it from the borrower." if not optional
                         else f"No {label.lower()}; needed only if reserves or funds to close must be verified.",
                         citations=cites)

        # W-2 years: DU 1 year, manual 2 years
        need = 2 if self.method == "manual" else 1
        years = sorted({d["fields"].get("tax_year") for d in self.w2_docs if d["fields"].get("tax_year")}, reverse=True)
        if self.w2_docs:
            ok = len(years) >= need
            self.add("DOC-W2-YEARS", "Documents", "W-2 history covers required years", PASS if ok else WARN,
                     f"W-2 tax years on file: {', '.join(map(str, years)) or 'unknown'}. "
                     f"{'DU requires the most recent year' if need == 1 else 'Manual underwriting requires two years'}.",
                     value=f"{len(years)} year(s)", threshold=f"{need} year(s)", citations=["B3-3.2-01"],
                     docs=[d["filename"] for d in self.w2_docs])

        # Age of credit documents on the note date
        aged = []
        for t, f, label in (("paystub", "pay_date", "Paystub"), ("bank_statement", "statement_period_end", "Bank statement"),
                            ("credit_report", "report_date", "Credit report")):
            for d in self.of_type(t):
                dt = parse_date(d["fields"].get(f))
                if dt:
                    aged.append((label, d["filename"], dt, months_between(dt, self.note_date)))
        if aged:
            stale = [a for a in aged if a[3] > G.CREDIT_DOC_MAX_MONTHS]
            oldest = max(aged, key=lambda a: a[3])
            self.add("DOC-AGE", "Documents", "Credit documents within 4 months of note date",
                     FAIL if stale else PASS,
                     (f"{len(stale)} document(s) will be older than 4 months on the note date "
                      f"({self.note_date:%b %d, %Y}): " + "; ".join(f"{a[0]} dated {a[2]:%m/%d/%Y}" for a in stale)
                      + ". Obtain updated documents.") if stale else
                     f"All dated credit documents are within 4 months of the expected note date ({self.note_date:%b %d, %Y}). "
                     f"Oldest: {oldest[0]} dated {oldest[2]:%m/%d/%Y}.",
                     value=f"{oldest[3]:.1f} months (oldest)", threshold="≤ 4 months", citations=["B1-1-03"],
                     docs=[a[1] for a in (stale or aged)])

        # Paystub dated within 30 days of application
        app_date = parse_date(self.app.get("application_date"))
        ps_date = parse_date(self.paystub.get("pay_date") or self.paystub.get("pay_period_end"))
        if app_date and ps_date:
            gap = (app_date - ps_date).days
            ok = gap <= G.PAYSTUB_MAX_DAYS_BEFORE_APP
            self.add("DOC-PAYSTUB-RECENCY", "Documents", "Paystub dated within 30 days of application",
                     PASS if ok else WARN,
                     f"Most recent paystub dated {ps_date:%m/%d/%Y}; application dated {app_date:%m/%d/%Y} "
                     f"({gap} days earlier)." + ("" if ok else " Request a more recent paystub."),
                     value=f"{gap} days", threshold="≤ 30 days before application", citations=["B3-3.2-01"],
                     docs=[self.paystub_doc["filename"]])

    # =========================================================== Consistency
    def rule_consistency(self):
        if not self.app:
            return
        bname = self.app.get("borrower_name")
        mismatches, checked = [], []
        for d in self.docs:
            if d["doc_type"] == "loan_application":
                continue
            f = d["fields"]
            other = f.get("employee_name") or f.get("borrower_name") or f.get("account_holder")
            if other:
                checked.append(d["filename"])
                if similar(bname, other) < 0.6:
                    mismatches.append(f"{d['filename']} shows '{other}'")
        if checked:
            self.add("CON-NAME", "Data Consistency", "Borrower name matches across documents",
                     WARN if mismatches else PASS,
                     ("Name differs from the application (" + (bname or "?") + "): " + "; ".join(mismatches)
                      + ". Confirm identity / obtain name affidavit.") if mismatches
                     else f"'{bname}' matches on {len(checked)} document(s).",
                     citations=["B3-3.2-01"], docs=checked)

        emp = self.app.get("employer_name")
        emp_checks = [(d["filename"], d["fields"].get("employer_name")) for d in self.docs
                      if d["doc_type"] in ("paystub", "w2") and d["fields"].get("employer_name")]
        if emp and emp_checks:
            bad = [(fn, e) for fn, e in emp_checks if similar(emp, e) < 0.6]
            # A W-2 from the disclosed prior employer is expected when the borrower changed jobs.
            prior = self.app.get("prior_employer_name")
            paystub_fn = self.paystub_doc["filename"] if self.paystub_doc else None
            bad = [(fn, e) for fn, e in bad if not (prior and similar(prior, e) >= 0.6 and fn != paystub_fn)]
            self.add("CON-EMPLOYER", "Data Consistency", "Employer matches application",
                     WARN if bad else PASS,
                     ("Employer on application is '" + emp + "' but " +
                      "; ".join(f"{fn} shows '{e}'" for fn, e in bad) + ". Verify employment (VVOE).") if bad
                     else f"Employer '{emp}' is consistent across paystub and W-2.",
                     citations=["B3-3.2-01"], docs=[fn for fn, _ in emp_checks])

        prop = self.app.get("property_address")
        subj = self.appraisal.get("subject_address")
        if prop and subj:
            s = similar(prop, subj, norm_addr)
            self.add("CON-ADDRESS", "Data Consistency", "Subject property address matches appraisal",
                     PASS if s >= 0.8 else FAIL,
                     f"Application: '{prop}'. Appraisal: '{subj}'." + ("" if s >= 0.8 else " Appraisal must be for the subject property."),
                     citations=["B4-1.2-04"], docs=[self.appraisal_doc["filename"]])

        occ = self.app.get("occupancy")
        appr_occ = self.appraisal.get("occupancy")
        if occ and appr_occ:
            conflict = occ == "primary_residence" and appr_occ == "tenant"
            self.add("CON-OCCUPANCY", "Data Consistency", "Occupancy consistent with appraisal",
                     WARN if conflict else PASS,
                     f"Application states {occ.replace('_', ' ')}; appraiser observed {appr_occ}."
                     + (" Tenant-occupied subject on an owner-occupied loan needs explanation (lease end, move-in plan)." if conflict else ""),
                     citations=["B2-1.2-01"], docs=[self.appraisal_doc["filename"]])

        if self.app.get("purchase_price") and self.appraisal.get("contract_price"):
            a, b = self.app["purchase_price"], self.appraisal["contract_price"]
            self.add("CON-PRICE", "Data Consistency", "Purchase price matches appraisal contract price",
                     PASS if abs(a - b) < 1 else WARN,
                     f"Application {money(a)} vs appraisal contract {money(b)}."
                     + ("" if abs(a - b) < 1 else " Obtain the final executed contract / addendum and send to the appraiser."),
                     citations=["B2-1.2-01"], docs=[self.appraisal_doc["filename"]])

    # =========================================================== Income
    def rule_income(self):
        ps = self.paystub
        qualifying = None
        base_current = None
        freq = ps.get("pay_frequency")
        ppy = PERIODS_PER_YEAR.get(freq or "", None)
        if ps:
            if ps.get("annual_salary"):
                base_current = ps["annual_salary"] / 12
                how = f"annual salary {money(ps['annual_salary'])} / 12"
            elif ps.get("hourly_rate") and ppy:
                hours = ps.get("regular_hours") or (40 * 52 / ppy)
                base_current = ps["hourly_rate"] * hours * ppy / 12
                how = f"${ps['hourly_rate']:.2f}/hr x {hours:g} hrs x {ppy} periods / 12"
            elif ps.get("current_base_pay") and ppy:
                base_current = ps["current_base_pay"] * ppy / 12
                how = f"{money(ps['current_base_pay'])} base per period x {ppy} / 12"
            else:
                how = "insufficient paystub data"

            end = parse_date(ps.get("pay_period_end") or ps.get("pay_date"))
            ytd_avg = None
            if end and (ps.get("ytd_base_pay") or ps.get("ytd_gross_pay")):
                months_elapsed = ((end - date(end.year, 1, 1)).days + 1) / 365 * 12
                ytd_basis = ps.get("ytd_base_pay") or ps.get("ytd_gross_pay")
                ytd_avg = ytd_basis / months_elapsed if months_elapsed > 0 else None

            w2_monthly = None
            if self.w2_docs:
                w = self.w2_docs[0]["fields"]
                wages = w.get("box5_medicare_wages") or w.get("box1_wages")
                if wages:
                    w2_monthly = wages / 12

            qualifying = base_current
            notes = []
            status = PASS
            if base_current is None:
                status = MISSING
                notes.append("Could not compute base income from the paystub.")
            else:
                if ytd_avg and ytd_avg < base_current * 0.90:
                    notes.append(f"YTD average {money(ytd_avg)}/mo is below the current rate; using the YTD average.")
                    qualifying = ytd_avg
                    status = WARN
                if w2_monthly and ytd_avg and ytd_avg < w2_monthly * 0.90:
                    notes.append(f"Income is declining versus prior-year W-2 ({money(w2_monthly)}/mo). Obtain explanation; use lower stable amount.")
                    qualifying = min(qualifying, ytd_avg)
                    status = WARN
                if not notes:
                    if w2_monthly and w2_monthly < base_current * 0.75:
                        notes.append("Current pay is supported by YTD earnings. Prior-year W-2 is much lower "
                                     "(partial year or raise); confirm start date and pay history with a VOE.")
                    else:
                        notes.append("Current base pay is supported by YTD" + (" and prior-year W-2." if w2_monthly else "."))
            self.add("INC-BASE", "Income & Employment", "Base income calculation and trend", status,
                     f"Base income {money(base_current)}/mo ({how}). YTD average {money(ytd_avg)}/mo. "
                     f"Prior-year W-2 {money(w2_monthly)}/mo. " + " ".join(notes),
                     value=f"{money(qualifying)}/mo qualifying", citations=["B3-3.3-01", "B3-3.2-01"],
                     docs=[x["filename"] for x in ([self.paystub_doc] + self.w2_docs[:1]) if x])
            self.metrics.update(base_income_current=base_current, base_income_ytd_avg=ytd_avg,
                                w2_monthly=w2_monthly)

            variable = sum(ps.get(k) or 0 for k in ("ytd_overtime", "ytd_bonus", "ytd_commission"))
            if variable > 0:
                self.add("INC-VARIABLE", "Income & Employment", "Overtime / bonus / commission income", INFO,
                         f"YTD variable income of {money(variable)} is excluded from qualifying income pending a "
                         "documented two-year history (minimum 12 months with justification). Obtain a written VOE "
                         "with a breakdown by year to consider it.",
                         value=money(variable) + " YTD", citations=["B3-3.3-02"], docs=[self.paystub_doc["filename"]])

        # Stated vs documented income
        stated = self.app.get("base_monthly_income")
        if stated and qualifying:
            diff = (stated - qualifying) / qualifying * 100
            status = PASS if diff <= 5 else WARN
            self.add("INC-STATED", "Income & Employment", "Stated base income supported by documentation", status,
                     f"Application states {money(stated)}/mo; documents support {money(qualifying)}/mo ({diff:+.1f}%)."
                     + ("" if status == PASS else " Qualify on the documented amount and correct the 1003."),
                     value=f"{diff:+.1f}%", threshold="stated ≤ documented + 5%", citations=["B3-3.3-01"],
                     docs=[self.app_doc["filename"]])
        if self.app.get("other_monthly_income"):
            self.add("INC-OTHER", "Income & Employment", "Other income on application", INFO,
                     f"Application lists {money(self.app['other_monthly_income'])}/mo of other income with no supporting "
                     "document in the file; it is excluded until documented.", citations=["B3-3.2-01"])

        # Employment history (2 years)
        start = parse_date(self.app.get("employment_start_date"))
        if start:
            as_of = parse_date(self.app.get("application_date")) or self.note_date
            months_on_job = months_between(start, as_of)
            prior = self.app.get("prior_employment_months") or 0
            total = months_on_job + prior
            status = PASS if total >= 24 else WARN
            self.add("INC-EMPLOYMENT", "Income & Employment", "Two-year employment history", status,
                     f"{months_on_job / 12:.1f} years with current employer as of the application date" + (f" plus {prior} months prior employment" if prior else "")
                     + ("." if status == PASS else ". Document the gap / prior employment or school history for a full 2 years."),
                     value=f"{total / 12:.1f} years", threshold="≥ 2 years", citations=["B3-3.2-01"],
                     docs=[self.app_doc["filename"]])
        if self.app.get("self_employed"):
            self.add("INC-SELFEMP", "Income & Employment", "Self-employment income", WARN,
                     "Borrower is self-employed; this prototype's core rule set does not analyze tax returns. "
                     "Route to an underwriter for B3-3.5 analysis.", citations=["B3-3.2-01"])

        self.metrics["qualifying_income"] = qualifying

    # =========================================================== Credit
    def rule_credit(self):
        c = self.credit
        if not c:
            return
        scores = [s for s in (c.get("score_equifax"), c.get("score_experian"), c.get("score_transunion")) if s]
        rep = None
        if scores:
            s = sorted(scores)
            rep = s[1] if len(s) == 3 else s[0]
        self.metrics["representative_score"] = rep
        amort = self.app.get("amortization_type") or "fixed"
        if rep is None:
            self.add("CR-SCORE", "Credit", "Representative credit score", WARN,
                     "No usable credit score found. Nontraditional credit rules (B3-5.4) would apply.",
                     citations=["B3-5.1-01"], docs=[self.credit_doc["filename"]])
        elif self.method == "manual":
            floor = G.MIN_SCORE_MANUAL_ARM if amort == "arm" else G.MIN_SCORE_MANUAL_FIXED
            self.add("CR-SCORE", "Credit", "Representative credit score", PASS if rep >= floor else FAIL,
                     f"Scores {', '.join(map(str, scores))}; representative score {rep} (middle of three / lower of two). "
                     f"Manual underwriting minimum is {floor} for {'ARMs' if amort == 'arm' else 'fixed-rate loans'}.",
                     value=str(rep), threshold=f"≥ {floor}", citations=["B3-5.1-01", "B3-5.1-02"],
                     docs=[self.credit_doc["filename"]])
        else:
            self.add("CR-SCORE", "Credit", "Representative credit score", INFO if rep >= 620 else WARN,
                     f"Scores {', '.join(map(str, scores))}; representative score {rep}. DU has no minimum credit "
                     "score for casefiles created on or after Nov 16, 2025; DU's own risk assessment governs."
                     + (" Score below 620: expect pricing impact and possible MI/lender overlays." if rep < 620 else ""),
                     value=str(rep), threshold="No DU minimum", citations=["B3-5.1-01", "B3-5.1-02"],
                     docs=[self.credit_doc["filename"]])

        # Significant derogatory events
        events = [e for e in c.get("derogatory_events") or [] if e.get("event_type") in G.WAITING_PERIOD_YEARS]
        if events:
            for e in events:
                when = parse_date(e.get("date"))
                yrs = G.WAITING_PERIOD_YEARS[e["event_type"]]
                if not when:
                    self.add(f"CR-DEROG-{e['event_type']}", "Credit", "Derogatory event waiting period", WARN,
                             f"{EVENT_LABELS[e['event_type']]} reported without a completion date. Obtain discharge papers.",
                             citations=["B3-5.3-07"], docs=[self.credit_doc["filename"]])
                    continue
                elapsed = months_between(when, self.note_date) / 12
                ok = elapsed >= yrs
                self.add(f"CR-DEROG-{e['event_type']}", "Credit", "Derogatory event waiting period", PASS if ok else FAIL,
                         f"{EVENT_LABELS[e['event_type']]} dated {when:%m/%d/%Y}: {elapsed:.1f} years elapsed at note date; "
                         f"{yrs}-year waiting period." + ("" if ok else " Ineligible unless extenuating circumstances are documented (B3-5.3-08)."),
                         value=f"{elapsed:.1f} yrs", threshold=f"≥ {yrs} yrs", citations=["B3-5.3-07"],
                         docs=[self.credit_doc["filename"]])
        else:
            self.add("CR-DEROG", "Credit", "Significant derogatory events", PASS,
                     "No bankruptcy, foreclosure, deed-in-lieu or short sale reported.",
                     citations=["B3-5.3-07"], docs=[self.credit_doc["filename"]])

        # Declarations vs credit report
        if self.app.get("declares_bankruptcy_past_7_years") is False and any(
                e.get("event_type", "").endswith("bankruptcy") for e in c.get("derogatory_events") or []):
            self.add("CR-DECLARATION", "Credit", "Declarations agree with credit report", FAIL,
                     "Application declares no bankruptcy in the past 7 years, but the credit report shows one. "
                     "Correct the 1003 and obtain a letter of explanation.",
                     citations=["B3-5.3-07"], docs=[self.credit_doc["filename"], self.app_doc["filename"] if self.app_doc else ""])

        lates = [t for t in c.get("tradelines") or [] if (t.get("late_30_last_12mo") or 0) + (t.get("late_60_plus_last_12mo") or 0) > 0]
        mortgage_late = [t for t in lates if t.get("account_type") == "mortgage"]
        self.add("CR-LATES", "Credit", "Recent late payments (12 months)",
                 WARN if lates else PASS,
                 ("Late payments in the last 12 months: " + "; ".join(
                     f"{t.get('creditor')} ({t.get('late_30_last_12mo') or 0}x30, {t.get('late_60_plus_last_12mo') or 0}x60+)" for t in lates)
                  + (". Mortgage lates weigh heavily in DU." if mortgage_late else ". Obtain letter of explanation."))
                 if lates else "No late payments reported in the last 12 months.",
                 citations=["B3-5.1-01"], docs=[self.credit_doc["filename"]])

        inq = c.get("inquiries_last_120_days")
        if inq:
            self.add("CR-INQUIRIES", "Credit", "Recent credit inquiries", INFO,
                     f"{inq} inquiries in the last 120 days. Confirm no new undisclosed debt was opened (inquiry letter).",
                     value=str(inq), citations=["B3-6-05"], docs=[self.credit_doc["filename"]])

    # =========================================================== DTI
    def _pitia(self) -> tuple[Optional[float], dict]:
        a = self.app
        parts = {}
        pi = a.get("proposed_principal_interest")
        computed = None
        if a.get("loan_amount") and a.get("note_rate_percent") and a.get("loan_term_months"):
            computed = amortized_payment(a["loan_amount"], a["note_rate_percent"], a["loan_term_months"])
        parts["principal_interest"] = pi or computed
        parts["principal_interest_computed"] = computed
        for k in ("homeowners_insurance", "property_taxes", "mortgage_insurance", "hoa_dues"):
            parts[k] = a.get(f"proposed_{k}") or 0.0
        if parts["principal_interest"] is None:
            return None, parts
        total = parts["principal_interest"] + sum(parts[k] for k in ("homeowners_insurance", "property_taxes", "mortgage_insurance", "hoa_dues"))
        return total, parts

    def _monthly_debts(self) -> tuple[float, list[dict]]:
        payoff = [l for l in self.app.get("liabilities") or [] if l.get("to_be_paid_off")]
        rows = []
        source = self.credit.get("tradelines") if self.credit else None
        if source is None:
            source = [{"creditor": l.get("creditor"), "account_type": l.get("liability_type"),
                       "balance": l.get("unpaid_balance"), "monthly_payment": l.get("monthly_payment"),
                       "months_remaining": l.get("months_remaining")} for l in self.app.get("liabilities") or []]
        for t in source:
            pay = t.get("monthly_payment")
            bal = t.get("balance") or 0
            typ = t.get("account_type") or "other"
            row = {"creditor": t.get("creditor"), "type": typ, "balance": bal, "payment": pay, "included": True, "reason": ""}
            if bal == 0 and not pay:
                row.update(included=False, reason="Zero balance")
            elif any(similar(p.get("creditor"), t.get("creditor")) >= 0.7 for p in payoff):
                row.update(included=False, reason="Paid off at/before closing (verify)")
            elif typ in ("installment", "auto", "student") and t.get("months_remaining") is not None and t["months_remaining"] <= 10:
                row.update(included=False, reason="≤ 10 payments remaining")
            elif typ == "mortgage" and self.app.get("current_housing") != "own":
                row.update(included=False, reason="Mortgage tradeline; borrower not retaining property (verify)")
            elif typ == "revolving" and not pay and bal:
                row.update(payment=round(bal * 0.05, 2), reason="No payment reported: 5% of balance used")
            rows.append(row)
        total = sum(r["payment"] or 0 for r in rows if r["included"])
        return total, rows

    def rule_dti(self):
        if not self.app:
            return
        pitia, parts = self._pitia()
        debts, rows = self._monthly_debts()
        income = self.metrics.get("qualifying_income")
        self.metrics.update(pitia=pitia, pitia_parts=parts, monthly_debts=debts, debt_schedule=rows)

        if parts.get("principal_interest_computed") and self.app.get("proposed_principal_interest"):
            diff = abs(parts["principal_interest_computed"] - self.app["proposed_principal_interest"])
            self.add("DTI-PI", "Liabilities & DTI", "Proposed P&I matches loan terms", PASS if diff <= 5 else WARN,
                     f"1003 P&I {money(self.app['proposed_principal_interest'])}; computed from "
                     f"{money(self.app['loan_amount'])} at {self.app['note_rate_percent']}% over {self.app['loan_term_months']} months = "
                     f"${parts['principal_interest_computed']:,.2f}.", citations=["B3-6-02"], docs=[self.app_doc["filename"]])

        # Undisclosed debts
        if self.credit:
            disclosed = self.app.get("liabilities") or []
            undisclosed = [t for t in self.credit.get("tradelines") or []
                           if (t.get("monthly_payment") or 0) > 0 and t.get("account_type") != "mortgage"
                           and not any(similar(l.get("creditor"), t.get("creditor")) >= 0.7 for l in disclosed)]
            counted = {r["creditor"] for r in rows if r["included"]}
            self.add("DTI-UNDISCLOSED", "Liabilities & DTI", "All credit report debts disclosed on 1003",
                     WARN if undisclosed else PASS,
                     ("Debts on credit report not listed on the application: " +
                      "; ".join(f"{t.get('creditor')} ({money(t.get('monthly_payment'))}/mo, "
                                f"{'counted in DTI' if t.get('creditor') in counted else 'excluded from DTI: ' + next((r['reason'] for r in rows if r['creditor'] == t.get('creditor')), '')})"
                                for t in undisclosed)
                      + ". Update the 1003 and confirm no other new debt.") if undisclosed
                     else "Every payment-bearing tradeline appears on the application.",
                     citations=["B3-6-05", "B3-6-02"], docs=[self.credit_doc["filename"]])

        if not income or pitia is None:
            self.add("DTI-TOTAL", "Liabilities & DTI", "Total debt-to-income ratio", MISSING,
                     "Cannot compute DTI: " + ("qualifying income missing. " if not income else "") +
                     ("proposed housing payment missing." if pitia is None else ""), citations=["B3-6-02"])
            return
        front = pitia / income * 100
        back = (pitia + debts) / income * 100
        self.metrics.update(front_dti=front, back_dti=back)
        self.add("DTI-HOUSING", "Liabilities & DTI", "Housing expense ratio (front-end)", INFO,
                 f"PITIA {money(pitia)} / income {money(income)} = {pct(front)}. Fannie Mae does not set a separate housing-ratio limit.",
                 value=pct(front), citations=["B3-6-02"])
        if self.method == "manual":
            if back <= G.DTI_MAX_MANUAL:
                st, msg = PASS, "Within the 36% manual maximum."
            elif back <= G.DTI_MAX_MANUAL_WITH_COMP:
                st, msg = WARN, "Above 36%: allowed up to 45% only if credit score and reserves meet the Eligibility Matrix."
            else:
                st, msg = FAIL, "Exceeds the 45% manual maximum."
            thr = "≤ 36% (≤ 45% w/ matrix)"
        else:
            st = PASS if back <= G.DTI_MAX_DU else FAIL
            msg = "Within the 50% DU maximum." if st == PASS else "Exceeds the 50% DU maximum: ineligible as structured."
            if st == PASS and back > 45:
                st, msg = WARN, "Within 50% but above 45%: DU approval less likely; strengthen reserves."
            thr = "≤ 50% (DU)"
        self.add("DTI-TOTAL", "Liabilities & DTI", "Total debt-to-income ratio", st,
                 f"(PITIA {money(pitia)} + debts {money(debts)}) / income {money(income)} = {pct(back)}. {msg}",
                 value=pct(back), threshold=thr, citations=["B3-6-02", "B3-6-05"])

    # =========================================================== Collateral
    def rule_collateral(self):
        a = self.app
        if not a:
            return
        loan = a.get("loan_amount")
        price = a.get("purchase_price")
        appraised = self.appraisal.get("appraised_value")
        purpose = a.get("loan_purpose") or "purchase"
        if purpose == "purchase":
            candidates = [v for v in (price, appraised) if v]
            value = min(candidates) if candidates else None
        else:
            value = appraised or a.get("estimated_value")
        if loan and value:
            ltv = loan / value * 100
            cltv = (loan + (a.get("subordinate_financing_amount") or 0)) / value * 100
            self.metrics.update(ltv=ltv, cltv=cltv, property_value=value, loan_amount=loan)
            max_l, why = G.max_ltv(a.get("occupancy"), purpose, a.get("number_of_units") or self.appraisal.get("number_of_units") or 1,
                                   a.get("amortization_type"), a.get("first_time_homebuyer"))
            self.add("COL-LTV", "Collateral & LTV", "LTV / CLTV within Eligibility Matrix", PASS if max(ltv, cltv) <= max_l + 1e-9 else FAIL,
                     f"Loan {money(loan)} / value {money(value)} = LTV {pct(ltv)}, CLTV {pct(cltv)}. "
                     f"Value basis: {'lower of price and appraised value' if purpose == 'purchase' else 'appraised value'}. Max {max_l:.0f}% ({why}).",
                     value=pct(ltv), threshold=f"≤ {max_l:.0f}%", citations=["B2-1.2-01", "ELIG-MATRIX"])
            if ltv > 80:
                has_mi = (a.get("proposed_mortgage_insurance") or 0) > 0
                self.add("COL-MI", "Collateral & LTV", "Mortgage insurance for LTV over 80%", PASS if has_mi else WARN,
                         f"LTV {pct(ltv)} requires mortgage insurance. " +
                         (f"MI of {money(a['proposed_mortgage_insurance'])}/mo included in PITIA." if has_mi
                          else "No MI premium on the application; obtain MI quote and add to PITIA (DTI will rise)."),
                         citations=["B7-1-01"])

        if loan:
            units = a.get("number_of_units") or 1
            if units == 1:
                if loan <= G.CONFORMING_LIMIT_1UNIT:
                    st, msg = PASS, "Within the 2026 baseline conforming limit."
                elif loan <= G.HIGH_BALANCE_CEILING_1UNIT:
                    st, msg = WARN, "High-balance: eligible only if the county's 2026 limit is at least this amount."
                else:
                    st, msg = FAIL, "Exceeds the 2026 high-cost ceiling: jumbo, not eligible for Fannie Mae."
                self.add("COL-LIMIT", "Collateral & LTV", "Loan amount within conforming limit", st,
                         f"Loan amount {money(loan)}. {msg}", value=money(loan),
                         threshold=f"≤ {money(G.CONFORMING_LIMIT_1UNIT)} (1 unit)", citations=["B2-1.5-01"])

        if self.appraisal:
            ap = self.appraisal
            if price and appraised and appraised < price:
                self.add("COL-VALUE", "Collateral & LTV", "Appraised value supports purchase price", WARN,
                         f"Appraised value {money(appraised)} is {money(price - appraised)} below the {money(price)} contract price. "
                         "LTV is based on the appraised value; borrower needs a larger down payment or a price renegotiation.",
                         citations=["B2-1.2-01"], docs=[self.appraisal_doc["filename"]])
            elif price and appraised:
                self.add("COL-VALUE", "Collateral & LTV", "Appraised value supports purchase price", PASS,
                         f"Appraised value {money(appraised)} supports the {money(price)} contract price.",
                         citations=["B2-1.2-01"], docs=[self.appraisal_doc["filename"]])

            eff = parse_date(ap.get("effective_date"))
            if eff:
                age = months_between(eff, self.note_date)
                if age <= G.APPRAISAL_UPDATE_MONTHS:
                    st, msg = PASS, "Within 4 months of note date."
                elif age <= G.APPRAISAL_MAX_MONTHS:
                    st, msg = WARN, "More than 4 months old at note date: appraisal update (Form 1004D) required."
                else:
                    st, msg = FAIL, "More than 12 months old at note date: new appraisal required."
                self.add("COL-APPR-AGE", "Collateral & LTV", "Appraisal age at note date", st,
                         f"Effective date {eff:%m/%d/%Y}; {age:.1f} months at the expected note date. {msg}",
                         value=f"{age:.1f} months", threshold="≤ 4 mo (≤ 12 with update)", citations=["B4-1.2-04"],
                         docs=[self.appraisal_doc["filename"]])

            cond = (ap.get("condition_rating") or "").upper().strip()
            qual = (ap.get("quality_rating") or "").upper().strip()
            if cond or qual:
                bad = cond in ("C5", "C6") or qual == "Q6"
                self.add("COL-CONDITION", "Collateral & LTV", "Property condition and quality ratings", FAIL if bad else PASS,
                         f"Condition {cond or '—'}, quality {qual or '—'}." +
                         (" C5/C6 or Q6 properties are ineligible until repaired and re-inspected." if bad else ""),
                         value=f"{cond}/{qual}", threshold="C4/Q5 or better", citations=["B4-1.3-06"],
                         docs=[self.appraisal_doc["filename"]])

            if ap.get("appraised_as") and ap["appraised_as"] != "as_is":
                self.add("COL-SUBJECT-TO", "Collateral & LTV", "Appraisal completed 'as is'", WARN,
                         f"Appraisal made {ap['appraised_as'].replace('_', ' ')}. A certification of completion (Form 1004D) is required before delivery.",
                         citations=["B4-1.2-05"], docs=[self.appraisal_doc["filename"]])

    # =========================================================== Assets
    def rule_assets(self):
        a = self.app
        if not a:
            return
        latest_by_acct: dict[str, dict] = {}
        for d in self.bank_docs:
            f = d["fields"]
            key = (f.get("institution") or "") + (f.get("account_last4") or d["filename"])
            cur = latest_by_acct.get(key)
            if not cur or (parse_date(f.get("statement_period_end")) or date.min) > (parse_date(cur["fields"].get("statement_period_end")) or date.min):
                latest_by_acct[key] = d
        verified = sum(d["fields"].get("ending_balance") or 0 for d in latest_by_acct.values())
        gift = a.get("gift_funds") or 0
        purpose = a.get("loan_purpose") or "purchase"
        price = a.get("purchase_price") or 0
        loan = a.get("loan_amount") or 0
        closing = a.get("estimated_closing_costs")
        closing_note = ""
        if closing is None and price:
            closing = round(price * 0.03, 2)
            closing_note = " (closing costs estimated at 3% of price; replace with Loan Estimate figure)"
        emd = a.get("earnest_money_deposit") or 0
        cash_to_close = max(price - loan + (closing or 0) - emd, 0) if purpose == "purchase" else (closing or 0)
        available = verified + gift
        self.metrics.update(verified_assets=verified, gift_funds=gift, cash_to_close=cash_to_close)

        if self.bank_docs:
            short = available < cash_to_close
            self.add("AST-FUNDS", "Assets & Reserves", "Verified funds cover cash to close", FAIL if short else PASS,
                     f"Verified balances {money(verified)}" + (f" + gift {money(gift)}" if gift else "") +
                     f" vs cash to close {money(cash_to_close)} (down payment {money(max(price - loan, 0))} + closing "
                     f"{money(closing)} − EMD {money(emd)}){closing_note}." +
                     (f" Short {money(cash_to_close - available)}." if short else ""),
                     value=money(available), threshold=f"≥ {money(cash_to_close)}", citations=["B3-4.1-01", "B3-4.2-02"],
                     docs=[d["filename"] for d in latest_by_acct.values()])

            pitia = self.metrics.get("pitia")
            if pitia:
                remaining = available - cash_to_close
                months = remaining / pitia if pitia else 0
                req, why = G.required_reserves_months(self.method, a.get("occupancy"), a.get("number_of_units") or 1,
                                                      purpose, self.metrics.get("back_dti"))
                self.metrics.update(reserves_months=max(months, 0), reserves_amount=max(remaining, 0))
                if remaining < 0:
                    # The shortfall is already a failure under AST-FUNDS; only fail again if reserves are required.
                    self.add("AST-RESERVES", "Assets & Reserves", "Reserves after closing", FAIL if req > 0 else INFO,
                             f"No reserves: verified funds do not cover cash to close (see funds rule). Required: {req:g} months ({why}).",
                             value="0.0 months", threshold=f"≥ {req:g} months", citations=["B3-4.1-01"])
                else:
                    self.add("AST-RESERVES", "Assets & Reserves", "Reserves after closing", PASS if months >= req else FAIL,
                             f"{money(remaining)} remaining after closing = {months:.1f} months of PITIA. Required: {req:g} months ({why}).",
                             value=f"{months:.1f} months", threshold=f"≥ {req:g} months", citations=["B3-4.1-01"])

            income = self.metrics.get("qualifying_income")
            if income and purpose == "purchase":
                limit = income * G.LARGE_DEPOSIT_PCT_OF_MONTHLY_INCOME
                emp = norm_name(a.get("employer_name"))
                large = []
                for d in self.bank_docs:
                    for dep in d["fields"].get("deposits") or []:
                        desc = (dep.get("description") or "").lower()
                        is_payroll = any(k in desc for k in ("payroll", "direct dep", "dir dep", "salary")) or (emp and emp.split()[0] in desc)
                        if (dep.get("amount") or 0) > limit and not is_payroll:
                            large.append((d["filename"], dep))
                self.add("AST-LARGE-DEP", "Assets & Reserves", "Large deposits sourced", WARN if large else PASS,
                         ("Large deposits over 50% of monthly income (" + money(limit) + "): " +
                          "; ".join(f"{money(dep.get('amount'))} on {dep.get('date')} '{dep.get('description')}'" for _, dep in large)
                          + ". Obtain source documentation or a gift letter, or exclude the funds.") if large
                         else f"No non-payroll deposits above {money(limit)} (50% of monthly qualifying income).",
                         threshold=f"> {money(limit)} must be sourced", citations=["B3-4.2-02", "B3-4.3-04"],
                         docs=sorted({fn for fn, _ in large}) or [d["filename"] for d in self.bank_docs])
        if gift:
            self.add("AST-GIFT", "Assets & Reserves", "Gift funds documented", WARN,
                     f"Application lists {money(gift)} in gift funds. Obtain a signed gift letter and evidence of transfer.",
                     citations=["B3-4.3-04"])

    # =========================================================== Summary
    def summary(self) -> dict:
        counts = {s: 0 for s in (PASS, FAIL, WARN, INFO, MISSING)}
        for r in self.results:
            counts[r.status] += 1
        if counts[FAIL]:
            decision = {"code": "ineligible", "label": "Ineligible as submitted",
                        "detail": f"{counts[FAIL]} rule(s) failed. Restructure or resolve before submitting to DU."}
        elif counts[WARN] or counts[MISSING]:
            decision = {"code": "refer", "label": "Refer — conditions required",
                        "detail": f"{counts[WARN]} warning(s) and {counts[MISSING]} missing item(s) need underwriter review."}
        else:
            decision = {"code": "eligible", "label": "Meets automated checks",
                        "detail": "No failures or warnings. Proceed to DU submission and full underwriting."}
        if not self.docs:
            decision = {"code": "empty", "label": "Awaiting documents", "detail": "Upload loan documents to begin."}
        order = {c: i for i, c in enumerate(CATEGORIES)}
        sev = {FAIL: 0, MISSING: 1, WARN: 2, INFO: 3, PASS: 4}
        results = sorted(self.results, key=lambda r: (order.get(r.category, 99), sev[r.status]))
        return {
            "decision": decision,
            "counts": counts,
            "metrics": self.metrics,
            "results": [r.as_dict() for r in results],
            "settings": {"underwriting_method": self.method, "note_date": self.note_date.isoformat()},
            "borrower": self.app.get("borrower_name") if self.app else None,
            "property": (self.app.get("property_address") if self.app else None) or self.appraisal.get("subject_address"),
        }


def evaluate(documents: list[dict], settings: dict) -> dict:
    return LoanFileEvaluator(documents, settings).evaluate()
