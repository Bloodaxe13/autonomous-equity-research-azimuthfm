# CUV Live Run Remediation Plan - 2026-04-20

> For Hermes: use strict TDD and verification-driven-automation for every task below. Do not rerun the full live CUV pipeline until the pre-implementation harnesses exist and the targeted acceptance tests for the touched surface pass.

Goal: close the gap between the current live CUV run and the repository spec so the system can produce a spec-compliant, internally consistent, citation-backed, red-teamed report on an ASX small-cap without silent data substitution or redundant subagent sprawl.

Architecture:
- Treat the failures as three classes: contract enforcement, research-process control, and financial truth-surface integrity.
- Build a narrow failing test or reproducible harness for each defect before implementation.
- Fix lower layers before prompt tuning when the failure is infrastructural (PDF/OCR, date/as-of integrity, stage gating).

Tech stack:
- Python runtime in `src/`
- pytest in `tests/`
- prompt contracts in `prompts/`
- schemas in `schemas/`
- live runtime in `src/live_autonomous_runtime.py` and `src/responses_agent_runtime.py`

---

## Global execution rules

1. No production code changes for a defect until the corresponding failing test or reproducible harness exists.
2. Prefer the smallest general mechanism that fixes the class of failure.
3. No deterministic fallback to fake LLM-stage success.
4. After each task:
   - run the targeted test(s)
   - run a narrow integration check if relevant
   - only then move on
5. Full live rerun happens once all blocking tasks are green.

---

## Phase 0 - Stabilize the verification loop first

### Task 0.1: Create a live-run regression packet fixture from the failed CUV run
Objective: preserve the current failure as a reproducible offline fixture so future tests do not require paid live reruns.

Files:
- Create: `tests/fixtures/live_cuv_run/lead_bad_output.json`
- Create: `tests/fixtures/live_cuv_run/subagent_outputs/` (copy representative parsed outputs)
- Modify: `tests/test_live_autonomous_runtime.py`

Test first:
- Add a fixture-driven test that loads the recorded bad lead payload and confirms `FinalReport.model_validate(...)` fails with the same class of errors.

Run:
- `pytest -q tests/test_live_autonomous_runtime.py::test_recorded_cuv_bad_lead_output_fails_validation`

Expected before implementation:
- PASS as a regression capture of the old bad payload.

Verification:
- Ensure the test uses the saved artifact from `/tmp/azimuthfm-live-real/.../lead/parsed_output.json` and not a hand-written simplification.

### Task 0.2: Add a stage-level harness for lead/red-team/citation execution with fake tool outputs
Objective: make stage-gating and schema enforcement testable without a paid live run.

Files:
- Modify: `tests/test_live_autonomous_runtime.py`
- Possibly create helper: `tests/helpers/fake_responses_runtime.py`

Test first:
- Build a fake client / fake executor path that can emit:
  - valid lead output
  - invalid lead output
  - valid red-team output
  - valid citation output

Run:
- `pytest -q tests/test_live_autonomous_runtime.py -k stage`

Expected before implementation:
- failing tests for missing downstream stage execution guarantees.

---

## Phase 1 - Lock down stage contracts and mandatory downstream gating

### Task 1.1: Test lead uses strict `FinalReport` tool schema at completion time
Objective: verify the recent lead schema patch is real and stays real.

Files:
- Modify: `tests/test_live_autonomous_runtime.py`

Test first:
- Add a test asserting the lead stage binds `complete_task` to `FinalReport.model_json_schema()` rather than the generic payload schema.

Run:
- `pytest -q tests/test_live_autonomous_runtime.py::test_lead_complete_task_uses_final_report_schema`

Expected:
- should pass after the already-applied patch.

### Task 1.2: Test red-team and citation are hard-gated after a valid lead report
Objective: prove they are required downstream stages, not best-effort extras.

Files:
- Modify: `tests/test_live_autonomous_runtime.py`
- Modify: `src/live_autonomous_runtime.py` if orchestration glue is missing or ambiguous

