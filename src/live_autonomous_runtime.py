from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import re
import shutil
from datetime import datetime, timezone

from src.contracts_runtime import (
    CitationOutput,
    FinalReport,
    FindingIndexItem,
    RedTeamVerdict,
    ReportPacket,
    SourceMetadata,
    SubagentFindings,
    TaskInput,
)
from src.memory.json_store_runtime import JsonMemoryStore
from src.responses_agent_runtime import AgentLoopIncomplete, AgentRunContext, ResponsesAgentLoop, _tool_counts, build_default_agent_tools
from src.structured_secondary import build_structured_secondary_context
from src.tools.code_execution_runtime import CodeExecutionTool
from src.tools.runtime_documents import OpenAIDocumentToolkit
from src.tools.runtime_web import WebFetchTool, WebSearchTool


@dataclass
class PipelineStageError(RuntimeError):
    run_id: str
    stage: str
    artifact_dir: Path
    message: str

    def __post_init__(self) -> None:
        super().__init__(self.message)


@dataclass
class AutonomousEquityResearchRuntime:
    repo_root: Path
    memory_store: JsonMemoryStore
    web_search: WebSearchTool
    web_fetch: WebFetchTool
    code_execution: CodeExecutionTool
    client: Any | None = None
    document_toolkit: OpenAIDocumentToolkit | None = None
    lead_model: str = "gpt-5.4"
    subagent_model: str = "gpt-5.4-mini"
    review_model: str = "gpt-5.4"
    lead_max_turns: int = 40
    subagent_max_turns: int = 20
    review_max_turns: int = 12
    lead_max_output_tokens: int = 100000
    subagent_max_output_tokens: int = 100000
    review_max_output_tokens: int = 100000
    max_reopen_attempts: int = 1

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root)
        if self.document_toolkit is None:
            try:
                self.document_toolkit = OpenAIDocumentToolkit(client=self.client, cache_dir=Path(self.memory_store.root) / '_document_cache')
            except Exception:
                self.document_toolkit = None
        self.prompt_dir = self.repo_root / "prompts"

    def run(self, task: TaskInput) -> ReportPacket:
        lead_recovered = False
        try:
            report = self.run_lead(task)
        except PipelineStageError as exc:
            if exc.stage != 'lead':
                raise
            report = self._build_degraded_final_report(task, exc)
            lead_recovered = True
        self._snapshot_stage_attempt(task.run_id, 'lead', 0)
        self.memory_store.write(task.run_id, 'draft_report', report.model_dump(mode='json'))
        self.memory_store.write(task.run_id, 'computation_log', [entry.model_dump(mode='json') for entry in report.computation_log])
        self.memory_store.append_event(
            task.run_id,
            'checkpoints',
            {
                'stage': 'before_red_team',
                'attempt': 0,
                'rating': report.rating,
                'price_target_aud': report.price_target_aud,
                'lead_recovered': lead_recovered,
            },
        )

        red_team: RedTeamVerdict | None = None
        for attempt in range(self.max_reopen_attempts + 1):
            red_team = self.run_red_team(report.model_dump(mode='json'), run_id=task.run_id)
            self._snapshot_stage_attempt(task.run_id, 'red_team', attempt)
            self.memory_store.write(task.run_id, 'red_team', red_team.model_dump(mode='json'))
            self.memory_store.append_event(
                task.run_id,
                'checkpoints',
                {
                    'stage': 'after_red_team',
                    'attempt': attempt,
                    'verdict': red_team.verdict.value,
                    'counter_rating': red_team.red_team_counter_rating,
                },
            )
            if red_team.verdict.value != 'strong_counter_case':
                break
            if attempt >= self.max_reopen_attempts:
                stage_dir = Path(self.memory_store.root) / task.run_id / 'agent_artifacts' / 'red_team'
                self._persist_gate_failure(
                    run_id=task.run_id,
                    stage='red_team',
                    stage_dir=stage_dir,
                    error='Red-team remained strong after maximum reopen attempts; fail closed before citation.',
                    response_ids=[],
                    tool_counts={},
                    completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
                    attempt=attempt,
                )
                raise PipelineStageError(
                    run_id=task.run_id,
                    stage='red_team',
                    artifact_dir=stage_dir,
                    message='Red-team remained strong after reopen; citation aborted.',
                )
            self.memory_store.append_event(
                task.run_id,
                'checkpoints',
                {
                    'stage': 'red_team_reopen_requested',
                    'attempt': attempt + 1,
                    'reason': red_team.verdict_reasoning,
                },
            )
            report = self.run_lead(
                TaskInput(
                    ticker=task.ticker,
                    tier=task.tier,
                    run_id=task.run_id,
                    triggering_event=f'{task.triggering_event} | reopen_after_red_team_attempt_{attempt + 1}',
                    prior_report={
                        'report': report.model_dump(mode='json'),
                        'red_team': red_team.model_dump(mode='json'),
                        'reopen_attempt': attempt + 1,
                    },
                )
            )
            self._snapshot_stage_attempt(task.run_id, 'lead', attempt + 1)
            self.memory_store.write(task.run_id, 'draft_report', report.model_dump(mode='json'))
            self.memory_store.write(task.run_id, 'computation_log', [entry.model_dump(mode='json') for entry in report.computation_log])
            self.memory_store.append_event(
                task.run_id,
                'checkpoints',
                {
                    'stage': 'red_team_reopen_completed',
                    'attempt': attempt + 1,
                    'rating': report.rating,
                    'price_target_aud': report.price_target_aud,
                },
            )

        assert red_team is not None
        citation = self.run_citation(
            report.model_dump(mode='json'),
            [item.model_dump(mode='json') for item in report.findings_index],
            [entry.model_dump(mode='json') for entry in report.computation_log],
            run_id=task.run_id,
        )
        self.memory_store.write(task.run_id, 'citation', citation.model_dump(mode='json'))
        if self._has_blocking_unsourced_claims(citation):
            stage_dir = Path(self.memory_store.root) / task.run_id / 'agent_artifacts' / 'citation'
            self._persist_gate_failure(
                run_id=task.run_id,
                stage='citation',
                stage_dir=stage_dir,
                error='Citation stage returned unsourced claims; fail closed.',
                response_ids=[],
                tool_counts={},
                completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
                attempt=0,
                extra={'unsourced_claims': citation.unsourced_claims},
            )
            raise PipelineStageError(
                run_id=task.run_id,
                stage='citation',
                artifact_dir=stage_dir,
                message='Citation stage returned blocking unsourced claims.',
            )
        self.memory_store.append_event(
            task.run_id,
            'checkpoints',
            {'stage': 'finalized', 'sources': len(citation.source_list)},
        )

        plan = self.memory_store.read(task.run_id, 'plan', {})
        findings_wave_1 = self.memory_store.read(task.run_id, 'findings_wave_1', [])
        subagent_findings = [SubagentFindings.model_validate(item) for item in findings_wave_1]
        subagent_briefs = []
        for item in self.memory_store.read(task.run_id, 'subagent_briefs', []):
            try:
                from src.contracts_runtime import SubagentBrief
                subagent_briefs.append(SubagentBrief.model_validate(item))
            except Exception:
                continue

        return ReportPacket(
            task=task,
            plan=plan,
            subagent_briefs=subagent_briefs,
            subagent_findings=subagent_findings,
            report=report,
            red_team=red_team,
            citation=citation,
            artifacts={},
        )

    def run_subagent(self, brief: dict[str, Any], *, run_id: str) -> SubagentFindings:
        document_query_tool = self._document_query_callback if self.document_toolkit is not None else None
        tools = build_default_agent_tools(
            web_search=self.web_search,
            web_fetch=self.web_fetch,
            code_execution=self.code_execution,
            memory_store=self.memory_store,
            document_query_tool=document_query_tool,
        )
        tools['complete_task'].parameters = SubagentFindings.model_json_schema()
        executor = ResponsesAgentLoop(
            client=self.client,
            tools=tools,
            default_model=self.subagent_model,
            max_turns=self.subagent_max_turns,
            max_output_tokens=self.subagent_max_output_tokens,
        )
        try:
            result = executor.run_prompt_file(
                self.prompt_dir / "research_subagent.md",
                user_input={"task_brief": brief},
                prompt_context={"TaskBrief": json.dumps(brief, indent=2, ensure_ascii=False)},
                tool_names=[name for name in ["web_search", "web_fetch", "document_query", "complete_task"] if name in tools],
                run_id=run_id,
            )
            try:
                packet = SubagentFindings.model_validate(normalize_subagent_payload(result.final_output))
            except Exception:
                repaired = self._repair_subagent_output(raw_output=result.final_output, brief=brief, run_id=run_id)
                packet = SubagentFindings.model_validate(normalize_subagent_payload(repaired))
            self._persist_agent_artifacts(run_id, f"subagent_{brief.get('facet', 'unknown')}", result, packet.model_dump(mode='json'))
            return packet
        except AgentLoopIncomplete as exc:
            repaired = self._repair_subagent_output(
                raw_output=exc.final_text or json.dumps(exc.tool_history, ensure_ascii=False, default=str),
                brief=brief,
                run_id=run_id,
            )
            packet = SubagentFindings.model_validate(normalize_subagent_payload(repaired))
            self._persist_incomplete_agent_artifacts(run_id, f"subagent_{brief.get('facet', 'unknown')}", exc, repaired)
            return packet

    def run_lead(self, task: TaskInput) -> FinalReport:
        structured_secondary = build_structured_secondary_context(task.ticker)
        self.memory_store.write(task.run_id, 'structured_secondary_context', structured_secondary)
        document_query_tool = self._document_query_callback if self.document_toolkit is not None else None
        tools = build_default_agent_tools(
            web_search=self.web_search,
            web_fetch=self.web_fetch,
            code_execution=self.code_execution,
            memory_store=self.memory_store,
            subagent_runner=self._run_subagent_callback,
            document_query_tool=document_query_tool,
        )
        tools['complete_task'].parameters = FinalReport.model_json_schema()
        executor = ResponsesAgentLoop(
            client=self.client,
            tools=tools,
            default_model=self.lead_model,
            max_turns=self.lead_max_turns,
            max_output_tokens=self.lead_max_output_tokens,
        )
        result = executor.run_prompt_file(
            self.prompt_dir / "lead_analyst.md",
            user_input={
                "ticker": task.ticker,
                "tier": task.tier.value,
                "run_id": task.run_id,
                "triggering_event": task.triggering_event,
                "prior_report": task.prior_report,
                "structured_secondary_context": structured_secondary,
            },
            prompt_context={
                "TaskJSON": task.model_dump(mode="json"),
                "StructuredSecondaryContext": json.dumps(structured_secondary, indent=2, ensure_ascii=False),
            },
            tool_names=[name for name in ["run_subagent", "document_query", "code_execution", "web_search", "web_fetch", "memory_write", "memory_read", "complete_task"] if name in tools],
            run_id=task.run_id,
        )
        stage_dir = self._persist_agent_artifacts(task.run_id, "lead", result, result.final_output)
        normalized_output, normalization_warnings = normalize_final_report_payload(result.final_output)
        if normalization_warnings:
            (stage_dir / 'normalization_warnings.json').write_text(
                json.dumps(normalization_warnings, indent=2, ensure_ascii=False, default=str),
                encoding='utf-8',
            )
        try:
            report = FinalReport.model_validate(normalized_output)
        except Exception as exc:
            self._persist_validation_failure(task.run_id, "lead", stage_dir, result, exc)
            raise PipelineStageError(
                run_id=task.run_id,
                stage="lead",
                artifact_dir=stage_dir,
                message=f"Lead stage failed strict FinalReport validation: {exc}",
            )
        (stage_dir / 'parsed_output.json').write_text(json.dumps(report.model_dump(mode='json'), indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        return report

    def run_red_team(self, report: str | dict[str, Any], *, run_id: str) -> RedTeamVerdict:
        tools = build_default_agent_tools(
            web_search=self.web_search,
            web_fetch=self.web_fetch,
            code_execution=self.code_execution,
            memory_store=self.memory_store,
        )
        tools['complete_task'].parameters = RedTeamVerdict.model_json_schema()
        executor = ResponsesAgentLoop(
            client=self.client,
            tools=tools,
            default_model=self.review_model,
            max_turns=self.review_max_turns,
            max_output_tokens=self.review_max_output_tokens,
        )
        result = executor.run_prompt_file(
            self.prompt_dir / "red_team.md",
            user_input={"report": report},
            prompt_context={"Report": report},
            tool_names=["complete_task"],
            run_id=run_id,
        )
        stage_dir = self._persist_agent_artifacts(run_id, "red_team", result, result.final_output)
        try:
            verdict = RedTeamVerdict.model_validate(result.final_output)
        except Exception as exc:
            verdict = self._build_degraded_red_team_verdict(report=report, stage_dir=stage_dir, error=exc)
        (stage_dir / 'parsed_output.json').write_text(json.dumps(verdict.model_dump(mode='json'), indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        return verdict

    def run_citation(self, report: str | dict[str, Any], findings_index: Any, computation_log: Any, *, run_id: str) -> CitationOutput:
        tools = build_default_agent_tools(
            web_search=self.web_search,
            web_fetch=self.web_fetch,
            code_execution=self.code_execution,
            memory_store=self.memory_store,
        )
        tools['complete_task'].parameters = CitationOutput.model_json_schema()
        executor = ResponsesAgentLoop(
            client=self.client,
            tools=tools,
            default_model=self.review_model,
            max_turns=self.review_max_turns,
            max_output_tokens=self.review_max_output_tokens,
        )
        result = executor.run_prompt_file(
            self.prompt_dir / "citation.md",
            user_input={"report": report, "findings_index": findings_index, "computation_log": computation_log},
            prompt_context={"Report": report, "FindingsIndex": findings_index, "ComputationLog": computation_log},
            tool_names=["complete_task"],
            run_id=run_id,
        )
        stage_dir = self._persist_agent_artifacts(run_id, "citation", result, result.final_output)
        try:
            citation = CitationOutput.model_validate(result.final_output)
        except Exception as exc:
            citation = self._build_degraded_citation_output(report=report, stage_dir=stage_dir, error=exc, raw_output=result.final_output)
        (stage_dir / 'parsed_output.json').write_text(json.dumps(citation.model_dump(mode='json'), indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        return citation

    def _run_subagent_callback(self, brief: dict[str, Any], context: AgentRunContext) -> Any:
        run_id = context.run_id or "subagent-run"
        packet = self.run_subagent(brief, run_id=run_id)
        return packet.model_dump(mode="json")

    def _document_query_callback(self, arguments: dict[str, Any], _: AgentRunContext) -> Any:
        if self.document_toolkit is None:
            raise RuntimeError("document_query requested but document toolkit is unavailable")
        return self.document_toolkit.analyze(
            question=str(arguments.get('question', '')),
            document_urls=list(arguments.get('document_urls') or []),
            document_paths=list(arguments.get('document_paths') or []),
            mode=str(arguments.get('mode') or 'auto'),
            task_type=str(arguments.get('task_type') or 'qa'),
            max_num_results=int(arguments.get('max_num_results') or 5),
            debug=bool(arguments.get('debug', False)),
        )

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
            max_output_tokens=self.review_max_output_tokens,
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

    def _persist_agent_artifacts(self, run_id: str, stage: str, result, parsed_output: Any) -> Path:
        root = Path(self.memory_store.root) / run_id / 'agent_artifacts'
        root.mkdir(parents=True, exist_ok=True)
        stage_root = root / stage
        stage_root.mkdir(parents=True, exist_ok=True)
        (stage_root / 'summary.json').write_text(json.dumps({
            'prompt_path': result.prompt_path,
            'turns': result.turns,
            'completed_via_tool': result.completed_via_tool,
            'response_ids': result.response_ids,
            'started_at': result.started_at,
            'completed_at': result.completed_at,
            'duration_ms': result.duration_ms,
            'tool_counts': result.tool_counts,
            'tool_history_length': len(result.tool_history),
        }, indent=2, ensure_ascii=False), encoding='utf-8')
        (stage_root / 'tool_history.json').write_text(json.dumps(result.tool_history, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        (stage_root / 'raw_api_payloads.json').write_text(json.dumps(result.raw_responses, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        (stage_root / 'response_ids.json').write_text(json.dumps(result.response_ids, indent=2, ensure_ascii=False), encoding='utf-8')
        (stage_root / 'response_text.txt').write_text(result.response_text or '', encoding='utf-8')
        tool_errors = [
            {
                'turn': item.get('turn'),
                'tool': item.get('tool'),
                'call_id': item.get('call_id'),
                'error_type': item.get('result', {}).get('error_type'),
                'error': item.get('result', {}).get('error'),
            }
            for item in result.tool_history
            if isinstance(item.get('result'), dict) and item.get('result', {}).get('ok') is False
        ]
        if tool_errors:
            (stage_root / 'tool_error_warnings.json').write_text(json.dumps(tool_errors, indent=2, ensure_ascii=False), encoding='utf-8')
        (stage_root / 'parsed_output.json').write_text(json.dumps(parsed_output, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        return stage_root

    def _persist_validation_failure(self, run_id: str, stage: str, stage_dir: Path, result, exc: Exception) -> None:
        failure = {
            'stage': stage,
            'error': str(exc),
            'response_ids': result.response_ids,
            'tool_counts': result.tool_counts,
            'completed_at': result.completed_at,
            'restart_from_stage': stage,
            'retrigger_agents': [stage],
            'recommended_context_files': self._recommended_context_files(stage_dir),
        }
        (stage_dir / 'validation_error.json').write_text(json.dumps(failure, indent=2, ensure_ascii=False), encoding='utf-8')
        self._write_failure_envelope(
            run_id=run_id,
            stage=stage,
            stage_dir=stage_dir,
            failure_type='validation_error',
            error=str(exc),
            turns=result.turns,
            prompt_path=result.prompt_path,
            response_ids=result.response_ids,
            tool_counts=result.tool_counts,
            started_at=result.started_at,
            completed_at=result.completed_at,
            duration_ms=result.duration_ms,
            attempt=0,
            retrigger_agents=[stage],
        )
        restart_plan = {
            'run_id': run_id,
            'failed_stage': stage,
            'artifact_dir': str(stage_dir),
            'response_ids': result.response_ids,
            'restart_hint': f'Restart from {stage} using saved raw API payloads and tool history.',
        }
        stage_dir.parent.parent.mkdir(parents=True, exist_ok=True)
        (stage_dir.parent.parent / 'restart_plan.json').write_text(json.dumps(restart_plan, indent=2, ensure_ascii=False), encoding='utf-8')

    def _persist_incomplete_agent_artifacts(self, run_id: str, stage: str, exc: AgentLoopIncomplete, repaired_output: Any) -> None:
        root = Path(self.memory_store.root) / run_id / 'agent_artifacts'
        root.mkdir(parents=True, exist_ok=True)
        stage_root = root / stage
        stage_root.mkdir(parents=True, exist_ok=True)
        (stage_root / 'incomplete_summary.json').write_text(json.dumps({
            'error': str(exc),
            'prompt_path': exc.prompt_path,
            'turns': exc.turns,
            'response_ids': exc.response_ids,
            'started_at': exc.started_at,
            'completed_at': exc.completed_at,
            'duration_ms': exc.duration_ms,
            'tool_counts': _tool_counts(exc.tool_history),
            'tool_history_length': len(exc.tool_history),
        }, indent=2, ensure_ascii=False), encoding='utf-8')
        (stage_root / 'incomplete_tool_history.json').write_text(json.dumps(exc.tool_history, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        (stage_root / 'raw_api_payloads.json').write_text(json.dumps(exc.raw_responses, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        (stage_root / 'response_ids.json').write_text(json.dumps(exc.response_ids, indent=2, ensure_ascii=False), encoding='utf-8')
        (stage_root / 'final_text.txt').write_text(exc.final_text or '', encoding='utf-8')
        self._write_failure_envelope(
            run_id=run_id,
            stage=stage,
            stage_dir=stage_root,
            failure_type='incomplete_agent_loop',
            error=str(exc),
            turns=exc.turns,
            prompt_path=exc.prompt_path,
            response_ids=exc.response_ids,
            tool_counts=_tool_counts(exc.tool_history),
            started_at=exc.started_at,
            completed_at=exc.completed_at,
            duration_ms=exc.duration_ms,
            attempt=0,
            retrigger_agents=[stage],
        )
        (stage_root / 'repaired_output.json').write_text(json.dumps(repaired_output, indent=2, ensure_ascii=False, default=str), encoding='utf-8')

    def _build_degraded_final_report(self, task: TaskInput, exc: PipelineStageError) -> FinalReport:
        stage_dir = Path(exc.artifact_dir)
        raw_payload = self._read_json_file(stage_dir / 'parsed_output.json') or {}
        normalized_payload, normalization_warnings = normalize_final_report_payload(raw_payload)
        raw_dict = normalized_payload if isinstance(normalized_payload, dict) else {}
        rating = self._coerce_rating(raw_dict.get('rating') or raw_dict.get('header_block', {}).get('rating'), default='Hold')
        current_price = self._coerce_float(raw_dict.get('header_block', {}).get('current_price_aud'), default=1.0)
        price_target = self._coerce_float(raw_dict.get('price_target_aud') or raw_dict.get('header_block', {}).get('price_target_aud'), default=current_price)
        implied_return = self._coerce_float(raw_dict.get('implied_return_pct') or raw_dict.get('header_block', {}).get('implied_return_pct'), default=0.0)
        degraded_payload = {
            'ticker': raw_dict.get('ticker') or task.ticker,
            'tier': task.tier.value,
            'generated_at': raw_dict.get('generated_at') or datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
            'version': raw_dict.get('version') or '0.1.0-degraded',
            'header_block': {
                'ticker': raw_dict.get('ticker') or task.ticker,
                'company_name': raw_dict.get('header_block', {}).get('company_name') or f'{task.ticker} degraded report',
                'report_title': raw_dict.get('header_block', {}).get('report_title') or f'{task.ticker} degraded initiation',
                'report_date': raw_dict.get('header_block', {}).get('report_date') or datetime.now(timezone.utc).date().isoformat(),
                'report_type': task.tier.value,
                'rating': rating,
                'price_target_aud': price_target,
                'current_price_aud': current_price,
                'implied_return_pct': implied_return,
                'market_cap_aud_m': self._coerce_float(raw_dict.get('header_block', {}).get('market_cap_aud_m')),
                'net_cash_aud_m': self._coerce_float(raw_dict.get('header_block', {}).get('net_cash_aud_m')),
                'primary_valuation_method': raw_dict.get('header_block', {}).get('primary_valuation_method') or 'DegradedFallback',
                'valuation_summary': raw_dict.get('header_block', {}).get('valuation_summary') or 'Degraded report generated from raw lead output after validation failure.',
                'generated_at': raw_dict.get('header_block', {}).get('generated_at') or datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
            },
            'sections': self._build_degraded_sections(raw_dict, exc),
            'computation_log': [],
            'findings_index': self._build_degraded_findings_index(raw_dict, stage_dir, normalization_warnings),
            'rating': rating,
            'price_target_aud': price_target,
            'implied_return_pct': implied_return,
        }
        report = FinalReport.model_validate(degraded_payload)
        (stage_dir / 'degraded_report.json').write_text(json.dumps(report.model_dump(mode='json'), indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        return report

    def _build_degraded_red_team_verdict(self, *, report: str | dict[str, Any], stage_dir: Path, error: Exception) -> RedTeamVerdict:
        ticker = self._extract_report_field(report, 'ticker', default='UNKNOWN')
        rating = self._coerce_rating(self._extract_report_field(report, 'rating', default='Hold'), default='Hold')
        verdict = RedTeamVerdict.model_validate(
            {
                'ticker': ticker,
                'report_rating': rating,
                'red_team_counter_rating': rating,
                'verdict': 'weak_counter_case',
                'counter_thesis': 'Red-team output schema failed, so this is a degraded pass-through verdict generated from raw output.',
                'three_strongest_challenges': [],
                'missed_risks': [f'Degraded red-team validation fallback: {error}'],
                'disagreements_with_calculations': [],
                'verdict_reasoning': 'Degraded red-team verdict generated to keep the pipeline moving after a schema failure.',
            }
        )
        (stage_dir / 'degraded_output.json').write_text(json.dumps(verdict.model_dump(mode='json'), indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        return verdict

    def _build_degraded_citation_output(self, *, report: str | dict[str, Any], stage_dir: Path, error: Exception, raw_output: Any) -> CitationOutput:
        raw_text = ''
        if isinstance(raw_output, str):
            raw_text = raw_output
        elif isinstance(raw_output, dict):
            raw_text = json.dumps(raw_output, ensure_ascii=False, indent=2, default=str)
        elif raw_output is not None:
            raw_text = str(raw_output)
        annotated_report = raw_text.strip() or (report if isinstance(report, str) else json.dumps(report, ensure_ascii=False, indent=2, default=str))
        citation = CitationOutput.model_validate(
            {
                'annotated_report': annotated_report,
                'source_list': [],
                'computation_log': [],
                'unsourced_claims': [f'Degraded citation validation fallback: {error}'],
            }
        )
        (stage_dir / 'degraded_output.json').write_text(json.dumps(citation.model_dump(mode='json'), indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        return citation

    def _build_degraded_sections(self, raw_dict: dict[str, Any], exc: PipelineStageError) -> dict[str, str]:
        sections = raw_dict.get('sections') if isinstance(raw_dict.get('sections'), dict) else {}
        appendix = sections.get('appendix') or ''
        appendix_suffix = (
            '\n\nSources reviewed\n- raw lead output artifact\n\n'
            'Items not found\n- degraded report generated after strict validation failure\n\n'
            f'Computation notes\n- Degraded report generated due to lead validation failure: {exc.message}'
        )
        return {
            'investment_thesis': sections.get('investment_thesis') or 'Degraded report generated from raw lead output.',
            'business_description': sections.get('business_description') or 'Degraded business description retained because the original lead output was only partially valid.',
            'industry_competitive': sections.get('industry_competitive') or 'Degraded industry/competitive section retained from partial lead output.',
            'financial_analysis': sections.get('financial_analysis') or 'Degraded financial analysis retained from partial lead output.',
            'forecasts': sections.get('forecasts') or 'Degraded forecast section retained from partial lead output.',
            'valuation': sections.get('valuation') or 'Degraded valuation section retained from partial lead output.',
            'catalysts': sections.get('catalysts') or 'Degraded catalysts section retained from partial lead output.',
            'risks': sections.get('risks') or 'Degraded risks section retained from partial lead output.',
            'esg_governance': sections.get('esg_governance') or 'Degraded ESG/governance section retained from partial lead output.',
            'appendix': (appendix + appendix_suffix).strip(),
        }

    def _build_degraded_findings_index(self, raw_dict: dict[str, Any], stage_dir: Path, normalization_warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for item in raw_dict.get('findings_index') or []:
            if not isinstance(item, dict):
                continue
            try:
                findings.append(FindingIndexItem.model_validate(item).model_dump(mode='json'))
            except Exception as item_exc:
                normalization_warnings.append(
                    {
                        'path': 'findings_index[]',
                        'error': str(item_exc),
                        'action': 'dropped_invalid_fact',
                    }
                )
        if not findings:
            findings.append(
                FindingIndexItem.model_validate(
                    {
                        'facet': 'degraded_runtime_recovery',
                        'claim': 'Degraded report generated from raw lead output after validation failure.',
                        'source_url': f'file://{stage_dir / "parsed_output.json"}',
                        'source_title': 'Lead raw output artifact',
                        'source_tier': 4,
                        'confidence': 'low',
                    }
                ).model_dump(mode='json')
            )
        if normalization_warnings:
            (stage_dir / 'normalization_warnings.json').write_text(json.dumps(normalization_warnings, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        return findings

    @staticmethod
    def _extract_report_field(report: str | dict[str, Any], key: str, *, default: Any = None) -> Any:
        if isinstance(report, dict):
            return report.get(key, default)
        return default

    @staticmethod
    def _coerce_rating(value: Any, *, default: str = 'Hold') -> str:
        if isinstance(value, str):
            normalized = value.strip().capitalize()
            if normalized in {'Buy', 'Hold', 'Sell'}:
                return normalized
        return default

    @staticmethod
    def _coerce_float(value: Any, default: float | None = None) -> float | None:
        try:
            if value in (None, ''):
                return default
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _read_json_file(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _snapshot_stage_attempt(self, run_id: str, stage: str, attempt: int) -> None:
        root = Path(self.memory_store.root) / run_id / 'agent_artifacts'
        stage_root = root / stage
        if not stage_root.exists():
            return
        snapshot_root = root / f'{stage}_attempt_{attempt}'
        if snapshot_root.exists():
            shutil.rmtree(snapshot_root)
        shutil.copytree(stage_root, snapshot_root)

    @staticmethod
    def _recommended_context_files(stage_dir: Path) -> list[str]:
        candidates = [
            stage_dir / 'summary.json',
            stage_dir / 'incomplete_summary.json',
            stage_dir / 'tool_history.json',
            stage_dir / 'incomplete_tool_history.json',
            stage_dir / 'raw_api_payloads.json',
            stage_dir / 'response_ids.json',
            stage_dir / 'final_text.txt',
            stage_dir / 'parsed_output.json',
            stage_dir / 'repaired_output.json',
        ]
        return [str(path) for path in candidates if path.exists()]

    def _write_failure_envelope(
        self,
        *,
        run_id: str,
        stage: str,
        stage_dir: Path,
        failure_type: str,
        error: str,
        turns: int,
        prompt_path: str,
        response_ids: list[str],
        tool_counts: dict[str, Any],
        started_at: str,
        completed_at: str,
        duration_ms: int,
        attempt: int,
        retrigger_agents: list[str],
        extra: dict[str, Any] | None = None,
    ) -> None:
        envelope = {
            'failure_type': failure_type,
            'run_id': run_id,
            'stage': stage,
            'attempt': attempt,
            'prompt_path': prompt_path,
            'error': error,
            'turns': turns,
            'started_at': started_at,
            'completed_at': completed_at,
            'duration_ms': duration_ms,
            'response_ids': response_ids,
            'tool_counts': tool_counts,
            'artifact_files': self._recommended_context_files(stage_dir),
            'restart_from_stage': stage,
            'retrigger_agents': retrigger_agents,
        }
        if extra:
            envelope.update(extra)
        (stage_dir / 'failure_envelope.json').write_text(json.dumps(envelope, indent=2, ensure_ascii=False), encoding='utf-8')

    def _persist_gate_failure(
        self,
        *,
        run_id: str,
        stage: str,
        stage_dir: Path,
        error: str,
        response_ids: list[str],
        tool_counts: dict[str, Any],
        completed_at: str,
        attempt: int,
        extra: dict[str, Any] | None = None,
    ) -> None:
        stage_dir.mkdir(parents=True, exist_ok=True)
        self._write_failure_envelope(
            run_id=run_id,
            stage=stage,
            stage_dir=stage_dir,
            failure_type='quality_gate_failure',
            error=error,
            turns=0,
            prompt_path='',
            response_ids=response_ids,
            tool_counts=tool_counts,
            started_at='',
            completed_at=completed_at,
            duration_ms=0,
            attempt=attempt,
            retrigger_agents=[stage],
            extra=extra,
        )

    @staticmethod
    def _has_blocking_unsourced_claims(citation: CitationOutput) -> bool:
        for claim in citation.unsourced_claims:
            text = str(claim).strip().lower()
            if not text:
                continue
            if text in {'none', 'n/a'}:
                continue
            return True
        return False


def normalize_final_report_payload(payload: dict[str, Any] | str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    normalized = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    warnings: list[dict[str, Any]] = []
    findings_index = normalized.get('findings_index') or []
    if isinstance(findings_index, list):
        for idx, item in enumerate(findings_index):
            if not isinstance(item, dict):
                continue
            metadata = item.get('source_metadata')
            if metadata in (None, ''):
                continue
            try:
                item['source_metadata'] = SourceMetadata.model_validate(metadata).model_dump(mode='json')
            except Exception as exc:
                item['source_metadata'] = None
                warnings.append(
                    {
                        'path': f'findings_index[{idx}].source_metadata',
                        'error': str(exc),
                        'action': 'dropped_invalid_subfield',
                    }
                )
    return normalized, warnings


def normalize_subagent_payload(payload: dict[str, Any] | str) -> dict[str, Any]:
    def _normalize_dateish(value: Any) -> str | None:
        if value in (None, ''):
            return None
        text = str(value)
        return text[:10] if len(text) >= 10 else text

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
        entry['source_date'] = _normalize_dateish(
            entry.get('source_date')
            or entry.get('published_at')
            or entry.get('filing_date')
            or entry.get('date')
        )
        entry['data_as_of'] = _normalize_dateish(
            entry.get('data_as_of')
            or entry.get('as_of')
            or entry.get('captured_at')
            or entry.get('period_end')
            or entry.get('period_as_of')
        )
        entry['period_label'] = entry.get('period_label') or entry.get('period') or entry.get('fiscal_period')
        retrieval_date = entry.get('retrieval_date') or entry.get('retrieved_at') or entry.get('retrieved_on')
        if not retrieval_date:
            retrieval_date = datetime.now(timezone.utc).date().isoformat()
        entry['retrieval_date'] = str(retrieval_date)[:10]
        source_metadata = entry.get('source_metadata') or entry.get('source_provenance')
        if source_metadata:
            metadata = dict(source_metadata)
            if not metadata.get('captured_at') and entry.get('captured_at'):
                metadata['captured_at'] = entry.get('captured_at')
            entry['source_metadata'] = metadata
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
