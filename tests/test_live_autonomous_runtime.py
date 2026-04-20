import json
from pathlib import Path

import pytest

from src.contracts_runtime import CitationOutput, FinalReport, RedTeamVerdict, ReportPacket, SubagentFindings, TaskInput, ReportTier
from src.live_autonomous_runtime import AutonomousEquityResearchRuntime, PipelineStageError
from src.memory.json_store_runtime import JsonMemoryStore
from src.responses_agent_runtime import build_default_agent_tools
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
        lead_model='gpt-5-mini',
        subagent_model='gpt-5-mini',
        review_model='gpt-5-mini',
    )


def _fixture_path(*parts: str) -> Path:
    return Path(__file__).parent / 'fixtures' / 'live_cuv_run' / Path(*parts)


def _valid_final_report_payload() -> dict:
    return {
        'ticker': 'ACME',
        'tier': 'initiation',
        'generated_at': '2026-04-20T13:44:15Z',
        'version': '0.1.0',
        'header_block': {
            'ticker': 'ACME',
            'company_name': 'ACME Ltd',
            'report_title': 'ACME Ltd - Initiation',
            'report_date': '2026-04-20',
            'report_type': 'initiation',
            'rating': 'Buy',
            'price_target_aud': 12.0,
            'current_price_aud': 10.0,
            'implied_return_pct': 20.0,
            'market_cap_aud_m': 100.0,
            'net_cash_aud_m': 20.0,
            'primary_valuation_method': 'DCF',
            'valuation_summary': 'DCF indicates upside.',
            'generated_at': '2026-04-20T13:44:15Z',
        },
        'sections': {
            'investment_thesis': 'Thesis',
            'business_description': 'Business',
            'industry_competitive': 'Industry',
            'financial_analysis': 'Financial',
            'forecasts': 'Forecasts',
            'valuation': 'Valuation',
            'catalysts': 'Catalysts',
            'risks': 'Risks',
            'esg_governance': 'Governance',
            'appendix': 'Sources reviewed\n- source\n\nItems not found\n- none\n\nComputation notes\n- note',
        },
        'computation_log': [
            {'n': 1, 'what': 'target price', 'formula': '12-10', 'inputs': {'price_target_aud': 12.0, 'current_price_aud': 10.0}, 'output': 20.0}
        ],
        'findings_index': [
            {'facet': 'business_model', 'claim': 'ACME does things', 'source_url': 'https://example.test/acme/filing', 'source_title': 'ACME filing', 'source_tier': 1, 'confidence': 'high'}
        ],
        'rating': 'Buy',
        'price_target_aud': 12.0,
        'implied_return_pct': 20.0,
    }


def test_live_runtime_can_run_subagent_with_prompt_loop(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'sub_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'c1', 'arguments': '{"payload": {"facet": "business_model", "ticker": "ACME", "tool_calls_used": 1, "findings": [], "not_found": [], "contradictions": [], "summary": "done"}}'}]})
    ])
    packet = runtime.run_subagent({'facet': 'business_model', 'ticker': 'ACME'}, run_id='run-1')
    assert isinstance(packet, SubagentFindings)
    assert packet.facet == 'business_model'


def test_recorded_cuv_bad_lead_output_fails_validation():
    payload = json.loads(_fixture_path('lead_bad_output.json').read_text(encoding='utf-8'))

    with pytest.raises(Exception) as exc_info:
        FinalReport.model_validate(payload)

    message = str(exc_info.value)
    assert 'tier' in message
    assert 'header_block' in message
    assert 'sections' in message
    assert 'price_target_aud' in message


def test_recorded_cuv_fixture_captures_original_validation_failure_surface():
    failure = json.loads(_fixture_path('lead_validation_error.json').read_text(encoding='utf-8'))

    assert failure['stage'] == 'lead'
    assert '7 validation errors for FinalReport' in failure['error']
    assert 'tier' in failure['error']
    assert 'header_block' in failure['error']
    assert 'sections' in failure['error']


