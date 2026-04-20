# Build Plan

This file makes the repository self-describing for future implementation work.

## Canonical precedence

1. `docs/specs/Azimuth Analyst Agent — Complete Build Specification.md`
2. `schemas/*.schema.json`
3. `prompts/*.md`
4. `config/*.yaml`
5. runtime implementation in `src/`

## Recommended build order

1. Contracts
   - Use `schemas/` as the interface surface between agents.
   - Add runtime validation around every tool boundary.
2. Memory store
   - Persist plan, findings waves, findings index, computation log, checkpoints, frozen peer set, and partial report by `run_id`.
3. Tracing
   - Log every agent action and every tool call.
   - Checkpoint after each subagent wave and before writing.
4. Code execution sandbox
   - Deterministic Python runtime for ratios, DCF, reverse DCF, sensitivity tables, and scenario weighting.
5. Calculation library
   - Implement reusable valuation and forecast functions under `src/calculations/`.
6. Tools
   - `run_subagent`
   - `web_search`
   - `web_fetch`
   - `memory_write`
   - `memory_read`
   - `code_execution`
   - `complete_task`
7. Agents
   - Load prompt markdown and validate all inputs/outputs against schema files.
8. Orchestration and integration
   - Wave dispatch, gap analysis, red-team reopen loop, citation pass.
9. Production reliability
   - Error handling, retries, checkpoints, and deploy-safe controls.
10. Scale-out
   - model routing, async subagent dispatch, evaluation harness, and portfolio/scheduler integration.

## Non-negotiable design rules

- No thesis-first writing.
- No inferred numbers.
- No raw search dumps reaching the lead when a subagent can compress them.
- No section-by-section specialist writers.
- No red-teaming in the same context as the lead.

## Definition of done for interface layer

- Prompt files exist for all four roles.
- JSON Schemas exist for every documented contract.
- Config captures model roles, hard limits, and source hierarchy.
- README and docs identify the canonical source and current status.
