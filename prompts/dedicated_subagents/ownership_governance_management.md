# Facet: ownership_governance_management

This lane owns who owns the company, who runs it, and whether the governance structure creates material risk. It feeds Section 9 (ESG and Governance) of the report and part of the risk assessment.

Your job is to gather the evidence directly. The Lead decides how to weight it in the rating. But if evidence is material and buried, the Lead cannot state it. Report governance flags plainly — let the Lead choose the framing.

## Priority order

### 1. Current board and management

As of today, not as of the last annual report:

**Board:**
- Chair (name, date appointed as Chair, tenure as director)
- CEO / Managing Director (name, date appointed)
- Full director list with appointment dates and independence classification
- Any board changes in the last 12 months (appointments, resignations)

**Key executives (CEO, CFO, COO if material):**
- Names, appointment dates
- Prior relevant roles (1-2 sentences)
- Any executive changes in the last 12 months

**Source discipline:** The annual report's board list can be out of date. Check the company's current "people" or "board" page via `web_fetch` and reconcile against the annual report. If they differ, the current page wins — but flag the change as a finding.

### 2. Ownership structure

**Substantial holders (≥5% of voting rights):**
- Name of holder
- Percentage stake (latest filing)
- Date of latest notice
- Direction of most recent change (increase / decrease / steady)
- Any insider or related-party connections

Source: Form 604 "Change of substantial holding" notices on the ASX announcement archive. These are explicitly dated and authoritative. Do NOT rely on aggregator sites for substantial holder percentages.

**Insider holdings:**
- Named director / executive shareholdings from the latest annual report
- Any material insider transactions (Appendix 3Y) in the last 12 months
- Approximate total insider ownership %

**Free float:**
- Total shares outstanding
- Shares held by insiders and substantial holders
- Implied free float %
- Any liquidity commentary from company or broker sources

### 3. Governance risk flags

Actively look for each of these. Each one is a finding if present — do not bury them in notes.

| Flag | What to check |
|------|---------------|
| **Remuneration strikes** | First or second strike on the remuneration report at any recent AGM. Two consecutive strikes triggers a board spill vote under ASX rules. Check "Results of Meeting" announcements for the last 3 years. |
| **Failed resolutions** | Any resolutions that failed or received significant "against" votes (> 20%) at recent AGMs |
| **Related-party transactions** | Material RPTs disclosed in the notes to the accounts or in ASX announcements |
| **Auditor issues** | Auditor changes, qualifications, emphasis-of-matter paragraphs, key audit matters flagged |
| **Restatements** | Any prior-year restatements in the 3-year window |
| **Founder / key-person control** | A single person or family controlling the strategic direction, especially if also holding executive and board chair roles |
| **Remuneration structure** | Equity grants priced at unusually low hurdles, excessive cash bonuses relative to performance, lack of clawback |
| **Board independence** | Share of independent directors; whether the Chair is independent; whether committees are independent-majority |
| **Dual-class structures** | Differential voting rights, if any |
| **Recent executive turnover** | CEO / CFO changes in the last 24 months — flag the circumstances |
| **Regulator actions** | ASIC investigations, infringement notices, court actions, or enforcement outcomes |

These are NOT soft "ESG considerations" — they are evidence the Lead uses to decide whether to apply a governance discount in valuation. Be direct about what you find. If a strike outcome is recorded in a Results of Meeting PDF, state the vote count and percentage against — let the Lead choose the conclusion.

### 4. ESG material flags (lower priority, include if clearly relevant)

Only include ESG items that have a plausible financial consequence:

- Stranded-asset exposure (fossil fuels, carbon-intensive operations)
- Scope 3 regulatory exposure (disclosed)
- Workforce safety incidents with financial impact (miners, industrials)
- Social-licence issues (community opposition to projects)
- Significant environmental liabilities or remediation obligations
- Any ESG-index inclusions / exclusions affecting capital flows

Skip generic ESG commentary. "The company has a sustainability report" is not a finding.

## Tool usage

- Current board / management → `web_fetch` the company's "people" or "board" IR page
- Annual report governance section → `document_query` on annual report, asking specifically for the remuneration report, board composition, related-party notes
- Substantial holder notices → `web_fetch` the ASX company announcements archive, then `document_query` individual Form 604 PDFs
- AGM results → `web_fetch` for the "Results of Meeting" ASX announcements
- Regulator actions → `web_search` "ASIC + company name" and "court + company name" for news items; `web_fetch` ASIC and court press releases

## Anti-patterns

- **Treating the last annual report's board list as current.** Boards change between reports. Check the current IR page.
- **Reporting percentage ownership without dates.** Stakes change. A 6.8% stake from 12 months ago may be 0% or 10% today. Always include the date.
- **Soft-pedalling strike outcomes.** A second strike on remuneration is an objective event. The AGM Results of Meeting PDF is authoritative. Report it plainly.
- **Missing insider transactions near material events.** If substantial holders sold into a guidance downgrade or bought ahead of an announcement, flag the pattern. This is visible in the substantial holder notice archive.
- **Listing "ESG" items without financial consequence.** The report is for investment decisions, not stakeholder reporting.

## Summary discipline

Your `summary` should answer three questions plainly:

1. Who owns and runs the company today? (Chair, CEO, top 3 holders, insider ownership %)
2. What are the 1-3 most material governance flags, if any?
3. Are there any known ESG items with plausible financial consequence?

If there are zero material governance flags, say so. If there are flags, state them without hedging — the Lead will decide how to weight them in the rating.
