# CUV Runtime Hardening Plan - 2026-04-21

> For Hermes: use strict TDD and verification-driven-automation for every task below. Use bounded subagent work only for research/review, not for long-running execution. Do not rerun the full live CUV pipeline until the targeted test battery and small live smoke checks for the touched surfaces pass.

Goal: move AZIMUTHFM from “useful but not shippable” to a runtime that can produce a self-contained, source-disciplined, red-team-gated report on CUV and similar ASX small-caps without duplicated research lanes, weak failure observability, or silent source/provenance drift.

Architecture:
- Keep the system simple: strong lead, bounded first-wave facet set, one catch-all gap-fill lane, one red-team gate, one citation gate.
- Strengthen deterministic enforcement only at the interface and reliability layers.
- Treat primary-source truth and structured-secondary scaffolding as separate source classes.
- Make failure artifacts richer than success artifacts.

Tech stack:
- Python runtime in `src/`
- pytest in `tests/`
- prompts in `prompts/`
- schemas/contracts in `src/contracts_runtime.py` and `schemas/`
- live runtime in `src/live_autonomous_runtime.py` and `src/responses_agent_runtime.py`
- local secondary structured data from:
  - `/mnt/c/Users/Daniel/AzimuthAI-Research-V2/artifacts/marketscreener_cache`
  - `/home/daniel/azimuth-fund-ops/src/azimuth_fund_ops/secondary_enrichment_*.py`

---

## What recent research established

1. The spec is not ambiguous on sequencing:
   - Lead -> Red-Team -> re-open if needed -> Citation -> final report.
   - Current runtime still fails to enforce the re-open branch.

2. Prompt-only sprawl control helped materially:
   - the rerun used a clean first-wave facet set plus one `open_questions_gap_fill` lane.
   - avoid adding heavy runtime bureaucracy unless prompt reinforcement clearly fails again.

3. The catalyst/news lane did not fail conceptually; it thrashed:
   - broad 24-month archive-style brief
   - prompt pushed “start wide” + “must fetch” behavior
   - archive/listing surfaces were noisy/truncated
   - max-turn cap was burned on chronology reconstruction

4. Raw failure observability is still too weak:
   - incomplete-agent path persists summary/tool history/repaired output
   - but does not persist raw API payloads, final text, or response IDs in a consistent failure envelope

5. Marketscreener / Azimuth Fund structured financial outputs are useful but not primary truth:
   - they should be treated as trusted structured secondary inputs
   - high-priority for patching/scaffolding/search targeting
   - never silently override primary company/regulator truth

6. Current PDF handling is improved enough for readable PDFs without OCR:
   - PDF-aware extraction via PyMuPDF/pdfplumber/pypdf is in place
   - OCR is intentionally deferred

---

## Global execution rules

1. No production code change for a defect until a failing test, fixture, or deterministic harness exists.
2. Prefer the smallest general mechanism that fixes the failure class.
3. No deterministic fallback to fake LLM-stage success.
4. After each task:
   - run targeted tests
   - run a narrow integration or smoke check if relevant
   - only then move on
5. Full live rerun happens only after all blocking gates in Phase 7 are green.

---

## Phase 0 - Preserve the current regression surface

### Task 0.1: Keep recorded live-run fixtures current
Objective: preserve the latest failed/successful surfaces as reusable regression packets.

Files:
- Existing fixture dir: `tests/fixtures/live_cuv_run/`
- Add if needed: `tests/fixtures/live_cuv_rerun/`

Required artifacts to preserve:
- failed lead payload from first live run
- failed lead validation error
- representative subagent packets
- successful rerun lead / red-team / citation payloads

Verification:
- fixture-driven tests load these artifacts, not hand-written simplifications

---

## Phase 1 - Enforce the spec’s red-team reopen loop

### Task 1.1: Add failing tests for reopen routing
Objective: codify the intended state machine before changing runtime logic.

Files:
- Modify: `tests/test_live_autonomous_runtime.py`

Add failing tests for:
- valid lead -> red-team `strong_counter_case` -> lead reopen -> second red-team -> citation only after surviving
- valid lead -> red-team `covered_ground` -> citation immediately
- valid lead -> red-team `strong_counter_case` twice -> fail closed, do not cite/finalize

Run:
- `pytest -q tests/test_live_autonomous_runtime.py -k 'reopen or red_team or citation'`

### Task 1.2: Implement a bounded reopen loop
Objective: enforce the spec without building a full workflow engine.

Files:
- Modify: `src/live_autonomous_runtime.py`
- Modify: `prompts/lead_analyst.md`

Design:
- one initial lead pass
- one red-team pass
- if `strong_counter_case`:
  - persist reopen request checkpoint/event
  - rerun lead once with:
    - prior report
    - red-team verdict/challenges
    - reopen reason
    - reopen attempt count
  - rerun red-team once
- if second red-team still returns `strong_counter_case`:
  - fail closed
  - do not run citation
- otherwise run citation

