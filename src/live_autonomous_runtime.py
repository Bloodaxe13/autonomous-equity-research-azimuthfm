from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import re
from datetime import datetime, timezone

from src.contracts_runtime import CitationOutput, RedTeamVerdict, SubagentFindings, TaskInput
from src.memory.json_store_runtime import JsonMemoryStore
from src.responses_agent_runtime import AgentRunContext, ResponsesAgentLoop, build_default_agent_tools, build_default_prompt_executor
from src.tools.code_execution_runtime import CodeExecutionTool
from src.tools.runtime_web import WebFetchTool, WebSearchTool


@dataclass
class AutonomousEquityResearchRuntime:
    repo_root: Path
    memory_store: JsonMemoryStore
    web_search: WebSearchTool
    web_fetch: WebFetchTool
    code_execution: CodeExecutionTool
    client: Any | None = None
    lead_model: str = "gpt-5"
    subagent_model: str = "gpt-5-mini"
    review_model: str = "gpt-5"
    lead_max_turns: int = 40
    subagent_max_turns: int = 20
    review_max_turns: int = 12

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root)
        self.prompt_dir = self.repo_root / "prompts"
        self.subagent_executor = build_default_prompt_executor(
            memory_store=self.memory_store,
            web_search=self.web_search,
            web_fetch=self.web_fetch,
            code_execution=self.code_execution,
            client=self.client,
            default_model=self.subagent_model,
            max_turns=self.subagent_max_turns,
        )
        self.lead_executor = build_default_prompt_executor(
            memory_store=self.memory_store,
            web_search=self.web_search,
            web_fetch=self.web_fetch,
            code_execution=self.code_execution,
            subagent_runner=self._run_subagent_callback,
            client=self.client,
            default_model=self.lead_model,
            max_turns=self.lead_max_turns,
        )
        self.red_team_executor = build_default_prompt_executor(
            memory_store=self.memory_store,
            web_search=self.web_search,
            web_fetch=self.web_fetch,
            code_execution=self.code_execution,
            client=self.client,
            default_model=self.review_model,
            max_turns=self.review_max_turns,
        )
        self.citation_executor = build_default_prompt_executor(
            memory_store=self.memory_store,
            web_search=self.web_search,
            web_fetch=self.web_fetch,
            code_execution=self.code_execution,
            client=self.client,
            default_model=self.review_model,
            max_turns=self.review_max_turns,
        )

    def run_subagent(self, brief: dict[str, Any], *, run_id: str) -> SubagentFindings:
        tools = build_default_agent_tools(
            web_search=self.web_search,
            web_fetch=self.web_fetch,
            code_execution=self.code_execution,
            memory_store=self.memory_store,
        )
        tools['complete_task'].parameters = SubagentFindings.model_json_schema()
        executor = ResponsesAgentLoop(
            client=self.client,
            tools=tools,
            default_model=self.subagent_model,
            max_turns=self.subagent_max_turns,
        )
        result = executor.run_prompt_file(
            self.prompt_dir / "research_subagent.md",
            user_input={"task_brief": brief},
            prompt_context={"TaskBrief": json.dumps(brief, indent=2, ensure_ascii=False)},
            tool_names=["web_search", "web_fetch", "complete_task"],
            run_id=run_id,
        )
        try:
            return SubagentFindings.model_validate(normalize_subagent_payload(result.final_output))
        except Exception:
            repaired = self._repair_subagent_output(raw_output=result.final_output, brief=brief, run_id=run_id)
            return SubagentFindings.model_validate(normalize_subagent_payload(repaired))

    def run_lead(self, task: TaskInput) -> dict[str, Any]:
        result = self.lead_executor.run_prompt_file(
            self.prompt_dir / "lead_analyst.md",
            user_input={
                "ticker": task.ticker,
                "tier": task.tier.value,
                "run_id": task.run_id,
                "triggering_event": task.triggering_event,
                "prior_report": task.prior_report,
            },
            prompt_context={"TaskJSON": task.model_dump(mode="json")},
            tool_names=["run_subagent", "code_execution", "web_search", "memory_write", "memory_read", "complete_task"],
            run_id=task.run_id,
        )
        return result.final_output

    def run_red_team(self, report: str | dict[str, Any], *, run_id: str) -> RedTeamVerdict:
        result = self.red_team_executor.run_prompt_file(
            self.prompt_dir / "red_team.md",
            user_input={"report": report},
            prompt_context={"Report": report},
            tool_names=["complete_task"],
            run_id=run_id,
        )
        return RedTeamVerdict.model_validate(result.final_output)

    def run_citation(self, report: str | dict[str, Any], findings_index: Any, computation_log: Any, *, run_id: str) -> CitationOutput:
        result = self.citation_executor.run_prompt_file(
            self.prompt_dir / "citation.md",
            user_input={"report": report, "findings_index": findings_index, "computation_log": computation_log},
            prompt_context={"Report": report, "FindingsIndex": findings_index, "ComputationLog": computation_log},
            tool_names=["complete_task"],
            run_id=run_id,
        )
        return CitationOutput.model_validate(result.final_output)

    def _run_subagent_callback(self, brief: dict[str, Any], context: AgentRunContext) -> Any:
        run_id = context.run_id or "subagent-run"
        packet = self.run_subagent(brief, run_id=run_id)
        return packet.model_dump(mode="json")

    def _repair_subagent_output(self, *, raw_output: Any, brief: dict[str, Any], run_id: str) -> Any:
        tools = build_default_agent_tools(
            web_search=self.web_search,
            web_fetch=self.web_fetch,
            code_execution=self.code_execution,
            memory_store=self.memory_store,
        )
        tools['complete_task'].parameters = SubagentFindings.model_json_schema()
        executor = ResponsesAgentLoop(
            client=self.client,
            tools=tools,
            default_model=self.review_model,
            max_turns=self.review_max_turns,
        )
        result = executor.run_prompt_file(
            self.prompt_dir / 'subagent_repair.md',
            user_input={'task_brief': brief, 'raw_payload': raw_output},
            prompt_context={
                'TaskBrief': json.dumps(brief, indent=2, ensure_ascii=False),
                'RawPayload': json.dumps(raw_output, indent=2, ensure_ascii=False, default=str),
            },
            tool_names=['complete_task'],
            run_id=run_id,
        )
        return result.final_output