Test first:
- Add a test where lead returns a valid `FinalReport` and assert:
  - red-team runs
  - citation runs after red-team success
  - final packet is not considered complete until both succeed
- Add a test where lead fails and assert:
  - red-team and citation do not run
  - failure is explicit at lead stage

Run:
- `pytest -q tests/test_live_autonomous_runtime.py -k 'red_team or citation or gating'`

Implementation note:
- If current orchestration only wires these stages in the ad hoc run script, move the canonical sequence into a tested runtime/orchestrator function.

### Task 1.3: Test stage artifacts are written for all required stages
Objective: ensure successful red-team and citation stages persist artifacts just like subagents and lead.

Files:
- Modify: `tests/test_restartable_failure_handling.py`
- Modify: `tests/test_live_autonomous_runtime.py`

Run:
- `pytest -q tests/test_restartable_failure_handling.py tests/test_live_autonomous_runtime.py -k artifacts`

---

## Phase 2 - Fix time/as-of integrity and silent data substitution

### Task 2.1: Introduce explicit as-of semantics tests for historical, period-end, and current facts
Objective: stop mixing FY2025, H1 FY2026, and current-snapshot values under one label.

Files:
- Modify: `src/contracts_runtime.py` if new fact metadata types are needed
- Modify: lead/subagent prompts if they need explicit date semantics
- Create/modify tests: `tests/test_payload_normalization.py`, `tests/test_live_autonomous_runtime.py`

Test first:
- Add tests that distinguish:
  - `fy2025_cash`
  - `h1fy2026_cash`
  - `current_market_cap`
- Add a failure test showing a report cannot label a later-period cash balance as FY2025 cash without explicit provenance.

Run:
- `pytest -q tests/test_payload_normalization.py tests/test_live_autonomous_runtime.py -k 'as_of or timing or period'`

Implementation approach:
- add explicit `source_date`, `retrieval_date`, and optionally `data_as_of` propagation to normalized findings where missing
- require lead synthesis to preserve time regime in header/financial sections
- reject ambiguous substitution when the label and source period differ

### Task 2.2: Freeze valuation anchor inputs in one typed object before writing
Objective: ensure the values used for market cap, EV, target price, current price, and cash bridge are declared once and reused consistently.

Files:
- Modify: `src/contracts_runtime.py`
- Modify: `src/live_autonomous_runtime.py`
- Add tests: `tests/test_live_autonomous_runtime.py`, `tests/test_relative_valuation.py`, `tests/test_reverse_dcf.py`

Test first:
- Add a test that inconsistent valuation anchors between header, body, and computation log fail validation.

Run:
- `pytest -q tests/test_live_autonomous_runtime.py tests/test_relative_valuation.py tests/test_reverse_dcf.py -k anchor`

---

## Phase 3 - Fix PDF ingestion and OCR fallback at the tool layer

### Task 3.1: Characterize current PDF extraction quality on known ASX annual reports
Objective: create a measurable gate for when plain PDF extraction is unusable.

Files:
- Create: `tests/test_runtime_web_pdf_extraction.py`
- Possibly create: `scripts/pdf_quality_probe.py`

Test first:
- Use one or more saved CLINUVEL annual report PDFs or stable sample PDFs.
- Define a quality heuristic, for example:
  - minimum extracted text length
  - printable-character ratio
  - keyword hit rate for expected headings (`Revenue`, `Cash`, `Annual Report`)
- Write failing tests for PDFs that currently return junk.

Run:
- `pytest -q tests/test_runtime_web_pdf_extraction.py`

### Task 3.2: Implement OCR fallback in `web_fetch` / PDF handling path
Objective: if PDF extraction quality is poor, route through OCR automatically.

Files:
- Modify: `src/tools/runtime_web.py`
- Add dependency wiring if needed
- Add tests: `tests/test_runtime_web_pdf_extraction.py`, `tests/test_runtime_web.py`

Test first:
- expected behavior:
  - readable-text PDFs still use the fast path
  - low-quality text PDFs trigger OCR path
  - output includes path decision metadata