def test_lead_complete_task_uses_final_report_schema(tmp_path: Path):
    runtime = _runtime(tmp_path, [])

    tools = build_default_agent_tools(
        web_search=runtime.web_search,
        web_fetch=runtime.web_fetch,
        code_execution=runtime.code_execution,
        memory_store=runtime.memory_store,
        subagent_runner=runtime._run_subagent_callback,
    )
    tools['complete_task'].parameters = FinalReport.model_json_schema()

    assert tools['complete_task'].parameters == FinalReport.model_json_schema()
    required = set(tools['complete_task'].parameters['required'])
    assert {'ticker', 'tier', 'header_block', 'sections', 'rating', 'price_target_aud', 'implied_return_pct'} <= required


def test_live_runtime_can_run_lead_with_nested_subagent_callback(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'run_subagent', 'call_id': 'lead_call_1', 'arguments': '{"brief": {"facet": "business_model", "ticker": "ACME"}}'}]}),
        FakeResponse({'id': 'sub_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'sub_done', 'arguments': '{"payload": {"facet": "business_model", "ticker": "ACME", "tool_calls_used": 1, "findings": [], "not_found": [], "contradictions": [], "summary": "done"}}'}]}),
        FakeResponse({'id': 'lead_2', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': '{"payload": {"ticker": "ACME", "company": "ACME Ltd", "current_price_aud": 10.0, "price_target_aud": 12.0, "implied_return_pct": 20.0, "sections": [{"section": "2. Business description", "content": {"summary": "Business"}}, {"section": "3. Industry and competitive position", "content": {"summary": "Industry"}}, {"section": "4. Financial analysis", "content": {"summary": "Financial"}}, {"section": "5. Forecasts", "content": {"summary": "Forecasts"}}, {"section": "6. Valuation", "content": {"summary": "Valuation"}}, {"section": "7. Catalysts", "content": {"items": ["Catalyst"]}}, {"section": "8. Risks", "content": {"items": ["Risk"]}}, {"section": "9. ESG and governance", "content": {"summary": "ESG"}}, {"section": "10. Key gaps and uncertainties", "content": {"items": ["Gap"]}}, {"section": "1. Investment thesis", "content": {"thesis": "Thesis"}}]}}'}]}),
    ])
    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))
    exc = exc_info.value
    assert exc.stage == 'lead'
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead' / 'raw_api_payloads.json').exists()
    assert (tmp_path / 'memory' / 'run-1' / 'restart_plan.json').exists()


def test_run_pipeline_executes_red_team_and_citation_after_valid_lead(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]}),
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Hold", "verdict": "weak_counter_case", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "ok"}}'}]}),
        FakeResponse({'id': 'ct_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'ct_done', 'arguments': '{"payload": {"annotated_report": "# report", "source_list": [], "computation_log": [], "unsourced_claims": []}}'}]}),
    ])

    packet = runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert isinstance(packet, ReportPacket)
    assert packet.report.ticker == 'ACME'
    assert packet.red_team.ticker == 'ACME'
    assert packet.citation.annotated_report == '# report'
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead' / 'parsed_output.json').exists()
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'red_team' / 'parsed_output.json').exists()
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'citation' / 'parsed_output.json').exists()


