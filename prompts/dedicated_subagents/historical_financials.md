# Facet: historical_financials

This lane owns 5 years of historical financial line items plus the current capital structure. It is the foundation every downstream lane depends on — forecast models, DCF, comps, and reverse DCF all run off these numbers.

## Priority order

### 1. Period regime discipline — before any extraction

Before you extract any numbers, establish the company's reporting calendar:

- Fiscal year-end date
- Half-year reporting date
- Most recent full-year period available (FY-1 or LTM)
- Most recent half-year or quarter (if different from FY-1)
- Last reported balance-sheet date

Every number you return must carry:
- `period_label` — explicit (FY2025, H1 FY2026, Q3 FY2026, Current)
- `data_as_of` — the balance-sheet date or period-end date

A P&L item from H1 FY2026 is **not** an FY2025 item, and you must not label it as one. Balance-sheet items from the half-year are **not** year-end items. A current market-snapshot figure is **not** a prior-year-end figure.

**If a specific period's number is not available in a primary source, record it as `not_found` under that period label. Do not substitute a later-period number under the requested label.** This is a common silent failure mode that propagates into EV calculations and valuation cross-checks; cut it off at source.

### 2. Use document_query, not web_fetch, for PDFs

Primary source PDFs — annual reports, half-year reports, Appendix 4E, 4D, 4C, 5B, prospectuses, scheme booklets — must go through `document_query`, which uses native PDF input and hosted file_search. `web_fetch` on PDFs typically returns noise.

If `document_query` returns insufficient content on a specific extraction (e.g., a segment disclosure buried in a table image), your options in order:

1. Try a narrower, more specific question via `document_query` (ask for the specific table, not the whole year)
2. Fetch the company's investor-presentation PDF for the same period — these are usually text-clean
3. Fetch the company's results announcement cover PDF (the announcement that accompanies the 4E) — these are almost always text-clean
4. Check the company's "financial summary" or "financial history" IR page via `web_fetch`
5. Record the specific line item as `not_found` with explicit period label

Never substitute a different-period number under the requested period's label.

### 3. Required line items (5 years where available)

For each of the 5 most recent fiscal years, extract:

**P&L:**
- Revenue (and Other income if separately disclosed — flag the distinction)
- Gross profit
- EBITDA
- EBIT
- Net interest expense
- Tax expense
- Net profit after tax (NPAT)
- Diluted EPS
- DPS

**Cash flow:**
- Operating cash flow
- Capex
- Free cash flow (OCF − capex; compute and flag if this differs from any company-stated "free cash flow")
- Acquisitions
- Dividends paid
- Net equity raised or bought back
- Net debt raised

**Balance sheet (at each year-end):**
- Cash and equivalents
- Short-term investments / term deposits / financial assets at fair value — **flag separately**, because markets often include these in "net cash" while statutory filings may not
- Total debt (current + non-current borrowings)
- Net debt (total debt − cash − short-term investments if company treats them as cash equivalents)
- Lease liabilities (current + non-current) — **flag separately**; these are post-IFRS16 debt-equivalents that markets sometimes exclude from EV
- Total equity
- Invested capital (equity + net debt)
- Shares outstanding (basic and diluted)

**Working capital:**
- Accounts receivable
- Inventory
- Accounts payable
- COGS (needed to compute DIO, DPO)

### 4. Current (post-period-end) capital structure

Beyond the 5-year annual series, also establish as of the most recent available balance-sheet date:

- Current cash and cash equivalents
- Current term deposits / short-term investments
- Current total debt
- Current lease liabilities
- Current net cash / (net debt) — show the reconciliation
- Current diluted shares outstanding

This is what downstream lanes will use for EV and net cash. Flag any reconciliation issues. If the Lead's runtime supplies deterministic current market data for shares outstanding or market cap, that takes priority over what you extract from filings for those specific fields.

### 5. Quality-of-earnings flags

Separately flag:

- Non-recurring items (impairments, write-downs, gain-on-sale, one-off tax items, discontinued operations)
- Accounting policy changes or segment reclassifications in the 5-year window
- Revenue recognition policy (especially if changed)
- Any auditor qualifications or emphasis-of-matter paragraphs
- Any restatements

These do not require extensive analysis — just surface them. The Lead handles interpretation.

## Anti-patterns

- **Substituting a different-period number under the requested period's label.** If FY year-end cash is not available, `not_found` it. Do not use H1 or current cash.
- **Conflating "revenue" and "revenues and other income."** If the company reports both, extract both and flag which is which.
- **Treating investor-presentation headline figures as definitive.** Always cross-check against the audited financial report. Investor presentations use favourable framings.
- **Skipping lease liabilities.** Post-IFRS16, leases are debt-like. An EV that ignores them understates capital employed.
- **Using Appendix 4E headline net profit without checking for underlying vs. reported.** Many ASX companies present an "underlying NPAT" that excludes restructuring/impairment. Extract reported; flag the underlying if disclosed.
- **Relying on aggregator sites for base financials.** Aggregators re-express filings. Always go to the filing itself.

## Geographic and segment mix

Secondary priority, but include if accessible:

- Revenue by segment for the latest 2-3 years
- EBIT by segment (if disclosed)
- Revenue by geography for the latest 2-3 years
- Customer concentration if top customer > 10% or top 3 > 30% (usually disclosed in risk factors or notes)

## Summary discipline

Your `summary` should state:

1. Which periods are cleanly extracted vs. which are gappy
2. Any period-regime issues (e.g., "FY-1 year-end balance sheet not cleanly extractable from audited accounts; captured via company financial summary page")
3. The net cash bridge from the most recent balance sheet — because this will anchor EV downstream
4. Any quality-of-earnings flags material enough for the Lead to address in Section 4