Prompt reinforcement:
- tell the lead exactly how to use prior_report + red-team feedback in a reopen pass
- do not let reopen become a free-form new research expedition

### Task 1.3: Make citation a true final gate
Objective: prevent “completed” status when the citation stage still reports unsourced claims.

Files:
- Modify: `src/live_autonomous_runtime.py`
- Modify tests in `tests/test_live_autonomous_runtime.py`

Rule:
- if `citation.unsourced_claims` is non-empty and the claims are not explicitly allowed placeholders, fail closed and require reopen/repair

Verification:
- targeted pytest for reopen + citation gate behavior

---

## Phase 2 - Persist richer raw failure artifacts

### Task 2.1: Add failing tests for incomplete-agent raw artifact persistence
Objective: capture the current observability bug in tests first.

Files:
- Modify: `tests/test_responses_agent_runtime.py`
- Modify: `tests/test_restartable_failure_handling.py`

Required failure artifacts for incomplete runs:
- `raw_api_payloads.json`
- `final_text.txt`
- `response_ids.json`
- `incomplete_tool_history.json`
- `failure_envelope.json`
- `repaired_output.json` if repair succeeds

Run:
- `pytest -q tests/test_responses_agent_runtime.py tests/test_restartable_failure_handling.py -k 'incomplete or failure_envelope or raw_api_payloads'`

### Task 2.2: Enrich `AgentLoopIncomplete` at the source
Objective: failure persistence must be fed from the actual exception payload, not reconstructed later.

Files:
- Modify: `src/responses_agent_runtime.py`

Add to `AgentLoopIncomplete`:
- `prompt_path`
- `response_ids`
- `raw_responses`
- `final_text`
- `started_at`
- `completed_at`
- `duration_ms`

### Task 2.3: Unify failure persistence in the live runtime
Objective: incomplete and validation failures should share a common machine-readable envelope.

Files:
- Modify: `src/live_autonomous_runtime.py`

Add canonical `failure_envelope.json` with:
- `failure_type`
- `run_id`
- `stage`
- `attempt`
- `prompt_path`
- `error`
- `turns`
- `started_at`
- `completed_at`
- `duration_ms`
- `response_ids`
- `tool_counts`
- `artifact_files`
- `restart_from_stage`
- `retrigger_agents`

Verification:
- all failure tests green
- py_compile clean

---

## Phase 3 - Integrate trusted structured secondary data safely

### Task 3.1: Add the source taxonomy before importing anything
Objective: make provenance explicit so structured secondary inputs cannot be mistaken for primary truth.

Files:
- Modify: `src/contracts_runtime.py`
- Modify: `schemas/` only if needed
- Modify: `tests/test_payload_normalization.py`

Minimum added metadata on imported values:
- `authority_class`
- `source_family`
- `source_type`
- `origin`
- `verification_status`
- `captured_at`
- `raw_payload_path`
- `quality_flags`
- `comparability_flags`

Source regime:
- `primary_truth`
- `trusted_structured_secondary`
- `narrative_secondary`
- `low_trust_tertiary`

Policy:
- Marketscreener / Azimuth Fund outputs map to `trusted_structured_secondary`
- never to primary truth

### Task 3.2: Implement the smallest safe importer
Objective: patch sparse line-item gaps without importing all of V2 or old fact stores.

Files:
- Create: `src/structured_secondary.py` (or similarly small module)
- Reuse logic conceptually from:
  - `/home/daniel/azimuth-fund-ops/src/azimuth_fund_ops/secondary_enrichment_adapter.py`
  - `/home/daniel/azimuth-fund-ops/src/azimuth_fund_ops/secondary_enrichment_cache.py`
- Add tests: `tests/test_structured_secondary.py`

First allowed metrics only:
- `roic_pct`
- `eps_revision_3m_pct`

First cache source:
- `/mnt/c/Users/Daniel/AzimuthAI-Research-V2/artifacts/marketscreener_cache`

Do not import as truth yet:
- market cap
- EV
- current price
- derived multiples
- statement line items where primary filings/API already exist

### Task 3.3: Allow structured secondary values into the runtime as scaffolding, not truth
Objective: use structured secondary inputs to patch/scaffold while preserving verification discipline.

Files:
- Modify: `src/live_autonomous_runtime.py`
- Modify: `prompts/lead_analyst.md`
- Modify: `prompts/research_subagent.md`
- Modify: `prompts/citation.md`

Rules:
- can patch sparse tables
- can seed search targeting and lead plans
- can scaffold forecast/valuation inputs
- cannot silently override primary source values
- any primary-vs-secondary conflict becomes a contradiction, not a merge

Verification:
- tests for primary-wins-on-conflict
- tests that structured-secondary values preserve period/provenance metadata
- tests that citation labels them distinctly

---

## Phase 4 - Tighten the catalyst/news lane so it converges

### Task 4.1: Add regression tests for truncated archive thrash
Objective: capture the exact failure mode before patching prompts/runtime.

Files:
- Modify/create: `tests/test_live_autonomous_runtime.py`
- Modify/create: `tests/test_tool_output_limits.py`
- Modify/create: `tests/test_responses_agent_runtime.py`