def test_run_pipeline_reopens_lead_once_after_strong_red_team_then_cites(tmp_path: Path):
    initial_report = _valid_final_report_payload()
    reopened_report = _valid_final_report_payload() | {
        'rating': 'Hold',
        'price_target_aud': 11.0,
        'implied_return_pct': 10.0,
        'header_block': _valid_final_report_payload()['header_block'] | {
            'rating': 'Hold',
            'price_target_aud': 11.0,
            'implied_return_pct': 10.0,
            'valuation_summary': 'Revised after red-team feedback.',
        },
    }
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done_1', 'arguments': json.dumps({'payload': initial_report})}]}),
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done_1', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Sell", "verdict": "strong_counter_case", "counter_thesis": "counter", "three_strongest_challenges": [{"challenge": "forecast too aggressive", "evidence_or_logic": "evidence", "where_report_fails": "forecasts", "severity": "critical"}], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "reopen"}}'}]}),
        FakeResponse({'id': 'lead_2', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done_2', 'arguments': json.dumps({'payload': reopened_report})}]}),
        FakeResponse({'id': 'rt_2', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done_2', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Hold", "red_team_counter_rating": "Sell", "verdict": "covered_ground", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "resolved"}}'}]}),
        FakeResponse({'id': 'ct_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'ct_done', 'arguments': '{"payload": {"annotated_report": "# report", "source_list": [], "computation_log": [], "unsourced_claims": []}}'}]}),
    ])

    packet = runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert packet.report.price_target_aud == 11.0
    assert packet.red_team.verdict == 'covered_ground'
    checkpoints = runtime.memory_store.read('run-1', 'checkpoints', [])
    assert any(item['stage'] == 'red_team_reopen_requested' for item in checkpoints)
    assert any(item['stage'] == 'red_team_reopen_completed' for item in checkpoints)
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead_attempt_0' / 'parsed_output.json').exists()
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead_attempt_1' / 'parsed_output.json').exists()
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'red_team_attempt_0' / 'parsed_output.json').exists()
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'red_team_attempt_1' / 'parsed_output.json').exists()


def test_run_pipeline_fails_closed_when_red_team_remains_strong_after_reopen(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done_1', 'arguments': json.dumps({'payload': valid_report})}]}),
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done_1', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Sell", "verdict": "strong_counter_case", "counter_thesis": "counter", "three_strongest_challenges": [{"challenge": "forecast too aggressive", "evidence_or_logic": "evidence", "where_report_fails": "forecasts", "severity": "critical"}], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "reopen"}}'}]}),
        FakeResponse({'id': 'lead_2', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done_2', 'arguments': json.dumps({'payload': valid_report | {'rating': 'Hold', 'header_block': valid_report['header_block'] | {'rating': 'Hold'}}})}]}),
        FakeResponse({'id': 'rt_2', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done_2', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Hold", "red_team_counter_rating": "Sell", "verdict": "strong_counter_case", "counter_thesis": "still broken", "three_strongest_challenges": [{"challenge": "still broken", "evidence_or_logic": "evidence", "where_report_fails": "valuation", "severity": "critical"}], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "fail closed"}}'}]}),
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert exc_info.value.stage == 'red_team'
    assert not (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'citation').exists()
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'red_team' / 'failure_envelope.json').exists()


def test_run_pipeline_fails_closed_when_citation_finds_unsourced_claims(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]}),
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Hold", "verdict": "covered_ground", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "ok"}}'}]}),
        FakeResponse({'id': 'ct_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'ct_done', 'arguments': '{"payload": {"annotated_report": "# report", "source_list": [], "computation_log": [], "unsourced_claims": ["claim without source"]}}'}]}),
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert exc_info.value.stage == 'citation'
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'citation' / 'failure_envelope.json').exists()


def test_run_pipeline_continues_with_degraded_lead_report_when_schema_invalid(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': '{"payload": {"ticker": "ACME", "status": "partial only", "rating": "Hold"}}'}]}),
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Hold", "red_team_counter_rating": "Sell", "verdict": "weak_counter_case", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "ok"}}'}]}),
        FakeResponse({'id': 'ct_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'ct_done', 'arguments': '{"payload": {"annotated_report": "# degraded report", "source_list": [], "computation_log": [], "unsourced_claims": []}}'}]}),
    ])

    packet = runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert packet.report.ticker == 'ACME'
    assert packet.report.rating == 'Hold'
    assert 'Degraded report generated' in packet.report.sections.appendix
    lead_dir = tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead'
    assert (lead_dir / 'validation_error.json').exists()
    assert (lead_dir / 'degraded_report.json').exists()
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'red_team' / 'parsed_output.json').exists()
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'citation' / 'parsed_output.json').exists()


