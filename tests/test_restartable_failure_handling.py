from pathlib import Path

import pytest

from src.contracts_runtime import ReportTier, TaskInput
from src.live_autonomous_runtime import AutonomousEquityResearchRuntime, PipelineStageError
from src.memory.json_store_runtime import JsonMemoryStore
from src.tools.code_execution_runtime import CodeExecutionTool
from src.tools.runtime_web import StaticFetchAdapter, StaticSearchAdapter, WebFetchTool, WebSearchTool
from tests.test_responses_agent_runtime import FakeClient, FakeResponse


def _runtime(tmp_path: Path, scripted_responses: list[FakeResponse]) -> AutonomousEquityResearchRuntime:
    return AutonomousEquityResearchRuntime(
        repo_root=Path('/mnt/c/Users/Daniel/Azimuth Equity Research AZIMUTHFM'),
        memory_store=JsonMemoryStore(tmp_path / 'memory'),
        web_search=WebSearchTool(StaticSearchAdapter({'ACME business': [{'title': 'ACME filing', 'url': 'https://example.test/acme/filing', 'snippet': 'Annual report'}]})),
        web_fetch=WebFetchTool(StaticFetchAdapter({'https://example.test/acme/filing': {'status_code': 200, 'content_type': 'text/html', 'text': 'ACME filing body'}})),
        code_execution=CodeExecutionTool(),
        client=FakeClient(scripted_responses),
        lead_model='gpt-5.4-mini',
        subagent_model='gpt-5.4-mini',
        review_model='gpt-5.4-mini',
    )


def test_invalid_lead_output_raises_and_persists_restart_artifacts(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': '{"payload": {"ticker": "ACME", "status": "partial only"}}'}]})
    ])
    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))
    exc = exc_info.value
    assert exc.stage == 'lead'
    assert exc.run_id == 'run-1'
    assert exc.artifact_dir.exists()
    assert (exc.artifact_dir / 'raw_api_payloads.json').exists()
    assert (exc.artifact_dir / 'validation_error.json').exists()
    assert (exc.artifact_dir / 'failure_envelope.json').exists()
    assert (tmp_path / 'memory' / 'run-1' / 'restart_plan.json').exists()


def test_incomplete_subagent_persists_raw_failure_artifacts(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'sub_1', 'output': [{'type': 'function_call', 'name': 'web_search', 'call_id': 'call_1', 'arguments': '{"query": "ACME business", "limit": 1}'}]}, output_text='partial progress'),
        FakeResponse({'id': 'repair_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'repair_done', 'arguments': '{"payload": {"facet": "business_model", "ticker": "ACME", "tool_calls_used": 1, "findings": [], "not_found": ["repair"], "contradictions": [], "summary": "repaired"}}'}]}),
    ])
    runtime.subagent_max_turns = 1

    runtime.run_subagent({'facet': 'business_model', 'ticker': 'ACME'}, run_id='run-1')

    stage_dir = tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'subagent_business_model'
    assert (stage_dir / 'raw_api_payloads.json').exists()
    assert (stage_dir / 'response_ids.json').exists()
    assert (stage_dir / 'final_text.txt').read_text(encoding='utf-8') == 'partial progress'
    assert (stage_dir / 'failure_envelope.json').exists()
    assert (stage_dir / 'repaired_output.json').exists()