Test cases:
- repeated archive/listing fetches return truncated metadata-only content
- direct PDFs are usable
- news subagent should stop broad archive reconstruction and return top material events only

### Task 4.2: Tighten the research-subagent prompt
Objective: reduce lane thrash without redesign.

Files:
- Modify: `prompts/research_subagent.md`

Prompt changes:
- soften blanket “must fetch every relevant result” behavior
- for archive/listing pages, fetch at most 1-2 discovery pages
- if 2 consecutive archive/listing fetches are truncated or low-yield, stop broad retrieval
- for news/catalyst tasks, return top 5-8 material events only
- explicitly forbid full-archive reconstruction

### Task 4.3: Tighten the lead’s news-brief instructions
Objective: fix the bad brief shape at the source.

Files:
- Modify: `prompts/lead_analyst.md`

Required wording:
- for `news_catalysts_and_corporate_actions`, ask for top material events only
- no full chronology
- no routine notice enumeration unless clearly price-sensitive
- explicit negative finding allowed for legal/IP if nothing material is found

### Task 4.4: Add one small runtime guard for truncated archive/listing fetches
Objective: reduce repeated low-value archive fetches without building search policing machinery.

Files:
- Modify: `src/responses_agent_runtime.py`

Behavior:
- detect archive/listing URLs with truncated fetch results
- return a machine-readable low-yield signal
- after repeated low-yield listing fetches in one run, discourage more sibling archive fetches

Verification:
- targeted tests green
- small live smoke on the catalyst lane only

---

## Phase 5 - Preserve self-contained report behavior

### Task 5.1: Strengthen final-report cleanliness gates
Objective: the final report should not read like a work log or TODO list.

Files:
- Modify: `prompts/lead_analyst.md`
- Add tests: `tests/test_live_autonomous_runtime.py`

Rules:
- no “this should be followed up” language in final report body
- no process-debug appendix content
- `Items not found` should be `- none` unless a genuinely material uncertainty remains after allowed research passes

### Task 5.2: Decide what is allowed to remain unresolved
Objective: unresolved uncertainty should be investment-relevant, not process-relevant.

Files:
- prompt-only plus tests

Allowed:
- material uncertainty that still affects the investment case after research passes
Not allowed:
- mere retrieval/process failures that should have triggered another pass or a fail-closed state

---

## Phase 6 - Optional but deferred until the above are green: rating policy / NR

This is important but not the first operational fire.

Future direction:
- separate continuous expected return from final label
- add explicit `NR` / `Unrated` / `Insufficient evidence`
- do not let Hold act as abstention
- backtest thresholds before changing policy

Do not implement this in the current tranche unless earlier phases are green.

---

## Phase 7 - Verification battery before the next live rerun

### Required targeted tests
Run at minimum:
- `pytest -q tests/test_live_autonomous_runtime.py`
- `pytest -q tests/test_responses_agent_runtime.py`
- `pytest -q tests/test_restartable_failure_handling.py`
- `pytest -q tests/test_payload_normalization.py`
- `pytest -q tests/test_runtime_web.py`
- `pytest -q tests/test_structured_secondary.py` (once added)
- `pytest -q tests/test_tool_output_limits.py`

### Required smoke checks
1. Catalyst/news lane smoke
- run only the news/catalyst subagent on CUV
- verify it returns top material events without archive-thrash

2. Structured secondary smoke
- import a known ticker’s V2 cache values
- verify provenance metadata and conflict behavior

3. Reopen loop smoke
- fake-client runtime test where:
  - first red-team returns `strong_counter_case`
  - reopened lead revises
  - second red-team returns `weak_counter_case`
  - citation runs

### Required full rerun acceptance gates
Before a paid live CUV rerun is considered successful:
- completed packet emitted
- lead/red-team/citation artifacts all present
- no missing raw failure observability on any incomplete lanes
- red-team reopen path works if triggered
- citation unsourced claims either zero or intentionally fail-closed
- no duplicate overlapping subagent lane explosion
- report reads as self-contained final product
- structured secondary inputs, if used, are visibly tagged and do not override primary truth silently

---

## Suggested implementation order

1. Phase 1 red-team reopen loop
2. Phase 2 richer failure artifacts
3. Phase 3 structured-secondary taxonomy + importer
4. Phase 4 catalyst/news convergence tightening
5. Phase 5 final-report cleanliness enforcement
6. Phase 7 verification battery
7. only then another paid live rerun

---

## Definition of done

This plan is complete only when:
- the runtime enforces Lead -> Red-Team -> re-open if needed -> Citation -> final report
- failed and incomplete agents persist rich raw artifacts
- Marketscreener/Azimuth Fund structured financial outputs can be consumed as trusted structured secondary inputs with explicit provenance and verification status
- the catalyst/news lane converges without archive thrash
- final reports do not emit process-y follow-up language unless a material investment uncertainty truly remains
- the next live CUV rerun passes both technical and analytical quality gates rather than merely completing