Run:
- `pytest -q tests/test_runtime_web_pdf_extraction.py tests/test_runtime_web.py`
- `python3 -m py_compile src/tools/runtime_web.py`

Verification:
- on a real sample PDF, verify extracted text now contains key financial headings and enough numeric content to support downstream parsing.

---

## Phase 4 - Enforce subagent discipline and facet deduplication

### Task 4.1: Encode canonical initiation facet set and dedupe rules
Objective: stop the lead from spawning overlapping subagents and uncontrolled gap-fill chains.

Files:
- Modify: `src/live_autonomous_runtime.py` or orchestration surface responsible for subagent dispatch
- Possibly create: `src/facet_planning.py`
- Add tests: `tests/test_live_autonomous_runtime.py`

Test first:
- Add tests that a HIGH-complexity initiation defaults to a capped canonical set, e.g.:
  - business_model_and_pipeline
  - industry_and_competitive_position
  - historical_financials
  - forecasts_guidance_and_consensus
  - news_catalysts_and_corporate_actions
  - peer_set_and_valuation_inputs
  - ownership_governance_management
- Add tests that duplicate/near-duplicate facet requests are rejected or merged.

Run:
- `pytest -q tests/test_live_autonomous_runtime.py -k 'facet or subagent cap or dedupe'`

Implementation note:
- adopt: default target 5-7, hard cap 10 for initiation, absolute safeguard 20
- require explicit reason code for every wave-2/gap-fill dispatch

### Task 4.2: Add dispatch budget telemetry
Objective: make subagent sprawl visible in artifacts and tests.

Files:
- Modify: `src/live_autonomous_runtime.py`
- Add tests: `tests/test_live_autonomous_runtime.py`

Test first:
- assert artifacts contain:
  - total subagents dispatched
  - wave-1 count
  - wave-2/gap-fill count
  - reasons for additional dispatches

---

## Phase 5 - Consensus retrieval fallback ladder

### Task 5.1: Codify consensus-availability states
Objective: separate "no broker coverage", "coverage exists but estimates unavailable", and "consensus retrieved".

Files:
- Modify: `src/contracts_runtime.py`
- Modify: relevant prompts (`prompts/research_subagent.md`, maybe lead prompt)
- Add tests: `tests/test_payload_normalization.py`, `tests/test_live_autonomous_runtime.py`

Test first:
- Add tests asserting the system preserves one of three explicit states:
  - no_coverage
  - coverage_exists_but_consensus_unretrievable
  - consensus_retrieved

Run:
- `pytest -q tests/test_payload_normalization.py tests/test_live_autonomous_runtime.py -k consensus`

### Task 5.2: Implement retrieval fallback protocol
Objective: the forecast facet should not give up after one blocked aggregator.

Files:
- Modify: `prompts/research_subagent.md`
- Modify: any facet-brief builder if present
- Potentially modify: `src/tools/runtime_web.py`
- Add tests: `tests/test_live_autonomous_runtime.py` using fake tool responses

Fallback order to encode:
1. company analyst coverage page
2. directly accessible broker/public summary pages
3. alternate estimate sources
4. explicit unresolved state if estimates still unavailable

Verification:
- fake-tool integration test proving the subagent continues to fallback step 2/3 after a blocked first source

---

## Phase 6 - Enforce report completeness against the full intended spec

### Task 6.1: Expand `FinalReport` / `HeaderBlock` contract to the intended minimum surface
Objective: close schema drift between `docs/specs/...` and runtime contracts.

Files:
- Modify: `src/contracts_runtime.py`
- Modify: `schemas/final_report.schema.json`
- Modify: `prompts/lead_analyst.md`
- Add tests: `tests/test_live_autonomous_runtime.py`

Add the missing enforced surface in stages, not all at once. Minimum additions:
- header metadata for 52-week high/low if available
- ADV / liquidity field(s)
- top holders / free float if available
- explicit catalyst structure
- explicit sensitivity-grid object rather than freeform prose

Test first:
- add failing validation tests for omitted required spec fields once the schema is expanded

