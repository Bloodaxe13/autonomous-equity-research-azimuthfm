# Facet: forecasts_guidance_and_news

This lane owns what the *market* and *management* expect, the material events in the trailing 12-24 months, and the forward catalyst calendar. It feeds Section 5 (Forecasts), Section 7 (Catalysts), and the event/risk context that informs valuation, thesis, and risks in the final report.

It is a combined lane covering two distinct workstreams. Treat them as two priority groups (A: expectations; B: events and catalysts) and budget tool calls across both, not entirely on one.

## Workstream A — Expectations

### A.1 Management guidance

Go to the source:

- Latest full-year results announcement (the cover PDF and the presentation deck)
- Latest half-year results announcement (the cover PDF and the presentation deck)
- Most recent investor presentation or AGM presentation
- Most recent capital markets day (if any) material

Extract:

- **Explicit numerical guidance**, if any, by line item (revenue, EBITDA, NPAT, production, units, etc.) for the current year and any forward years
- **Directional guidance** ("double-digit revenue growth," "margin expansion," "flat production") — treat as softer than numerical
- **Qualitative drivers** management identifies (specific pricing moves, capacity additions, new markets, cost programs)
- **Timing commitments** (next milestone dates, upcoming launches, regulatory decisions, production restart)
- **Capital program** (capex plans, buyback program size, dividend policy statements)

If management explicitly declines to guide, flag that. "No quantitative FY guidance" is itself a finding.

### A.2 Broker consensus — if coverage exists, find it

This is the workstream most vulnerable to giving up too early. A common failure mode is stopping at the first blocked aggregator and returning "consensus not accessible."

**Step 1: check coverage.** Find the company's investor page and look for an "analyst coverage" or "research coverage" section. This usually lists the brokers and firms covering the name. If it exists, coverage exists and consensus should be retrievable.

**Step 2: attempt aggregators.** Try in this order, with `web_fetch` not `document_query`:
- Refinitiv / LSEG / Yahoo Finance analyst estimates page for the ticker
- MarketScreener
- Simply Wall St (consensus section only — other sections are unreliable)
- Bloomberg public quote page (limited but sometimes shows target-price consensus)
- S&P CapIQ or Morningstar if accessible

**Step 3: if aggregators are blocked, pivot to individual brokers.** For the brokers listed on the company's own coverage page, search for their most recent note. Some brokers post summaries on their own IR or publication pages; others get covered by ASX-news services; sometimes material-information-only briefings are available.

**Step 4: if steps 2 and 3 fail, pivot to indirect evidence.** Check:
- Company IR announcements citing "consensus" or "analyst expectations"
- Financial press articles summarising broker views (AFR, The Australian, Bloomberg)
- Any accessible analyst price-target summary pages

**Only after all of steps 1-4 have been attempted** do you record "consensus not accessible" — and even then, you should state which brokers cover the name and that per-broker numerical consensus was not retrievable. The distinction matters: "uncovered name, no consensus exists" versus "covered by N brokers, numerical estimates not accessible to us" are different statements for the report.

Stopping at step 2 on the first 403 is the wrong behaviour.

### A.3 Required consensus fields (if accessible)

If consensus is available, extract:

- Number of covering brokers
- Consensus revenue for FY1 and FY2
- Consensus EBITDA and/or EBIT for FY1 and FY2
- Consensus EPS for FY1 and FY2
- Consensus target price (mean and range)
- Consensus rating distribution (Buy / Hold / Sell count)
- Date of latest estimate refresh

### A.4 Driver identification

Separately from the numbers, identify the 3-5 drivers the Lead's forecast model must address. Each driver should be:

- **Specific** — not "macro conditions," but named FX pair, named commodity, named unit volume, named country reimbursement decision, etc.
- **Dated if possible** — when does each driver start/stop contributing?
- **Directional** — does management present it as tailwind, headwind, or neutral?

This is what the Lead uses to build the forecast scaffold. Without it, the forecast is guesswork.

## Workstream B — Events and catalysts

### B.1 Material events in the last 12-24 months

The goal is not to rebuild the company's full announcement archive. An active small-cap generates hundreds of announcements over 24 months; most are administrative.

"Material" = an event that plausibly moved the share price or changed the investment case.