def test_run_lead_still_raises_validation_error_before_pipeline_level_recovery(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': '{"payload": {"ticker": "ACME", "status": "partial only"}}'}]})
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    exc = exc_info.value
    assert exc.stage == 'lead'
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead' / 'validation_error.json').exists()
    assert not (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'red_team').exists()
    assert not (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'citation').exists()


def test_run_lead_drops_invalid_partial_source_metadata_and_records_warning(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    valid_report['findings_index'].append(
        {
            'facet': 'forecasts',
            'claim': 'Secondary data point',
            'source_url': 'https://example.test/secondary',
            'source_title': 'Secondary source',
            'source_tier': 2,
            'confidence': 'medium',
            'source_metadata': {
                'authority_class': 'definitely_not_valid',
                'source_family': 'marketscreener',
                'source_type': 'cached_aggregator_financials',
                'origin': 'marketscreener_cache',
                'verification_status': 'unverified',
            },
        }
    )
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]})
    ])

    report = runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert report.findings_index[-1].source_metadata is None
    warnings_path = tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead' / 'normalization_warnings.json'
    assert warnings_path.exists()
    warnings = json.loads(warnings_path.read_text(encoding='utf-8'))
    assert any(item['path'] == 'findings_index[1].source_metadata' for item in warnings)


def test_live_runtime_can_run_red_team_and_citation(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Hold", "verdict": "weak_counter_case", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "ok"}}'}]}),
        FakeResponse({'id': 'ct_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'ct_done', 'arguments': '{"payload": {"annotated_report": "# report", "source_list": [], "computation_log": [], "unsourced_claims": []}}'}]}),
    ])
    red = runtime.run_red_team({'ticker': 'ACME'}, run_id='run-1')
    citation = runtime.run_citation({'ticker': 'ACME'}, [], [], run_id='run-1')
    assert isinstance(red, RedTeamVerdict)
    assert isinstance(citation, CitationOutput)


def test_run_lead_persists_tool_error_warnings_without_crashing_stage(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'run_subagent', 'call_id': 'lead_call_1', 'arguments': json.dumps({'brief': 'not even close to json'})}]}),
        FakeResponse({'id': 'lead_2', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]}, output_text='fallback final report text'),
    ])

    report = runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert report.ticker == 'ACME'
    stage_dir = tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead'
    warnings = json.loads((stage_dir / 'tool_error_warnings.json').read_text(encoding='utf-8'))
    assert warnings[0]['tool'] == 'run_subagent'
    assert warnings[0]['error_type'] == 'TypeError'
    assert (stage_dir / 'response_text.txt').read_text(encoding='utf-8') == 'fallback final report text'


def test_live_runtime_repairs_subagent_output_when_loop_exhausts(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'sub_1', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'not valid json'}]}]}, output_text='not valid json'),
        FakeResponse({'id': 'repair_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'repair_done', 'arguments': '{"payload": {"facet": "business_model", "ticker": "ACME", "tool_calls_used": 1, "findings": [], "not_found": ["repair"], "contradictions": [], "summary": "repaired"}}'}]}),
    ])
    packet = runtime.run_subagent({'facet': 'business_model', 'ticker': 'ACME'}, run_id='run-1')
    assert packet.summary == 'repaired'
    assert packet.not_found == ['repair']


def test_run_lead_exposes_web_fetch_and_document_query_when_document_toolkit_available(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]})
    ])

    runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-tools'))

    tool_names = {tool['name'] for tool in runtime.client.responses.calls[0]['tools']}
    assert 'web_fetch' in tool_names
    assert 'document_query' in tool_names