### Task 6.2: Require full 5x5 sensitivity grid
Objective: stop 3x3 outputs from passing when spec requires 5x5.

Files:
- Modify: `src/contracts_runtime.py`
- Modify: `src/calculations/sensitivity.py`
- Modify: lead prompt if needed
- Add tests: `tests/test_sensitivity.py`, `tests/test_live_autonomous_runtime.py`

Test first:
- assert exactly 25 cells with required WACC / growth ranges

Run:
- `pytest -q tests/test_sensitivity.py tests/test_live_autonomous_runtime.py -k sensitivity`

### Task 6.3: Require dedicated catalyst objects with timing / probability / impact / monitoring
Objective: stop catalysts from being buried in prose or news sections.

Files:
- Modify: `src/contracts_runtime.py`
- Modify: `schemas/final_report.schema.json`
- Modify: lead prompt
- Add tests: `tests/test_live_autonomous_runtime.py`

---

## Phase 7 - Freeze peer set before multiples and stop peer drift

### Task 7.1: Add a typed frozen peer-set artifact
Objective: prevent random-walk peer selection and post-hoc comp cherry-picking.

Files:
- Modify: `src/contracts_runtime.py`
- Modify: runtime/orchestration path storing memory/checkpoints
- Add tests: `tests/test_live_autonomous_runtime.py`, `tests/test_relative_valuation.py`

Test first:
- assert that once the peer set is frozen for a run, subsequent multiples calculations must consume that frozen set unless an explicit reopen event replaces it

### Task 7.2: Separate peer-identification from peer-multiples extraction cleanly
Objective: one facet chooses peers, another fills values, without overlap.

Files:
- Modify: prompts / brief templates for peer facets
- Add tests: `tests/test_live_autonomous_runtime.py`

---

## Phase 8 - End-to-end acceptance battery before the next live CUV rerun

### Task 8.1: Build a deterministic acceptance checklist for the full run
Objective: define what must be true before paying for another live run.

Files:
- Create: `tests/test_cuv_acceptance_contract.py`

Acceptance gates:
- valid `FinalReport`
- red-team artifact exists
- citation artifact exists
- no duplicate facet dispatches beyond cap
- no ambiguous period substitution for key financial facts
- 5x5 sensitivity grid present
- catalyst section structured correctly
- consensus state explicit

### Task 8.2: Run the narrow local/fixture battery
Run:
- `pytest -q tests/test_live_autonomous_runtime.py tests/test_restartable_failure_handling.py tests/test_payload_normalization.py tests/test_runtime_web_pdf_extraction.py tests/test_sensitivity.py tests/test_relative_valuation.py tests/test_reverse_dcf.py tests/test_cuv_acceptance_contract.py`
- `python3 -m py_compile src/*.py src/tools/*.py src/calculations/*.py`

Expected:
- all green before any new live run

### Task 8.3: Only then rerun the live CUV pipeline
Objective: one paid run, post-fixes, with explicit inspection checklist.

Post-run verification:
1. result file exists and status is completed
2. lead/red-team/citation artifacts all exist
3. read the final report and verify:
   - no period contamination
   - citations attached
   - peer set frozen and visible
   - full sensitivity grid present
   - consensus state explicit
4. compare against the previous failed run packet

---

## Suggested implementation order

1. Phase 0 harnesses
2. Phase 1 stage gating
3. Phase 2 time/as-of integrity
4. Phase 3 PDF/OCR
5. Phase 4 subagent discipline
6. Phase 5 consensus fallback
7. Phase 6 spec completeness
8. Phase 7 peer freeze
9. Phase 8 full acceptance battery
10. live rerun

---

## Definition of done

This remediation plan is complete only when:
- the system emits a valid `FinalReport`
- red-team and citation run as required downstream stages
- PDF-heavy ASX annual reports reliably produce usable text via OCR fallback when needed
- no silent substitution across time regimes occurs
- subagent count stays within enforced initiation budget
- consensus absence is distinguished from consensus retrieval failure
- the report contract enforces the intended minimum spec surface
- a post-fix live CUV run passes the acceptance battery without manual excuse-making
