# Facet: peers_and_valuation_inputs

This lane owns the peer set and the inputs the Lead needs for Section 6 (Valuation). It is the single lane most vulnerable to cherry-picking — a peer set chosen after seeing the multiples is a peer set built to support a desired conclusion. Your job is to produce a defensible peer set **before** the Lead computes anything.

Your output is upstream of the Lead's required `canonical_valuation_inputs` block. Gather the raw evidence and comparability notes the Lead will need to populate `peer_table`, valuation reconciliation, and current market-anchor context.

## Priority order

### 1. Peer selection — rules-based, in this order

Apply these filters sequentially. Do not skip the order.

**Filter 1: GICS sub-industry match.**
Start with all listed companies in the same 8-digit GICS sub-industry as the target. Primary exchange: ASX. Broaden to other markets only if the sub-industry on ASX is thin (<3 candidates).

**Filter 2: Size band.**
Target size band: 0.2× to 5× the target's market cap. For a ~A$500m ASX small-cap, that's A$100m to A$2.5bn. If fewer than 3 peers match, widen to 0.1× to 10×.

**Filter 3: Geography preference order.**
ASX first. Then (in order): LSE AIM, TSX-V, NZX, SGX, NASDAQ / NYSE small-cap. Cross-listing is fine; include only if the sub-industry is thin on ASX.

**Filter 4: Business model match.**
Same primary revenue model (product vs. service vs. royalty; B2B vs. B2C; capital-light vs. capital-heavy). A pre-revenue peer is **not** a comparable for a commercial-stage company even in the same sub-industry. State the model match explicitly.

**Filter 5: Exclusions.**
Exclude any peer with:
- M&A transaction in progress (target or acquirer)
- Currently distressed or in restructuring
- >50% revenue in a completely different business line (pure holding companies, conglomerates where the relevant business is < half of the group)
- Recently de-listed or primary listing moved

**Output:** 3-10 peers. Minimum 3, maximum 10. If you cannot find 3 after widening all filters, say so explicitly — the Lead will use DCF-primary valuation instead of comps. Do not pad to reach a target count.

For each peer retained, record the selection reasoning: "included because [GICS match, size band match, model match]" in the finding notes.

### 2. Peer financial snapshot

For each peer in the final set, extract from the peer's own most recent filings (annual / half-year / 10-K / 20-F — use `document_query`):

- Exchange and ticker
- Latest revenue (with period label)
- Latest EBITDA (if disclosed) or EBIT
- Latest net profit / net loss
- Latest reported free cash flow
- Most recent balance-sheet cash and debt
- 5-year revenue CAGR (if 5 years available; else shorter window with period flagged)
- Latest EBIT or EBITDA margin
- Latest ROE and ROIC (if computable from disclosures)

**Do not use aggregator sites for the base financials.** Go to the peer's own filing. Aggregators re-express filings and you cannot cite them with the same confidence.

Market cap data is the exception — aggregators (CompaniesMarketCap, Yahoo Finance, Google Finance) are acceptable for current market cap because prices move daily and the peer's own filing is stale the day after publication.

### 3. Multiples — do NOT compute them yourself

Multiples are computed by the Lead via `code_execution` after the peer set is frozen. Your job is to hand over the raw inputs (revenue, EBITDA, EBIT, net income, cash, debt, shares outstanding, current market cap). The Lead runs the division.

Why: if you pre-compute multiples, the Lead will be tempted to accept yours without reconciliation, and period-mismatch errors propagate silently. If the Lead runs the computation via `code_execution`, the system's tool-based discipline catches them.

### 4. Sub-industry-specific valuation inputs

Beyond standard comps, surface any sector-specific valuation inputs:

- **Miners:** NAV per share, resource grade, reserves, per-oz or per-tonne production cost, mine life
- **Biotechs:** pipeline risk-adjusted NPV inputs if industry-standard, probability-of-success base rates for relevant phases
- **REITs:** NAV per share, implied cap rate, FFO, AFFO
- **Financials:** book value, tangible book, ROTE, NIM, cost-to-income ratio
- **Asset managers:** AUM, management fee rate, performance fee rate
- **Industrials:** order book / backlog (for long-cycle businesses)

One to three findings, from the company's own disclosures, not industry averages.

### 5. Current market anchor for the target

**Defer to deterministic runtime context where supplied.** Azimuth's runtime provides deterministic current market data (current price, market cap, 52-week high/low, shares outstanding) via `DeterministicLeadContext`. When the Lead's brief indicates these fields are supplied deterministically, do NOT retrieve or overwrite them — the Lead uses the deterministic value as primary truth and any freeform web retrieval creates a silent two-source conflict.

**Only when deterministic context does NOT supply a field, or explicitly marks it as unavailable**, retrieve via `web_fetch`:

- Current share price (cite source and timestamp)
- Current market cap (shares outstanding × price)
- 52-week high and low
- 3-month average daily value traded (A$m)
- Free float estimate (from ownership lane if already run; else from company disclosures)

When you retrieve market-snapshot fields, use `period_label: "Current"` and `data_as_of: <today>` and state explicit provenance.

## Tool usage

- Peer identification → `web_search` for "[sub-industry] ASX listed companies", "[sub-industry] small cap peer set", then refine
- Peer financials → `document_query` on each peer's most recent annual report or 10-K
- Peer market caps → `web_fetch` on CompaniesMarketCap, Yahoo Finance, or Google Finance
- Target market data → use deterministic context if supplied; else `web_fetch` on Yahoo Finance, Google Finance, or ASX quote page

## Anti-patterns

- **Peer-set laundering.** Selecting peers after seeing which multiples give a desired target price. Your peer set is frozen at the end of this lane, before any valuation runs.
- **Padding the peer set to 10.** If 4 peers defensibly match, 4 is the correct answer.
- **Using pre-revenue peers for commercial-stage companies.** The business-model filter exists to catch this. A pre-revenue biotech has revenue CAGR meaninglessly because the base is zero.
- **Mixing cycle positions.** For cyclicals (miners, industrials), picking all peers at cycle peaks creates a biased multiple set. Note cycle position in the peer reasoning.
- **Computing multiples in the subagent.** Hand over raw line items. Let the Lead's `code_execution` compute.
- **Quoting aggregator-computed multiples as facts.** EV/EBITDA from an aggregator is a computation — if their period or EV definition differs from yours, your multiple differs. Always go to the underlying financials.
- **Retrieving current market data when deterministic context supplies it.** This creates two truths for the same field. Defer to deterministic.

## Summary discipline

Your `summary` should state:

1. The final peer set as a bullet list (ticker / exchange / market cap / business-model match)
2. Any notable limitations (thin peer set, imperfect model match, cycle-position issues)
3. The target's current market anchor — from deterministic context if supplied, else from retrieved sources with explicit provenance
4. Any sector-specific valuation inputs surfaced

**The peer set you return in this lane is final.** The Lead will freeze it in memory and compute all multiples from it.
