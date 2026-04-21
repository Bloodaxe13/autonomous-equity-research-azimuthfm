import json
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


def _minimal_brief(facet: str, ticker: str = 'ACME') -> dict:
    return {
        'facet': facet,
        'ticker': ticker,
        'objective': f'Investigate {facet} for {ticker}.',
        'required_fields': [],
        'source_guidance': 'Prefer primary company and regulator sources.',
        'task_boundaries': 'Return findings only; do not draft report prose.',
    }


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
    restart_plan = json.loads((tmp_path / 'memory' / 'run-1' / 'restart_plan.json').read_text(encoding='utf-8'))
    assert restart_plan['failed_stage'] == 'lead'
    assert restart_plan['last_good_report_path'] is None
    assert restart_plan['last_good_stage_path'] is None


def test_incomplete_subagent_persists_raw_failure_artifacts(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'sub_1', 'output': [{'type': 'function_call', 'name': 'web_search', 'call_id': 'call_1', 'arguments': '{"query": "ACME business", "limit": 1}'}]}, output_text='partial progress'),
        FakeResponse({'id': 'repair_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'repair_done', 'arguments': '{"payload": {"facet": "business_model", "ticker": "ACME", "tool_calls_used": 1, "findings": [], "not_found": ["repair"], "contradictions": [], "summary": "repaired"}}'}]}),
    ])
    runtime.subagent_max_turns = 1

    runtime.run_subagent(_minimal_brief('business_model'), run_id='run-1')

    stage_dir = tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'subagent_business_model'
    assert (stage_dir / 'raw_api_payloads.json').exists()
    assert (stage_dir / 'response_ids.json').exists()
    assert (stage_dir / 'final_text.txt').read_text(encoding='utf-8') == 'partial progress'
    assert (stage_dir / 'failure_envelope.json').exists()
    assert (stage_dir / 'repaired_output.json').exists()


def test_checkpoint_last_good_report_writes_authoritative_files(tmp_path: Path):
    from src.contracts_runtime import FinalReport
    from tests.test_live_autonomous_runtime import _valid_final_report_payload

    runtime = _runtime(tmp_path, [])
    report = FinalReport.model_validate(_valid_final_report_payload())
    runtime._checkpoint_last_good_report('run-1', report, stage='lead', attempt=0)

    run_root = tmp_path / 'memory' / 'run-1'
    last_good_report = run_root / 'last_good_report.json'
    last_good_stage = run_root / 'last_good_stage.json'
    assert last_good_report.exists()
    assert last_good_stage.exists()
    stage_meta = json.loads(last_good_stage.read_text(encoding='utf-8'))
    assert stage_meta['stage'] == 'lead'
    assert stage_meta['attempt'] == 0
    assert stage_meta['report_path'] == str(last_good_report)


def test_restart_plan_includes_last_good_paths_when_available(tmp_path: Path):
    from src.contracts_runtime import FinalReport
    from tests.test_live_autonomous_runtime import _valid_final_report_payload

    runtime = _runtime(tmp_path, [])
    report = FinalReport.model_validate(_valid_final_report_payload())
    runtime._checkpoint_last_good_report('run-1', report, stage='lead', attempt=0)

    stage_dir = tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'citation'
    runtime._write_restart_plan(
        run_id='run-1',
        failed_stage='citation',
        artifact_dir=stage_dir,
        response_ids=['resp_1'],
        restart_hint='Restart citation',
    )

    restart_plan = json.loads((tmp_path / 'memory' / 'run-1' / 'restart_plan.json').read_text(encoding='utf-8'))
    assert restart_plan['failed_stage'] == 'citation'
    assert restart_plan['last_good_report_path'].endswith('last_good_report.json')
    assert restart_plan['last_good_stage_path'].endswith('last_good_stage.json')


def test_raise_lead_gate_archives_existing_stage_dir_before_overwrite(tmp_path: Path):
    runtime = _runtime(tmp_path, [])
    stage_dir = tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead'
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / 'parsed_output.json').write_text('{"draft": true}', encoding='utf-8')
    (stage_dir / 'summary.json').write_text('{"turns": 5}', encoding='utf-8')

    with pytest.raises(PipelineStageError):
        runtime._raise_lead_gate(
            task=TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'),
            stage_dir=stage_dir,
            message='Lead aborted: test gate.',
        )

    archived = tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead_gate_failure_0'
    assert archived.exists()
    assert (archived / 'parsed_output.json').exists()
    assert json.loads((archived / 'parsed_output.json').read_text(encoding='utf-8'))['draft'] is True