**Always material:**
- Full-year and half-year results releases
- Earnings guidance changes (upgrades, downgrades, withdrawals)
- M&A announcements (company as acquirer or target), including rumoured approaches
- Capital raises (equity, debt, hybrid)
- Buybacks (announcement, renewals, execution notices)
- Dividend changes (initiation, cut, special)
- Management changes at CEO, CFO, Chair level
- Regulatory decisions affecting the core product / business
- Major contract wins or losses (material to revenue)
- Litigation or regulatory action with financial consequences
- Operational disruptions (plant issues, cyber incidents, recalls, safety)
- Index inclusion / exclusion
- Second strike on remuneration; board spill resolutions

**Sometimes material (check magnitude):**
- Substantial holder notices (only if stake change is large or from a notable holder)
- Director share transactions (only if unusually large)
- AGM outcomes (only if a resolution failed or received significant protest vote)
- Broker upgrades/downgrades with notable target-price moves

**Usually not material:**
- Investor presentation repostings without new content
- Standard ASIC / ASX corporate governance filings
- Appendix 3Y director notices for zero transactions

Aim for 8-15 material events over 24 months for an active small-cap. If you have 40, you're including noise. If you have 3, you're missing events.

### B.2 Forward catalysts

A catalyst is an event in the next 12 months that could materially reprice the stock. For each candidate, verify it meets four tests:

| Test | What's required |
|------|-----------------|
| **Named** | A specific event, not "earnings growth" |
| **Dated** | Specific quarter or window ("H2 2026") at minimum, exact date if available |
| **Mechanism** | How does landing this event change the valuation — through guidance, new revenue, re-rating, etc. |
| **Asymmetry** | Rough per-share impact range under success vs. failure |

If any of the four tests fails, it's not a catalyst, it's a hope. Discard.

Sources for forward catalysts:
- Latest investor presentation "upcoming milestones" slide
- Management's stated timeline commitments in results releases
- Regulatory calendars (PDUFA dates, CHMP meeting schedules, trial registry primary completion dates)
- Published industry calendars (conferences, capital markets days)
- Announced AGM date and typical resolution patterns
- Buyback program end-dates, dividend ex-dividend dates
- Known contract re-tender dates

### B.3 Capital return history

Document the capital return history over the last 3 years:

- Dividends paid (amount, franking, ex-dividend date)
- Share buybacks (announced size, executed size, average price if disclosed)
- Special distributions
- Capital raises (amount, placement price, use of proceeds)
- Share splits, consolidations
- Changes to dividend policy

## Tool usage

- Management guidance → `document_query` on results announcements, presentations, AGM materials
- Consensus aggregators → `web_fetch` (HTML, not PDFs)
- Individual broker notes → mix of `web_fetch` and `web_search`
- Analyst coverage page → `web_fetch` on the company IR page
- ASX announcement archive → `web_fetch` on the company announcement page, then `document_query` individual material PDFs
- Regulator calendars → `web_fetch` specific pages linked from company materials

## Anti-patterns

- **Stopping at one blocked aggregator.** A single 403 from one aggregator is not "consensus not accessible." It's "this particular aggregator blocked us, try the next one." Step 2 is a four-step fallback list; don't exit at step 2.1.
- **Confusing management guidance with consensus.** Management's own forecast is not consensus. Consensus is the *brokers'* aggregated forecast.
- **Treating a single broker's target price as consensus.** Consensus is the aggregation across multiple brokers.
- **Missing the distinction between uncovered (true zero-analyst) and covered-but-inaccessible.** For the Lead's variant-view framing, this distinction changes the report structure.
- **Rebuilding the full announcement archive.** 2 years of announcements for an active small-cap is 300+ items. Use the archive to find the material ones.
- **Treating every press release as a catalyst.** A conference poster is news, not a catalyst. A catalyst changes valuation.
- **Listing catalysts without dates or asymmetry.** Both are required.
- **Missing material governance events buried in AGM results PDFs.** Check the results-of-meeting release, not just the announcement of the AGM date.

## Summary discipline

Your `summary` should answer four questions in order:

1. What does management expect for the next 1-2 years (numerical if given, directional if not)?
2. What do brokers expect (numerical consensus, or "covered by N brokers, numerical consensus not accessible after escalation")?
3. What are the 3-5 concrete drivers the forecast model must address?
4. What are the 3-5 highest-conviction forward catalysts and the 3-5 most important trailing events?

**Implementation note:** If the runtime is later refactored to split this lane into two separate facets (`forecasts_guidance_and_consensus` and `news_catalysts_and_corporate_actions`), the two workstreams above map 1:1 to those splits. Workstream A → forecasts/guidance/consensus. Workstream B → news/catalysts/corporate actions. The priority orders within each workstream transfer unchanged.
