# Azimuth Equity Research AZIMUTHFM

Last updated: 2026-04-20 17:28 AEST

Autonomous Equity Research AZIMUTHFM.

## Canonical source of truth

The build is governed by:
- `docs/specs/Azimuth Analyst Agent — Complete Build Specification.md`

If any derivative file conflicts with that spec, the spec wins.

## Current implementation state

Implemented now in this repo:
- prompt layer under `prompts/`
- contract layer under `schemas/`
- config surfaces under `config/`
- calculation library under `src/calculations/`
- JSON memory store under `src/memory/`
- JSONL tracing logger under `src/tracing/`
- tool wrappers under `src/tools/`
- MVP runtime agents under `src/agents/`
- orchestrator under `src/orchestration_runtime.py`
- CUV-only MVP entrypoint under `src/cuv_runtime_entrypoint.py`
- test suite under `tests/`

## Verified now

- `pytest -q`
- `python3 -m py_compile src/contracts_runtime.py src/memory/json_store_runtime.py src/tracing/jsonl_runtime_logger.py src/tools/runtime_web.py src/tools/code_execution_runtime.py src/agents/runtime_agents.py src/orchestration_runtime.py src/cuv_runtime_entrypoint.py src/calculations/__init__.py src/calculations/ratios.py src/calculations/dcf.py src/calculations/relative_valuation.py src/calculations/reverse_dcf.py src/calculations/sensitivity.py src/calculations/scenario_weighting.py tests/test_*.py`
- `python3 -m src.cuv_runtime_entrypoint`

Current result:
- `11 passed`
- CUV-only MVP packet generated successfully

## Important limitation

This repo is not yet a full live production implementation of the final spec.
It is currently an MVP runtime proving:
- orchestration shape
- persistence
- tracing
- calculations
- report packet generation
- red-team pass
- citation pass
- CUV-only test flow

Still to finish for full spec fidelity:
- live lead/subagent execution against the final role prompts
- live OpenAI web search + fetch loop in the orchestrated run
- full institutional data ingestion
- complete DCF/comps/reverse-DCF wiring from live findings
- richer consistency checks and citation enforcement
- report tier specialization beyond the current initiation-focused MVP

## Repo map

- `docs/specs/` — canonical specification
- `docs/BUILD_PLAN.md` — execution plan
- `docs/STATUS.md` — current build status
- `prompts/` — role prompts
- `schemas/` — JSON contracts
- `config/` — model/limit/source configuration
- `src/` — runtime implementation
- `tests/` — verification suite
- `scripts/` — future CLI surfaces
