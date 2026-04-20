from pathlib import Path

from src.contracts_runtime import CitationOutput, RedTeamVerdict, SubagentFindings, TaskInput, ReportTier
from src.live_autonomous_runtime import AutonomousEquityResearchRuntime
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
        lead_model='gpt-5-mini',
        subagent_model='gpt-5-mini',
        review_model='gpt-5-mini',
    )


def test_live_runtime_can_run_subagent_with_prompt_loop(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'sub_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'c1', 'arguments': '{"payload": {"facet": "business_model", "ticker": "ACME", "tool_calls_used": 1, "findings": [], "not_found": [], "contradictions": [], "summary": "done"}}'}]})
    ])
    packet = runtime.run_subagent({'facet': 'business_model', 'ticker': 'ACME'}, run_id='run-1')
    assert isinstance(packet, SubagentFindings)
    assert packet.facet == 'business_model'


def test_live_runtime_can_run_lead_with_nested_subagent_callback(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'run_subagent', 'call_id': 'lead_call_1', 'arguments': '{"brief": {"facet": "business_model", "ticker": "ACME"}}'}]}),
        FakeResponse({'id': 'sub_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'sub_done', 'arguments': '{"payload": {"facet": "business_model", "ticker": "ACME", "tool_calls_used": 1, "findings": [], "not_found": [], "contradictions": [], "summary": "done"}}'}]}),
        FakeResponse({'id': 'lead_2', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': '{"payload": {"ticker": "ACME", "status": "done"}}'}]}),
    ])
    output = runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))
    assert output == {'ticker': 'ACME', 'status': 'done'}


def test_live_runtime_can_run_red_team_and_citation(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Hold", "verdict": "weak_counter_case", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "ok"}}'}]}),
        FakeResponse({'id': 'ct_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'ct_done', 'arguments': '{"payload": {"annotated_report": "# report", "source_list": [], "computation_log": [], "unsourced_claims": []}}'}]}),
    ])
    red = runtime.run_red_team({'ticker': 'ACME'}, run_id='run-1')
    citation = runtime.run_citation({'ticker': 'ACME'}, [], [], run_id='run-1')
    assert isinstance(red, RedTeamVerdict)
    assert isinstance(citation, CitationOutput)
