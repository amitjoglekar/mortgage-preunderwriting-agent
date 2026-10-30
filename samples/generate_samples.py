"""Generate synthetic (fake) mortgage documents for testing the pre-underwriting agent.

Two loan files are produced:
  samples/loan_A_clean/   - a well-documented purchase that should meet automated checks
  samples/loan_B_issues/  - a purchase with many problems (bankruptcy within waiting period,
                            undisclosed debt, DTI too high, low appraisal, stale documents,
                            short funds, unsourced large deposit) plus one unsupported document

All names, employers, addresses, SSNs and account numbers are fictitious.
Run:  python samples/generate_samples.py
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).resolve().parent
SS = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=SS["Heading1"], fontSize=15, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=SS["Heading2"], fontSize=11.5, spaceBefore=8, spaceAfter=3,
                    textColor=colors.HexColor("#1f3a5f"))
BODY = ParagraphStyle("b", parent=SS["BodyText"], fontSize=9, leading=12)
SMALL = ParagraphStyle("s", parent=BODY, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#555555"))
RIGHT = ParagraphStyle("r", parent=BODY, alignment=TA_RIGHT)

GRID = TableStyle([
    ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa5b1")),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf3")),
    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
])
KV = TableStyle([
    ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
    ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8.5),
    ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 8.5),
    ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d7de")),
    ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
])


def m(v: float) -> str:
    return f"${v:,.2f}"


CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.5, leading=10.5)
CELL_B = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold")


def kv_table(pairs: list[tuple[str, str]], cols: int = 2, widths: list[float] | None = None) -> Table:
    """Label/value cells, `cols` pairs per row. Long values get a full-width row so they never wrap."""
    rows, row, spans = [], [], []
    def flush():
        nonlocal row
        if row:
            rows.append(row + [""] * (cols * 2 - len(row)))
            row = []
    for k, v in pairs:
        k, v = k.replace("&", "&amp;"), v.replace("&", "&amp;")
        if cols == 2 and len(k) > 22:
            flush()
            rows.append([Paragraph(f"{k}:", CELL_B), "", Paragraph(v, CELL), ""])
            spans += [("SPAN", (0, len(rows) - 1), (1, len(rows) - 1)), ("SPAN", (2, len(rows) - 1), (3, len(rows) - 1))]
            continue
        if cols == 2 and len(v) > 30:
            flush()
            rows.append([Paragraph(f"{k}:", CELL_B), Paragraph(v, CELL), "", ""])
            spans.append(("SPAN", (1, len(rows) - 1), (3, len(rows) - 1)))
            continue
        row += [Paragraph(f"{k}:" if k else "", CELL_B), Paragraph(v, CELL)]
        if len(row) == cols * 2:
            flush()
    flush()
    if widths is None:
        widths = [1.75, 1.9, 1.75, 1.9] if cols == 2 else [1.75, 5.55]
    t = Table(rows, colWidths=[w * inch for w in widths])
    t.setStyle(KV)
    if spans:
        t.setStyle(TableStyle(spans))
    return t


def grid(rows: list[list[str]], widths: list[float]) -> Table:
    t = Table(rows, colWidths=[w * inch for w in widths], repeatRows=1)
    t.setStyle(GRID)
    return t


def build(path: Path, story: list) -> None:
    doc = SimpleDocTemplate(str(path), pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.55 * inch, bottomMargin=0.55 * inch,
                            title=path.stem, author="Synthetic test data")
    doc.build(story)


def amort(p: float, rate: float, n: int = 360) -> float:
    r = rate / 1200
    return round(p * r / (1 - (1 + r) ** -n), 2)


# =============================================================================== documents
def paystub(path, d):
    s = [
        Paragraph(f"<b>{d['employer']}</b>", H1),
        Paragraph(d["employer_addr"], SMALL),
        Paragraph("EARNINGS STATEMENT", H2),
        kv_table([
            ("Employee", d["name"]), ("Employee ID", d["emp_id"]),
            ("Pay Period Start", d["start"]), ("Pay Period End", d["end"]),
            ("Pay Date", d["pay_date"]), ("Pay Frequency", d["freq"]),
            ("Pay Type", d["pay_type"]), ("Rate", d["rate_text"]),
        ]),
        Spacer(1, 8),
        grid([["Earnings", "Rate", "Hours", "Current", "Year-to-Date"]] + d["earnings"] +
             [["Gross Pay", "", "", m(d["gross"]), m(d["ytd_gross"])]],
             [2.0, 1.1, 0.8, 1.4, 1.6]),
        Spacer(1, 8),
        grid([["Deductions", "Current", "Year-to-Date"]] + d["deductions"], [3.0, 1.9, 2.0]),
        Spacer(1, 8),
        kv_table([("Net Pay", m(d["net"])), ("Direct Deposit", d["bank"])]),
        Spacer(1, 14),
        Paragraph("This statement is provided for your records. Synthetic test document.", SMALL),
    ]
    build(path, s)


def w2(path, d):
    s = [
        Paragraph(f"Form W-2 Wage and Tax Statement {d['year']}", H1),
        Paragraph("Department of the Treasury - Internal Revenue Service. Copy B - To Be Filed With Employee's FEDERAL Tax Return.", SMALL),
        Spacer(1, 6),
        grid([
            ["Box", "Description", "Value"],
            ["a", "Employee's social security number", d["ssn"]],
            ["b", "Employer identification number (EIN)", d["ein"]],
            ["c", "Employer's name, address, and ZIP code", f"{d['employer']}, {d['employer_addr']}"],
            ["e", "Employee's first name and initial, last name", d["name"]],
            ["f", "Employee's address and ZIP code", d["addr"]],
            ["1", "Wages, tips, other compensation", m(d["box1"])],
            ["2", "Federal income tax withheld", m(d["box2"])],
            ["3", "Social security wages", m(d["box3"])],
            ["4", "Social security tax withheld", m(d["box3"] * 0.062)],
            ["5", "Medicare wages and tips", m(d["box5"])],
            ["6", "Medicare tax withheld", m(d["box5"] * 0.0145)],
            ["12a", "D - Elective deferrals 401(k)", m(d["box5"] - d["box1"])],
            ["15", "State / Employer's state ID", "CA 123-4567-8"],
            ["16", "State wages, tips, etc.", m(d["box1"])],
        ], [0.6, 3.6, 2.9]),
        Spacer(1, 10),
        Paragraph(f"Tax Year: {d['year']}", BODY),
        Paragraph("Synthetic test document - not a real tax form.", SMALL),
    ]
    build(path, s)


def urla(path, d):
    liab_rows = [["Creditor", "Type", "Unpaid Balance", "Monthly Payment", "Months Left", "To Be Paid Off"]]
    for l in d["liabilities"]:
        liab_rows.append([l[0], l[1], m(l[2]), m(l[3]), str(l[4]), l[5]])
    asset_rows = [["Account Type", "Financial Institution", "Account Number", "Cash or Market Value"]]
    for a in d["assets"]:
        asset_rows.append([a[0], a[1], a[2], m(a[3])])
    s = [
        Paragraph("Uniform Residential Loan Application", H1),
        Paragraph("Freddie Mac Form 65 | Fannie Mae Form 1003. Synthetic test document.", SMALL),
        kv_table([("Application Date", d["app_date"]), ("Lender Loan No.", d["loan_no"])]),
        Paragraph("Section 1: Borrower Information", H2),
        kv_table([
            ("Borrower Name", d["name"]), ("Social Security Number", d["ssn"]),
            ("Date of Birth", d["dob"]), ("Citizenship", "U.S. Citizen"),
            ("Marital Status", d["marital"]), ("Dependents", "0"),
            ("Current Address", d["cur_addr"]), ("Housing", d["housing"]),
            ("Monthly Housing Payment", m(d["rent"])), ("Years at Address", d["yrs_addr"]),
            ("First-Time Homebuyer", d["ftb"]), ("", ""),
        ]),
        Paragraph("1b. Current Employment / Self-Employment and Income", H2),
        kv_table([
            ("Employer Name", d["employer"]), ("Position or Title", d["title"]),
            ("Start Date", d["emp_start"]), ("Years in Line of Work", d["line_yrs"]),
            ("Self-Employed", "No"), ("Employer Phone", "(555) 010-2000"),
            ("Base", m(d["base"]) + " /month"), ("Overtime", m(d["ot"]) + " /month"),
            ("Bonus", m(d["bonus"]) + " /month"), ("Commission", m(0) + " /month"),
            ("Other Income", m(d["other"]) + " /month"), ("Total Monthly Income", m(d["base"] + d["ot"] + d["bonus"] + d["other"])),
        ]),
    ]
    if d.get("prior_employer"):
        s += [Paragraph("1d. Previous Employment", H2),
              kv_table([("Previous Employer", d["prior_employer"]), ("Months Employed", str(d["prior_months"]))])]
    s += [
        PageBreak(),
        Paragraph("Section 2: Financial Information - Assets and Liabilities", H2),
        Paragraph("2a. Assets - Bank, Retirement, and Other Accounts", BODY),
        grid(asset_rows, [1.5, 2.2, 1.4, 1.9]),
        Spacer(1, 6),
        kv_table([("Earnest Money Deposit", m(d["emd"])), ("Gift Funds", m(d["gift"]))]),
        Paragraph("2c. Liabilities - Credit Cards, Other Debts, and Leases", BODY),
        grid(liab_rows, [1.7, 1.0, 1.1, 1.2, 0.9, 1.1]),
        Paragraph("Section 4: Loan and Property Information", H2),
        kv_table([
            ("Loan Purpose", d["purpose"]), ("Loan Amount", m(d["loan"])),
            ("Property Address", d["prop_addr"]), ("Number of Units", "1"),
            ("Property Value / Sales Price", m(d["price"])), ("Occupancy", d["occupancy"]),
            ("Property Type", d["prop_type"]), ("Subordinate Financing", m(0)),
        ]),
        Paragraph("L4. Qualifying the Borrower - Proposed Monthly Payment", H2),
        kv_table([
            ("Note Rate", f"{d['rate']}%"), ("Loan Term", "360 months"),
            ("Amortization Type", "Fixed Rate"), ("Mortgage Type", "Conventional"),
            ("First Mortgage (P&I)", m(d["pi"])), ("Homeowner's Insurance", m(d["hoi"])),
            ("Property Taxes", m(d["tax"])), ("Mortgage Insurance", m(d["mi"])),
            ("HOA Dues", m(d["hoa"])), ("Total Proposed Housing", m(d["pi"] + d["hoi"] + d["tax"] + d["mi"] + d["hoa"])),
            ("Estimated Closing Costs", m(d["closing"])), ("", ""),
        ]),
        Paragraph("Section 5: Declarations", H2),
        kv_table([
            ("A. Will you occupy the property as your primary residence?", "Yes"),
            ("H. Outstanding judgments against you?", "No"),
            ("I. Declared bankruptcy within the past 7 years?", d["bk_decl"]),
            ("J. Property foreclosed upon in the last 7 years?", "No"),
        ], cols=1, widths=[5.4, 1.9]),
        Spacer(1, 12),
        Paragraph(f"Borrower Signature: /s/ {d['name']}      Date: {d['app_date']}", BODY),
    ]
    build(path, s)


def appraisal(path, d):
    comps = [["", "Subject", "Comparable 1", "Comparable 2", "Comparable 3"],
             ["Address", d["addr"].split(",")[0]] + d["comp_addrs"],
             ["Sale Price", m(d["price"])] + [m(x) for x in d["comp_prices"]],
             ["GLA (sq ft)", str(d["gla"])] + [str(x) for x in d["comp_gla"]],
             ["Condition", d["cond"]] + ["C3", "C3", "C4"],
             ["Adjusted Price", ""] + [m(x) for x in d["comp_adj"]]]
    s = [
        Paragraph("Uniform Residential Appraisal Report", H1),
        Paragraph("Fannie Mae Form 1004 | Freddie Mac Form 70. Synthetic test document.", SMALL),
        Paragraph("SUBJECT", H2),
        kv_table([
            ("Property Address", d["addr"]), ("Borrower", d["borrower"]),
            ("Occupant", d["occupant"]), ("Property Rights Appraised", "Fee Simple"),
            ("Assignment Type", "Purchase Transaction"), ("Lender/Client", "Example Mortgage Co."),
        ]),
        Paragraph("CONTRACT", H2),
        kv_table([("Contract Price", m(d["price"])), ("Date of Contract", d["contract_date"])]),
        Paragraph("NEIGHBORHOOD", H2),
        kv_table([("Property Values", d["trend"]), ("Demand/Supply", "In Balance"),
                  ("Marketing Time", "Under 3 mths"), ("Location", "Suburban")]),
        Paragraph("IMPROVEMENTS", H2),
        kv_table([
            ("Design (Style)", "1 Story Ranch"), ("Number of Units", "1"),
            ("Year Built", str(d["year_built"])), ("Gross Living Area", f"{d['gla']} sq ft"),
            ("Condition Rating", d["cond"]), ("Quality Rating", d["qual"]),
            ("FEMA Flood Zone", d["flood"]), ("Property Type", "Single Family Detached"),
        ]),
        Paragraph(d["condition_comment"], BODY),
        PageBreak(),
        Paragraph("SALES COMPARISON APPROACH", H2),
        grid(comps, [1.2, 1.5, 1.5, 1.5, 1.5]),
        Paragraph("RECONCILIATION", H2),
        Paragraph(f"This appraisal is made <b>{d['made']}</b>.", BODY),
        kv_table([
            ("Indicated Value by Sales Comparison", m(d["value"])),
            ("Appraised Value of Subject Property", m(d["value"])),
            ("Effective Date of Appraisal", d["eff"]),
            ("Date of Signature and Report", d["sig"]),
            ("Appraiser", d["appraiser"]), ("State License #", "AR-0045821"),
        ]),
        Spacer(1, 10),
        Paragraph("I certify that, to the best of my knowledge, the statements of fact contained in this report are true and correct. (Synthetic.)", SMALL),
    ]
    build(path, s)


def bank_statement(path, d):
    rows = [["Date", "Description", "Withdrawals", "Deposits", "Balance"]]
    bal = d["begin"]
    for t in d["txns"]:
        bal = round(bal - t[2] + t[3], 2)
        rows.append([t[0], t[1], m(t[2]) if t[2] else "", m(t[3]) if t[3] else "", m(bal)])
    s = [
        Paragraph(f"<b>{d['bank']}</b>", H1),
        Paragraph("Member FDIC | Customer Service 1-800-555-0199", SMALL),
        Paragraph("Account Statement", H2),
        kv_table([
            ("Account Holder", d["holder"]), ("Account Type", d["acct_type"]),
            ("Account Number", f"XXXX-XXXX-{d['last4']}"), ("Statement Period", f"{d['start']} through {d['end']}"),
            ("Beginning Balance", m(d["begin"])), ("Ending Balance", m(bal)),
        ]),
        Spacer(1, 8),
        Paragraph("Transaction Detail", H2),
        grid(rows, [0.9, 2.9, 1.1, 1.1, 1.1]),
        Spacer(1, 10),
        Paragraph("Synthetic test document.", SMALL),
    ]
    build(path, s)
    return bal


def credit_report(path, d):
    tl = [["Creditor", "Type", "Balance", "Payment", "Months Rem.", "Status", "30-Day Lates (12 mo)"]]
    for t in d["tradelines"]:
        tl.append([t[0], t[1], m(t[2]), m(t[3]), t[4], t[5], str(t[6])])
    s = [
        Paragraph("Tri-Merge Residential Mortgage Credit Report", H1),
        Paragraph("Example Credit Services, Inc. | Synthetic test document.", SMALL),
        kv_table([("Borrower", d["name"]), ("Report Date", d["date"]), ("SSN", d["ssn"]), ("Report ID", d["rid"])]),
        Paragraph("CREDIT SCORES", H2),
        grid([["Bureau", "Model", "Score"],
              ["Equifax", "Beacon 5.0", str(d["scores"][0])],
              ["Experian", "Fair Isaac Risk Model V2", str(d["scores"][1])],
              ["TransUnion", "FICO Risk Score Classic 04", str(d["scores"][2])]], [2.0, 3.2, 1.5]),
        Paragraph("TRADELINES", H2),
        grid(tl, [1.55, 0.85, 0.95, 0.85, 0.85, 1.05, 1.1]),
        Paragraph("PUBLIC RECORDS", H2),
    ]
    if d["public"]:
        s.append(grid([["Type", "Filed", "Discharged", "Court"]] + d["public"], [2.0, 1.4, 1.4, 2.4]))
    else:
        s.append(Paragraph("No public records reported.", BODY))
    s += [Paragraph("INQUIRIES (LAST 120 DAYS)", H2),
          Paragraph(f"Total Inquiries: {len(d['inquiries'])}", BODY)]
    if d["inquiries"]:
        s.append(grid([["Date", "Subscriber"]] + d["inquiries"], [1.5, 4.0]))
    build(path, s)


def purchase_agreement(path):
    s = [Paragraph("Residential Purchase Agreement", H1),
         Paragraph("This agreement is made between the Buyer and Seller for the property described below. "
                   "Buyer agrees to purchase and Seller agrees to sell the property on the terms herein. "
                   "Earnest money shall be held in escrow. Closing shall occur on or before the date specified. "
                   "Synthetic test document.", BODY),
         kv_table([("Buyer", "Derek A. Thompson"), ("Seller", "Coastal Homes Trust"),
                   ("Property", "455 Harbor View Lane, Long Beach, CA 90803"), ("Price", m(610000)),
                   ("Closing Date", "12/15/2026"), ("Escrow", "First Coast Escrow")])]
    build(path, s)


# =============================================================================== loan A
def loan_a():
    out = OUT / "loan_A_clean"
    out.mkdir(exist_ok=True)
    name, employer = "Maria L. Gonzalez", "Northwind Health Systems"
    emp_addr = "2200 Capitol Mall, Sacramento, CA 95814"
    annual = 135_000.0
    per = round(annual / 26, 2)
    ytd_periods = 20
    paystub(out / "Gonzalez_paystub_Oct.pdf", {
        "employer": employer, "employer_addr": emp_addr, "name": name, "emp_id": "NW-20817",
        "start": "09/21/2026", "end": "10/04/2026", "pay_date": "10/09/2026", "freq": "Biweekly",
        "pay_type": "Salary", "rate_text": f"{m(annual)} annual",
        "earnings": [["Regular Salary", "", "80.00", m(per), m(per * ytd_periods)]],
        "gross": per, "ytd_gross": per * ytd_periods,
        "deductions": [["Federal Income Tax", m(720.40), m(14408.00)], ["Social Security", m(321.92), m(6438.40)],
                       ["Medicare", m(75.29), m(1505.80)], ["401(k) 4%", m(207.69), m(4153.80)],
                       ["Medical/Dental", m(118.50), m(2370.00)]],
        "net": per - 720.40 - 321.92 - 75.29 - 207.69 - 118.50, "bank": "River City Bank ****4471",
    })
    w2(out / "Gonzalez_W2_2025.pdf", {
        "year": 2025, "ssn": "XXX-XX-6618", "ein": "94-7712054", "employer": employer, "employer_addr": emp_addr,
        "name": name, "addr": "3110 J Street Apt 4, Sacramento, CA 95816",
        "box1": 124_480.00, "box2": 18_210.00, "box3": 129_660.00, "box5": 129_660.00,
    })
    loan, price, rate = 472_500.0, 525_000.0, 6.375
    pi = amort(loan, rate)
    urla(out / "Gonzalez_1003_application.pdf", {
        "app_date": "10/12/2026", "loan_no": "EM-2026-10481", "name": name, "ssn": "XXX-XX-6618",
        "dob": "04/17/1988", "marital": "Unmarried", "cur_addr": "3110 J Street Apt 4, Sacramento, CA 95816",
        "housing": "Rent", "rent": 2150.0, "yrs_addr": "4", "ftb": "Yes",
        "employer": employer, "title": "Clinical Systems Analyst", "emp_start": "03/11/2019", "line_yrs": "9",
        "base": 11_250.0, "ot": 0.0, "bonus": 0.0, "other": 0.0,
        "assets": [("Checking", "River City Bank", "****4471", 66_850.0), ("Savings", "River City Bank", "****4490", 25_000.0)],
        "emd": 10_000.0, "gift": 0.0,
        "liabilities": [("Toyota Financial", "Installment", 15_640.0, 412.0, 38, "No"),
                        ("Chase Visa", "Revolving", 2_100.0, 85.0, "", "No"),
                        ("Nelnet Student Loan", "Installment", 21_300.0, 210.0, 112, "No")],
        "purpose": "Purchase", "loan": loan, "prop_addr": "1842 Willow Creek Drive, Sacramento, CA 95822",
        "price": price, "occupancy": "Primary Residence", "prop_type": "Single Family Detached",
        "rate": rate, "pi": pi, "hoi": 125.0, "tax": 547.0, "mi": 142.0, "hoa": 0.0, "closing": 14_200.0,
        "bk_decl": "No",
    })
    appraisal(out / "Gonzalez_appraisal_1004.pdf", {
        "addr": "1842 Willow Creek Dr, Sacramento, CA 95822", "borrower": name, "occupant": "Vacant",
        "price": price, "contract_date": "09/28/2026", "trend": "Stable", "year_built": 1998, "gla": 1684,
        "cond": "C3", "qual": "Q4", "flood": "X", "value": 530_000.0, "made": "\"as is\"",
        "condition_comment": "The subject has been well maintained with updated kitchen (2019). No physical deficiencies or adverse conditions were noted.",
        "comp_addrs": ["1790 Willow Creek Dr", "2011 Aspen Glen Way", "1655 Brookside Ct"],
        "comp_prices": [519_000, 541_500, 527_000], "comp_gla": [1620, 1750, 1702],
        "comp_adj": [528_400, 532_100, 529_600], "eff": "10/20/2026", "sig": "10/22/2026", "appraiser": "Linda Park, Certified Residential",
    })
    bank_statement(out / "Gonzalez_checking_Sep2026.pdf", {
        "bank": "River City Bank", "holder": name, "acct_type": "Personal Checking", "last4": "4471",
        "start": "09/01/2026", "end": "09/30/2026", "begin": 61_204.33,
        "txns": [("09/04", "Rent payment - Midtown Lofts", 2150.00, 0), ("09/11", "NORTHWIND HEALTH PAYROLL DIR DEP", 0, 3802.62),
                 ("09/14", "Toyota Financial autopay", 412.00, 0), ("09/16", "Chase card payment", 260.00, 0),
                 ("09/18", "Nelnet student loan", 210.00, 0), ("09/22", "Grocery Outlet", 184.12, 0),
                 ("09/25", "NORTHWIND HEALTH PAYROLL DIR DEP", 0, 3802.62),
                 ("09/29", "PG&E utilities", 141.18, 0)],
    })
    bank_statement(out / "Gonzalez_savings_Sep2026.pdf", {
        "bank": "River City Bank", "holder": name, "acct_type": "Savings", "last4": "4490",
        "start": "09/01/2026", "end": "09/30/2026", "begin": 34_950.00,
        "txns": [("09/15", "Interest paid", 0, 50.00), ("09/28", "Transfer to escrow - earnest money deposit", 10_000.00, 0)],
    })
    credit_report(out / "Gonzalez_credit_report.pdf", {
        "name": "GONZALEZ, MARIA L", "date": "10/13/2026", "ssn": "XXX-XX-6618", "rid": "ECS-88213045",
        "scores": [742, 755, 738],
        "tradelines": [("Toyota Financial", "Auto", 15_640.0, 412.0, "38", "Current", 0),
                       ("Chase Visa", "Revolving", 2_100.0, 85.0, "", "Current", 0),
                       ("Nelnet", "Student", 21_300.0, 210.0, "112", "Current", 0),
                       ("Amex Gold", "Revolving", 0.0, 0.0, "", "Current", 0)],
        "public": [], "inquiries": [("10/13/2026", "Example Mortgage Co.")],
    })


# =============================================================================== loan B
def loan_b():
    out = OUT / "loan_B_issues"
    out.mkdir(exist_ok=True)
    name, employer = "Derek A. Thompson", "Summit Logistics Group"
    emp_addr = "800 Harbor Plaza Dr, Long Beach, CA 90802"
    rate_hr = 42.50
    per = rate_hr * 80
    paystub(out / "IMG_2041.pdf", {
        "employer": employer, "employer_addr": emp_addr, "name": name, "emp_id": "SLG-5512",
        "start": "07/27/2026", "end": "08/09/2026", "pay_date": "08/14/2026", "freq": "Biweekly",
        "pay_type": "Hourly", "rate_text": f"${rate_hr:.2f} per hour",
        "earnings": [["Regular", f"${rate_hr:.2f}", "80.00", m(per), m(per * 16)],
                     ["Overtime", f"${rate_hr * 1.5:.2f}", "6.00", m(rate_hr * 1.5 * 6), m(6850.00)]],
        "gross": per + rate_hr * 1.5 * 6, "ytd_gross": per * 16 + 6850.00,
        "deductions": [["Federal Income Tax", m(455.10), m(7281.60)], ["Social Security", m(234.51), m(3797.72)],
                       ["Medicare", m(54.84), m(888.18)], ["Medical", m(96.00), m(1536.00)]],
        "net": per + rate_hr * 9 - 455.10 - 234.51 - 54.84 - 96.00, "bank": "Pacific Shore CU ****0937",
    })
    w2(out / "scan_0007.pdf", {
        "year": 2025, "ssn": "XXX-XX-3390", "ein": "33-1188420", "employer": employer, "employer_addr": emp_addr,
        "name": name, "addr": "2730 E 4th St Unit 12, Long Beach, CA 90814",
        "box1": 50_320.00, "box2": 5_480.00, "box3": 50_320.00, "box5": 50_320.00,
    })
    loan, price, rate = 591_700.0, 610_000.0, 6.75
    pi = amort(loan, rate)
    urla(out / "scan_0003.pdf", {
        "app_date": "10/02/2026", "loan_no": "EM-2026-10322", "name": name, "ssn": "XXX-XX-3390",
        "dob": "11/02/1990", "marital": "Unmarried", "cur_addr": "2730 E 4th St Unit 12, Long Beach, CA 90814",
        "housing": "Rent", "rent": 2475.0, "yrs_addr": "2", "ftb": "No",
        "employer": employer, "title": "Dispatch Supervisor", "emp_start": "06/02/2025", "line_yrs": "6",
        "prior_employer": "Bayline Freight Co.", "prior_months": 5,
        "base": 8_200.0, "ot": 450.0, "bonus": 0.0, "other": 0.0,
        "assets": [("Checking", "Pacific Shore Credit Union", "****0937", 21_800.0)],
        "emd": 5_000.0, "gift": 0.0,
        "liabilities": [("Ally Auto", "Installment", 31_900.0, 689.0, 54, "No"),
                        ("Capital One", "Revolving", 4_350.0, 145.0, "", "No"),
                        ("Discover", "Revolving", 3_200.0, 0.0, "", "No")],
        "purpose": "Purchase", "loan": loan, "prop_addr": "455 Harbor View Lane, Long Beach, CA 90803",
        "price": price, "occupancy": "Primary Residence", "prop_type": "Single Family Detached",
        "rate": rate, "pi": pi, "hoi": 140.0, "tax": 635.0, "mi": 0.0, "hoa": 0.0, "closing": 15_000.0,
        "bk_decl": "No",
    })
    appraisal(out / "Document (4).pdf", {
        "addr": "455 Harbor View Ln, Long Beach, CA 90803", "borrower": name, "occupant": "Tenant",
        "price": price, "contract_date": "05/30/2026", "trend": "Stable", "year_built": 1962, "gla": 1410,
        "cond": "C4", "qual": "Q4", "flood": "AE", "value": 595_000.0, "made": "\"subject to\" the following repairs",
        "condition_comment": "Roof shows missing shingles and evidence of a minor leak at the rear bedroom. Appraisal is made subject to roof repair by a licensed contractor.",
        "comp_addrs": ["471 Harbor View Ln", "5120 E Sorrento Dr", "390 Bay Shore Ave"],
        "comp_prices": [589_000, 602_500, 598_000], "comp_gla": [1380, 1455, 1420],
        "comp_adj": [592_800, 596_200, 594_900], "eff": "06/15/2026", "sig": "06/18/2026", "appraiser": "Robert Nguyen, Certified Residential",
    })
    bank_statement(out / "statement_july.pdf", {
        "bank": "Pacific Shore Credit Union", "holder": "Derek A Thompson", "acct_type": "Share Draft Checking", "last4": "0937",
        "start": "06/16/2026", "end": "07/15/2026", "begin": 6_912.40,
        "txns": [("06/19", "SUMMIT LOGISTICS PAYROLL", 0, 2611.08), ("06/21", "Rent - Belmont Shore Apts", 2475.00, 0),
                 ("06/24", "Ally Auto payment", 689.00, 0), ("06/27", "Zelle from R THOMPSON", 0, 15_000.00),
                 ("07/03", "SUMMIT LOGISTICS PAYROLL", 0, 2611.08), ("07/07", "Capital One payment", 145.00, 0),
                 ("07/09", "Upstart loan payment", 310.00, 0), ("07/12", "Costco", 226.40, 0)],
    })
    credit_report(out / "credit_10-03.pdf", {
        "name": "THOMPSON, DEREK A", "date": "10/03/2026", "ssn": "XXX-XX-3390", "rid": "ECS-88199102",
        "scores": [668, 652, 690],
        "tradelines": [("Ally Auto", "Auto", 31_900.0, 689.0, "54", "Current", 0),
                       ("Capital One", "Revolving", 4_350.0, 145.0, "", "Current", 1),
                       ("Discover", "Revolving", 3_200.0, 0.0, "", "Current", 0),
                       ("Upstart Personal Loan", "Installment", 11_480.0, 310.0, "41", "Current", 0),
                       ("Ashley Furniture", "Installment", 540.0, 95.0, "6", "Current", 0)],
        "public": [["Chapter 7 Bankruptcy", "10/04/2022", "03/01/2023", "US Bankruptcy Court C.D. Cal."]],
        "inquiries": [("10/03/2026", "Example Mortgage Co."), ("08/22/2026", "Upstart Network"), ("07/30/2026", "Best Buy Credit")],
    })
    purchase_agreement(out / "Scan_contract.pdf")


if __name__ == "__main__":
    loan_a()
    loan_b()
    for p in sorted(OUT.glob("loan_*/*.pdf")):
        print(p.relative_to(OUT))
