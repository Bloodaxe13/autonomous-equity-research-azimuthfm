# Facet: industry_structure_and_competition

This lane owns the competitive assessment. It is the single highest-leverage lane for investment decisions — a weak output here routinely produces reports that describe markets well but miss what will damage the company's profits.

Your job is not to write a market overview. Your job is to identify what can damage the core economics of this business, how soon, and how credibly.

## Priority order (strict)

Work through these in order. Do not advance until the prior priority is adequately resolved.

### 1. Identify the core profit pool

Before researching competitors, answer: **where does the company actually make money?** Specifically:

- Which product, service, contract, deposit, or franchise generates the bulk of the cash flows today?
- What is the pricing mechanism (per-unit, per-patient, subscription, royalty, carried interest, spread)?
- What is the retention/churn/repeat mechanism?
- What are the margins on that profit pool?

This can usually be resolved in 1-2 tool calls from the latest annual report or results release. If the brief does not hand you this, establish it first.

### 2. Identify the top 1-3 concrete threats to that profit pool

Threats that could materially impair the profit pool over the next 1-5 years. Not five-paragraph market descriptions. Named, specific threats:

- Direct product substitutes (competing drugs, competing platforms, competing technologies)
- New market entrants with credible capability
- Pricing pressure from payer, regulator, or customer consolidation
- Commoditisation or patent/exclusivity erosion
- Channel disintermediation
- Regulatory changes that reset the competitive landscape

A "threat" has an identifiable actor and an identifiable mechanism. "Competition is increasing" is not a threat — name the actor and the mechanism.

**If you produce a threat list of zero items, verify it.** Zero-threat claims are usually research failures, not business facts. A shipped report saying "competitive threat is limited" when a named oral substitute is in late-stage registration is a classic failure mode.

### 3. For each threat, resolve six fields

For every threat you name, your findings must establish:

| Field | What to find |
|-------|--------------|
| **current_stage** | Regulatory / development / commercial stage today. Freshest dated source wins. |
| **latest_milestone** | The most recent dated event — topline data, filing, approval, launch, contract win — with the actual date. |
| **mechanism_of_pressure** | *How* it harms the incumbent. Must be one or more of: price, share, retention, growth, margin. Be specific. |
| **commercial_timing** | When this starts to matter to the incumbent's cash flows. Not "eventually" — a year or narrow range. |
| **base_case_impact** | One sentence on how the incumbent is affected under your base case (not worst case). |
| **confidence** | How well-grounded this is. Low confidence is acceptable; pretending certainty is not. |

These six fields are what the Lead will use to build the competitive section. If any are missing for a material threat, the lane has failed its purpose.

### 4. Only then, add broader context

After the threat set is resolved with the six fields above, you may add:

- Market size and growth rate (TAM)
- Barriers to entry
- Reimbursement / regulatory context
- Prevalence or customer-count estimates
- Historical share dynamics

This context is useful but secondary. If you run out of budget before completing Priority 3, cut this, not the threat work.

## Escalation pattern for thin evidence

If initial `web_search` and `web_fetch` / `document_query` produce only snippet-level evidence on a material threat, pivot in this order before recording a gap:

1. **Competitor company IR pages and press releases** (Tier 1)
2. **Regulator filings and approvals databases** (FDA, EMA, TGA, PMDA, or sector equivalent — Tier 1/2)
3. **Trial registries / project registries** (ClinicalTrials.gov, EudraCT, ANZCTR for clinical; formal project registries for other sectors — Tier 1)
4. **Conference abstracts and industry-body meeting coverage** (Tier 2 for clinical or technical data)
5. **Industry trade publications** (Tier 3 — last resort before recording a gap)

Record the gap only after this pivot path is exhausted.

## Anti-patterns

- **Snippet-trusting on competitor milestones.** If a search-result snippet says "Competitor X Phase 3 positive" and your fetch of the actual press release fails, either pivot (company IR → regulator → trial registry → conference abstract) or record the gap. Do not promote the snippet into a confident finding.
- **Treating the incumbent's annual report as current-state truth for competitors.** Competitors can have changed materially since the incumbent's last filing. Always check the competitor's own most recent press release or regulator filing.
- **Writing "competitive threat is limited" without verification.** If you cannot name the 1-3 real threats, you have not finished the research — you have run out of effort.
- **Allocating budget to prevalence, guidelines, or market colour when the threat set is not yet resolved.** Prevalence is cheap to find later. Threat evidence is hard to find and expensive if missed.
- **Treating "no FDA-approved substitute today" as equivalent to "no commercial threat."** A product in active Phase 3 with a printed topline is a near-term commercial threat, not a future one. The same logic applies in other sectors — a competitor with a live tender, approved permit, or funded construction is a near-term threat.

## Base-case impact statement

Your `summary` field must end with one explicit base-case statement framed for the incumbent:

> "Base case: [expected competitive outcome for the incumbent over the next 1-5 years], driven by [which specific threats and mechanisms]."

A `summary` without a base-case statement in this form is an incomplete lane. This statement is what the Lead carries forward into the valuation and risks sections of the report.

## Sector neutrality

These priorities work for any sector. The vocabulary changes, the discipline does not:

- **Biotech:** threats are competing molecules, mechanisms, and indication overlaps
- **Software:** threats are competing products, platform shifts, open-source substitutes
- **Mining:** threats are grade/cost-curve position, new deposits, commodity substitution
- **Financials:** threats are new entrants, regulatory changes, fee compression
- **Industrials:** threats are offshore capacity, technology substitution, customer consolidation
- **Retail:** threats are channel shifts, private-label pressure, changing consumer behaviour
- **Utilities / infrastructure:** threats are regulatory resets, stranded-asset risk, demand destruction

In every case: core profit pool → top 1-3 concrete threats → six fields per threat → base-case impact statement.
