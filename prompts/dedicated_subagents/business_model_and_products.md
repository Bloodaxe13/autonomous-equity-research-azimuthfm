# Facet: business_model_and_products

This lane owns what the company does economically today and what product / program / project set could change that over the next 1-5 years. It feeds Section 2 (Business Description) and part of Section 3 (the company side of competitive position).

## Priority order

### 1. The revenue engine

State crisply, every claim sourced:

- **Primary product, service, contract, or franchise** that drives the bulk of revenue today
- **Revenue model**: transactional, recurring (SaaS/subscription), royalty, spread/NIM (banks), carried interest (asset managers), one-time project, ad revenue, commodity price × volume, etc.
- **Pricing mechanism**: per-unit, per-patient, per-seat, per-tonne, per-transaction, % of AUM, etc.
- **Customer type and concentration**: enterprise vs. retail, B2B vs. B2C, top-customer concentration if material (>10% of revenue from one customer, or >30% from top three)
- **Geographic mix** of revenue (and who it's sold to, if different from where it's booked)

### 2. Segment economics

If the company reports multiple segments, extract for each segment in the latest full year:

- Revenue (absolute and % of group)
- Operating profit / EBIT (absolute and % of group)
- EBIT margin
- Growth rate vs. prior year

If the company does not segment-report, state that explicitly rather than fabricating segments. Many small-caps do not report segments at all, or report only geographic (not product) segments.

### 3. The product / pipeline / project set

What's in development that could become or expand revenue in the next 1-5 years. Structure every item with these fields:

| Field | What to find |
|-------|--------------|
| **Asset** | Name of the product, program, project, contract, or deposit |
| **Stage** | Where it is today — Phase 2, FEED, pilot, beta, preliminary economic assessment, construction, ramp-up, etc. |
| **Indication / use case / market** | What problem it solves or opportunity it addresses |
| **Next milestone** | The next dated event that would change its status |
| **Timing** | When that milestone is expected |
| **Capital required** | If material and disclosed |

Sector vocabulary changes, the structure does not:
- **Biotech:** every clinical-stage asset, with phase and primary endpoint
- **Miners:** every project with resource/reserve status, grade, and stage (exploration / PFS / DFS / construction / production)
- **Industrials:** every major backlog contract with counterparty, value, and duration
- **Software:** every material product or module, with launch/beta status
- **Financials / asset managers:** material new fund launches, new distribution channels, platform migrations

**Do not promote rhetorical pipeline items** ("continued innovation," "strategic initiatives," "ongoing optimisation") into the pipeline table. If an asset has no name, no stage, and no next milestone, it is not pipeline — it is marketing copy.

### 4. Strategic shifts in the last 12-24 months

Has the company done any of the following?

- Suspended or de-prioritised a program or segment (this changes the forward pipeline materially and is often buried in the results release MD&A)
- Entered a new geography or exited one
- Material M&A (acquired, divested, spun off)
- Restructured the operating model
- Changed primary distribution channels
- Rebranded or repositioned

One to three findings, sourced.

## Tool usage

- Business description and segment economics → `document_query` on the latest annual report (the segment note)
- Pipeline detail → mix of annual report, investor presentations, clinical trial registries (biotechs), JORC/43-101 reports (miners), ASX announcements for material contract wins
- Strategic shifts → recent ASX announcements plus latest annual report MD&A section plus results-release presentation

## Anti-patterns

- **Quoting marketing copy as business description.** "Leading innovative platform for..." is not a business description. "Subscription SaaS billed per-seat, 87% of revenue from enterprises >$100M ARR, 68% US / 22% EU / 10% APAC" is.
- **Listing pipeline items without stages or dates.** A pipeline entry with no next milestone is noise, not signal.
- **Assuming the annual report pipeline is still current.** Companies suspend or reprioritise programs between annual reports — check the latest half-year announcement and material ASX releases.
- **Merging investigational assets with commercial products.** Explicitly distinguish approved/launched/contracted vs. in-development.

## Summary discipline

Your `summary` should answer: "What is this company, economically, and what is the realistic forward trajectory before valuation?"
