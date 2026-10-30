# Mortgage Pre-Underwriting Agent (prototype)

An AI agent that pre-underwrites conventional mortgage files against Fannie Mae guidelines. Upload the borrower's PDFs; the agent classifies each document, extracts the data, runs a deterministic Fannie Mae rule engine, and drafts an advisor memo with blockers, conditions and suggested fixes for the human underwriter.

> Prototype for evaluation only. It is not a credit decision system, does not replace Desktop Underwriter (DU) or an underwriter, and its guideline thresholds must be re-verified against the current Selling Guide before any real use.

## Quick start

**New to terminals? Follow [GETTING_STARTED.md](GETTING_STARTED.md)** for step-by-step instructions on Mac and Windows: installing Python, opening a terminal in the project folder, the exact commands to paste, adding your API key, and starting the app again later.

Short version:

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY (optional, see below)
./run.sh                      # Mac/Linux: creates .venv, installs deps, serves http://localhost:8000
```

On Windows, double-click `run_windows.bat`.

In the app, click **Load sample A** (clean purchase, meets all checks) or **Load sample B** (problem file with seven failures), or create a new loan file and drop PDFs onto the Documents tab.

**Two engines.** With `ANTHROPIC_API_KEY` set, Claude reads every PDF natively (layout, tables, scans), writes the memo, and answers questions. Without a key the app runs in **offline demo mode**: a keyword classifier and label parser tuned to the bundled sample PDFs, a template memo, and keyword guideline lookup. Demo mode exists so the app runs end to end with no network; it will not handle real-world documents.

## How it works

```
 PDF upload ──► Claude: classify + extract (one call per document)
                 │  one tool per document type; the tool Claude calls IS the classification,
                 │  its arguments ARE the extracted fields (validated by Pydantic schemas)
                 ▼
          Loan file (JSON) ──► Rule engine (pure Python, every rule cites a Selling Guide section)
                 │                 │  income, DTI, LTV, credit, reserves, document age, consistency
                 │                 ▼
                 └──────────► Claude advisor: memo with blockers, fixes, conditions, questions
                                   ▼
                         UI: decision stamp, KPIs, rule results, documents, memo, Q&A
```

Design choices worth knowing:

- **The LLM never decides a rule outcome.** Claude extracts data and explains results; pass/fail comes from readable Python in `app/rules.py`, so results are reproducible and auditable.
- **Human in the loop.** Underwriters can open any document next to its extracted fields, correct values (rules re-run instantly), or change a misclassified document's type (Claude re-reads it as that type).
- **Underwriting path toggle.** DU vs manual thresholds, and an expected note date that drives document-age, appraisal-age and waiting-period rules.

## Documents supported

Loan application (URLA / Form 1003), paystub, W-2, appraisal (URAR / Form 1004), bank statement, tri-merge credit report. Anything else is classified as *Other* and kept in the file but not used. Schemas live in `app/models.py`; adding a type means adding a Pydantic model and an entry in `DOC_TYPES`.

## Rule catalog

| Area | Rules | Selling Guide |
|---|---|---|
| Documents | Required documents present; W-2 years (1 DU / 2 manual); credit documents ≤ 4 months old at note date; paystub within 30 days of application | B1-1-03, B3-3.2-01 |
| Consistency | Borrower name, employer, subject address, occupancy, purchase price across documents | B3-3.2-01, B4-1.2-04 |
| Income | Base income from rate of pay vs YTD and prior-year W-2 (declining income uses lower amount); stated vs documented; variable income flagged, not counted; 2-year employment history | B3-3.3-01, B3-3.3-02 |
| Credit | Representative score (middle of 3); manual minimum 620 fixed / 640 ARM; no DU minimum (removed Nov 16, 2025); bankruptcy/foreclosure waiting periods; declarations vs credit report; recent lates; inquiries | B3-5.1-01, B3-5.3-07 |
| Liabilities & DTI | P&I recomputed from terms; undisclosed debts; debt schedule (installments ≤ 10 payments excluded, 5% of balance for revolving with no payment, payoffs excluded); DTI ≤ 50% DU, 36% / 45% manual | B3-6-02, B3-6-05 |
| Collateral | LTV/CLTV vs Eligibility Matrix (97% needs first-time buyer on standard purchase); MI over 80% LTV; 2026 loan limit $832,750 (high-balance to $1,249,125); appraisal age (update after 4 months, new after 12); C5/C6/Q6 ineligible; "subject to" needs 1004D; low appraisal | B2-1.2-01, B2-1.5-01, B4-1.2-04, B4-1.3-06, B7-1-01 |
| Assets | Verified funds vs cash to close; reserves (DU: 0 for 1-unit primary, 2 second home, 6 investment / 2-4 units); large non-payroll deposits > 50% of monthly income; gift documentation | B3-4.1-01, B3-4.2-02, B3-4.3-04 |

Thresholds and guideline summaries are centralized in `app/guidelines.py` (paraphrased from the Selling Guide published October 7, 2026 and the April 1, 2026 Eligibility Matrix). The Guidelines tab in the app shows them with links to each section.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | Engine mode, model, document types |
| GET/POST | `/api/loans` | List / create loan files |
| GET/PATCH/DELETE | `/api/loans/{id}` | Loan with live evaluation; update name or settings |
| POST | `/api/loans/{id}/documents` | Upload PDFs (multipart `files`) |
| PATCH/DELETE | `/api/loans/{id}/documents/{doc}` | Correct `fields` or reclassify via `doc_type`; remove |
| POST | `/api/loans/{id}/advice` | Regenerate the advisor memo |
| POST | `/api/loans/{id}/ask` | Q&A about the file or guidelines |
| POST | `/api/samples/{name}` | Create a loan file from a bundled sample |

## Project layout

```
app/
  main.py         HTTP API + static UI (Starlette)
  pipeline.py     background extraction, auto memo, Q&A orchestration
  llm.py          Claude Messages API: classify+extract, advisor, Q&A
  rules.py        deterministic rule engine
  guidelines.py   Fannie Mae knowledge base + thresholds
  models.py       extraction schemas (also the Claude tool schemas)
  offline.py      demo-mode parser and template memo
  store.py        JSON persistence in ./data
static/           index.html, styles.css, app.js (no build step)
samples/          synthetic test PDFs + generate_samples.py
tests/            pytest suite (rules, extraction, mocked Claude contract)
```

Run tests with `python -m pytest -q`. Regenerate sample PDFs with `python samples/generate_samples.py`.

## Data handling

Uploaded PDFs and extracted data are stored unencrypted under `./data`. Extraction records only the last four digits of SSNs and account numbers. In Claude mode, documents are sent to the Anthropic API. Use synthetic or properly authorized data, and add authentication, encryption at rest and audit logging before anything beyond a local demo.

## Known limitations and next steps

- Single borrower per file; no co-borrower income or average-median score.
- Self-employment, rental income, other financed properties and HomeReady rules are out of scope (flagged for manual review).
- Manual-underwriting credit score / reserve grid is simplified; encode the full Eligibility Matrix next.
- Closing costs default to 3% of price when the 1003 has none; pull from the Loan Estimate instead.
- Next: DU findings import to compare against the agent's view, per-condition clearing workflow, audit trail of corrections, lender overlay configuration.