def normalize_subagent_payload(payload: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            match = re.search(r'\{.*\}', payload, re.DOTALL)
            if not match:
                raise ValueError('Subagent payload was not valid JSON')
            payload = json.loads(match.group(0))
    normalized = dict(payload)
    findings = []
    for item in normalized.get('findings', []) or []:
        entry = dict(item)
        claim = entry.get('claim') or entry.get('statement') or entry.get('fact') or entry.get('title') or ''
        entry['claim'] = claim
        entry['data'] = entry.get('data') or entry.get('value') or entry.get('detail') or claim
        source_ref = entry.get('source_url') or entry.get('url') or entry.get('source') or 'unknown'
        source_tier = entry.get('source_tier', 4)
        if isinstance(source_ref, dict):
            entry['source_url'] = source_ref.get('url') or source_ref.get('href') or 'unknown'
            entry['source_title'] = entry.get('source_title') or entry.get('title') or source_ref.get('title') or source_ref.get('name') or 'Unknown source'
            source_tier = entry.get('source_tier', source_ref.get('source_tier', source_ref.get('tier', 4)))
        else:
            entry['source_url'] = source_ref
            entry['source_title'] = entry.get('source_title') or entry.get('title') or entry.get('document_title') or entry.get('source') or 'Unknown source'
        if source_tier in (None, ''):
            source_tier = 4
        if isinstance(source_tier, str):
            match = re.search(r'(\d+)', source_tier)
            source_tier = int(match.group(1)) if match else 4
        entry['source_tier'] = source_tier
        retrieval_date = entry.get('retrieval_date') or entry.get('retrieved_at') or entry.get('retrieved_on')
        if not retrieval_date:
            retrieval_date = datetime.now(timezone.utc).date().isoformat()
        entry['retrieval_date'] = str(retrieval_date)[:10]
        confidence = entry.get('confidence', 'medium')
        if isinstance(confidence, str):
            lowered = confidence.strip().lower()
            if lowered in {'high', 'medium', 'low'}:
                confidence = lowered
            elif 'high' in lowered:
                confidence = 'high'
            elif 'low' in lowered:
                confidence = 'low'
            else:
                confidence = 'medium'
        if isinstance(confidence, (int, float)):
            confidence = 'high' if confidence >= 0.85 else 'medium' if confidence >= 0.6 else 'low'
        entry['confidence'] = confidence
        entry['notes'] = entry.get('notes', '')
        findings.append(entry)
    normalized['findings'] = findings
    return normalized
