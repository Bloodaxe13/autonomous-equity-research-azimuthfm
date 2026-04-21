# Dedicated Subagent Prompts — Integration Guide

## What's in this directory

- `_base.md` — shared base prompt (tool discipline, output schema, hard limits, source tiers, epistemic honesty). Single source of truth for all seven lanes.
- Seven lane-specific facet files, matching the current AZIMUTHFM runtime facet names exactly:
  - `business_model_and_products.md`
  - `industry_structure_and_competition.md`
  - `historical_financials.md`
  - `forecasts_guidance_and_news.md`
  - `ownership_governance_management.md`
  - `peers_and_valuation_inputs.md`
  - `open_questions_gap_fill.md`

## Architecture

Each subagent's system prompt is composed at runtime as:

```
system_prompt = read(_base.md) + "\n\n" + read({facet}.md) + "\n\n## Your task brief\n\n" + brief_as_markdown
```

The base carries what never changes per-lane (tool schema, output contract, source tiers, epistemic rules). The facet file carries lane-specific priorities and anti-patterns. The brief (written by the Lead per-ticker) carries what to find for *this* company.

**Why inheritance and not seven standalone files:** Seven standalone files duplicate the base content, and when the output schema changes or a source tier needs updating, you edit seven files and drift creeps in. With `_base.md` + lane files, you edit one file for shared changes and the lane file for lane changes. Each lane file is 70-170 lines; the base is 130 lines.

## Wiring into `live_autonomous_runtime.py`

Minimal change to the subagent dispatcher:

```python
BASE_PROMPT_PATH = "prompts/dedicated_subagents/_base.md"
LANE_PROMPT_DIR = "prompts/dedicated_subagents"

def build_subagent_system_prompt(facet: str, current_date: str) -> str:
    base = read_file(BASE_PROMPT_PATH)
    lane = read_file(f"{LANE_PROMPT_DIR}/{facet}.md")
    # Template substitution for current_date
    base = base.replace("{{.CurrentDate}}", current_date)
    return base + "\n\n" + lane

# When spawning a subagent:
system_prompt = build_subagent_system_prompt(brief["facet"], today_iso())
# Pass `system_prompt` to the model; pass the brief itself as the user message
```

The `{{.TaskBrief}}` template placeholder in `_base.md` gets substituted by the user-message content (the brief), not by runtime templating. Either let the dispatcher handle brief injection in the user message (recommended), or substitute into the system prompt before dispatch. The former keeps the system prompt stable per-lane.

## What happens if the Lead dispatches a facet not in this directory

The runtime should fall back to `research_subagent.md` (the current shared prompt) with a warning logged. This preserves behaviour for any non-standard facets the Lead spawns and makes the new system a superset, not a replacement.

## Runtime facet name alignment (verified)

These filenames match the current runtime facet names:

| Runtime facet name | File |
|-------------------|------|
| `business_model_and_products` | `business_model_and_products.md` |
| `industry_structure_and_competition` | `industry_structure_and_competition.md` |
| `historical_financials` | `historical_financials.md` |
| `forecasts_guidance_and_news` | `forecasts_guidance_and_news.md` |
| `ownership_governance_management` | `ownership_governance_management.md` |
| `peers_and_valuation_inputs` | `peers_and_valuation_inputs.md` |
| `open_questions_gap_fill` | `open_questions_gap_fill.md` |

If the runtime later splits `forecasts_guidance_and_news` into `forecasts_guidance_and_consensus` and `news_catalysts_and_corporate_actions`, that file's content is already structured as two workstreams (A: expectations; B: events) that map 1:1 to the split. Section A moves to the forecasts file; Section B moves to the news file. No rewrite needed.

## What this does not change

- `lead_analyst.md` — unchanged. The Lead still writes dynamic briefs per-ticker. The Lead is agnostic to how the subagent prompt is composed.
- `red_team.md`, `citation.md`, `subagent_repair.md` — unchanged.
- The runtime brief schema (`SubagentBrief`) — unchanged. The `facet` field in the brief now determines which lane file loads alongside `_base.md`.
- Output contract (`SubagentFindings`) — unchanged. It lives in `_base.md` and applies to all lanes.

## Migration plan

1. Drop `_base.md` and the seven lane files into `prompts/dedicated_subagents/`.
2. Wire `build_subagent_system_prompt` into the dispatcher with a fallback to `prompts/research_subagent.md`.
3. Run on a non-CUV test ticker to verify the system works end-to-end on a new company (do not run on CUV first — CUV tests whether the prompt catches CUV's known failure modes, which it will trivially. A different ticker tests whether the discipline generalises).
4. After the test ticker succeeds, the shared `prompts/research_subagent.md` can be retired or kept as the fallback default.
