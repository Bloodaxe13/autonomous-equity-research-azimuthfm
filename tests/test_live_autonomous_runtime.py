import json
from pathlib import Path

import pytest

import src.live_autonomous_runtime as live_runtime_module
from src.contracts_runtime import CitationOutput, FinalReport, RedTeamVerdict, ReportPacket, SubagentFindings, TaskInput, ReportTier
from src.live_autonomous_runtime import AutonomousEquityResearchRuntime, PipelineStageError
from src.memory.json_store_runtime import JsonMemoryStore
from src.responses_agent_runtime import build_default_agent_tools
from src.tools.code_execution_runtime import CodeExecutionTool
from src.tools.runtime_web import StaticFetchAdapter, StaticSearchAdapter, WebFetchTool, WebSearchTool
from tests.test_responses_agent_runtime import FakeClient, FakeResponse


def _runtime(tmp_path: Path, scripted_responses: list[FakeResponse]) -> AutonomousEquityResearchRuntime:
    runtime = AutonomousEquityResearchRuntime(
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
    default_findings = [
        {
            'facet': 'newsflow_catalysts_corporate_actions',
            'ticker': 'ACME',
            'tool_calls_used': 1,
            'findings': [
                {
                    'claim': 'Latest half-year result',
                    'data': {'revenue': 20},
                    'source_url': 'https://example.test/h1fy26.pdf',
                    'source_tier': 1,
                    'source_title': 'First half results FY2026',
                    'source_date': '2026-02-26',
                    'data_as_of': '2025-12-31',
                    'period_label': 'H1 FY2026',
                    'retrieval_date': '2026-04-20',
                    'confidence': 'high',
                    'notes': 'Primary PDF',
                }
            ],
            'not_found': [],
            'contradictions': [],
            'summary': 'Recent result found',
        },
        {
            'facet': 'industry_market_and_competition',
            'ticker': 'ACME',
            'tool_calls_used': 1,
            'findings': [
                {
                    'claim': 'Competitor update with recent milestone',
                    'data': {'status': 'Phase 3'},
                    'source_url': 'https://example.test/competitor.pdf',
                    'source_tier': 1,
                    'source_title': 'Competitor update',
                    'source_date': '2026-03-30',
                    'data_as_of': '2026-03-30',
                    'period_label': 'Current',
                    'retrieval_date': '2026-04-20',
                    'confidence': 'high',
                    'notes': 'Recent competition context',
                }
            ],
            'not_found': [],
            'contradictions': [],
            'summary': 'Recent competitor context found',
        },
    ]
    runtime.memory_store.write('run-1', 'findings_wave_1', default_findings)
    runtime.memory_store.write('run-tools', 'findings_wave_1', default_findings)
    return runtime


def _fixture_path(*parts: str) -> Path:
    return Path(__file__).parent / 'fixtures' / 'live_cuv_run' / Path(*parts)


@pytest.fixture(autouse=True)
def _stub_deterministic_context(monkeypatch):
    monkeypatch.setattr(
        live_runtime_module,
        'build_deterministic_lead_context',
        lambda ticker: {
            'ticker': ticker,
            'has_primary_market_snapshot': True,
            'market_data_status': 'ok',
            'market_data_conflicted': False,
            'conflicts': [],
            'market_snapshot': {
                'share_price': {'value': 10.0, 'as_of': '2026-04-20', 'source': 'asx_api'},
                'market_cap_aud': {'value': 100.0, 'as_of': '2026-04-20', 'source': 'asx_api'},
                'shares_on_issue': {'value': 10000000, 'as_of': '2026-04-20', 'source': 'asx_api'},
                'fifty_two_week_high': {'value': 12.0, 'as_of': '2026-04-20', 'source': 'asx_api'},
                'fifty_two_week_low': {'value': 8.0, 'as_of': '2026-04-20', 'source': 'asx_api'},
            },
            'identity': {'company_name': 'ACME Ltd'},
        },
    )


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
        'canonical_valuation_inputs': {
            'reconciliation_status': 'resolved',
            'fcf_bridge': {
                'npat_aud_m': 30.0,
                'depreciation_and_amortization_aud_m': 2.0,
                'working_capital_outflow_aud_m': 1.0,
                'lease_cash_outflow_aud_m': 0.5,
                'capex_aud_m': 1.5,
                'equity_free_cash_flow_aud_m': 29.0,
            },
            'peer_table': [
                {
                    'peer_name': 'PeerCo',
                    'ticker': 'PEER',
                    'business_fit': 'Rare-disease peer',
                    'pe_ntm': 18.0,
                    'ev_revenue_ntm': 3.0,
                    'ev_ebitda_ntm': 11.0,
                    'notes': 'Used for cross-checking only.',
                }
            ],
            'scenario_analysis': [
                {'scenario': 'bull', 'probability_pct': 25.0, 'price_target_aud': 15.0, 'thesis': 'Bull case'},
                {'scenario': 'base', 'probability_pct': 50.0, 'price_target_aud': 12.0, 'thesis': 'Base case'},
                {'scenario': 'bear', 'probability_pct': 25.0, 'price_target_aud': 8.0, 'thesis': 'Bear case'},
            ],
            'pipeline_option_value': {
                'methodology': 'Probability-weighted option value',
                'probability_weighted_value_aud_m': 0.0,
                'included_in_price_target': False,
                'rationale': 'Excluded pending stronger evidence.',
            },
            'sensitivity_table': {
                'base_wacc_pct': 10.0,
                'base_terminal_growth_pct': 2.5,
                'rows': [
                    {'wacc_pct': 9.5, 'terminal_growth_pct': 2.0, 'price_target_aud': 13.4},
                    {'wacc_pct': 9.5, 'terminal_growth_pct': 2.5, 'price_target_aud': 13.9},
                    {'wacc_pct': 9.5, 'terminal_growth_pct': 3.0, 'price_target_aud': 14.4},
                    {'wacc_pct': 10.0, 'terminal_growth_pct': 2.0, 'price_target_aud': 11.5},
                    {'wacc_pct': 10.0, 'terminal_growth_pct': 2.5, 'price_target_aud': 12.0},
                    {'wacc_pct': 10.0, 'terminal_growth_pct': 3.0, 'price_target_aud': 12.5},
                    {'wacc_pct': 10.5, 'terminal_growth_pct': 2.0, 'price_target_aud': 9.6},
                    {'wacc_pct': 10.5, 'terminal_growth_pct': 2.5, 'price_target_aud': 10.1},
                    {'wacc_pct': 10.5, 'terminal_growth_pct': 3.0, 'price_target_aud': 10.6},
                ],
            },
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


def _minimal_brief(facet: str, ticker: str = 'ACME') -> dict:
    return {
        'facet': facet,
        'ticker': ticker,
        'objective': f'Investigate {facet} for {ticker}.',
        'required_fields': [],
        'source_guidance': 'Prefer primary company and regulator sources.',
        'task_boundaries': 'Return findings only; do not draft report prose.',
    }


def test_live_runtime_can_run_subagent_with_prompt_loop(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'sub_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'c1', 'arguments': '{"payload": {"facet": "business_model", "ticker": "ACME", "tool_calls_used": 1, "findings": [], "not_found": [], "contradictions": [], "summary": "done"}}'}]})
    ])
    packet = runtime.run_subagent(_minimal_brief('business_model'), run_id='run-1')
    assert isinstance(packet, SubagentFindings)
    assert packet.facet == 'business_model'


def test_build_subagent_prompt_path_uses_dedicated_base_plus_lane_when_available(tmp_path: Path):
    runtime = _runtime(tmp_path, [])

    prompt_path = runtime._build_subagent_prompt_path(
        brief=_minimal_brief('industry_structure_and_competition'),
        run_id='run-dedicated',
    )

    assert prompt_path.exists()
    text = prompt_path.read_text(encoding='utf-8')
    assert 'You are a research subagent working as part of a team.' in text
    assert '# Facet: industry_structure_and_competition' in text
    assert prompt_path.parent.name == '_rendered_prompts'


def test_build_subagent_prompt_path_falls_back_to_shared_prompt_for_unknown_facet(tmp_path: Path):
    runtime = _runtime(tmp_path, [])

    prompt_path = runtime._build_subagent_prompt_path(
        brief=_minimal_brief('non_standard_lane'),
        run_id='run-fallback',
    )

    assert prompt_path == runtime.prompt_dir / 'research_subagent.md'


def test_build_subagent_prompt_path_rejects_path_traversal_facet_values(tmp_path: Path):
    runtime = _runtime(tmp_path, [])

    prompt_path = runtime._build_subagent_prompt_path(
        brief={**_minimal_brief('industry_structure_and_competition'), 'facet': '../research_subagent'},
        run_id='run-fallback-unsafe',
    )

    assert prompt_path == runtime.prompt_dir / 'research_subagent.md'
    unsafe_render = tmp_path / 'memory' / 'run-fallback-unsafe' / 'research_subagent.md'
    assert not unsafe_render.exists()


def test_build_subagent_prompt_path_maps_legacy_aliases_to_dedicated_lanes(tmp_path: Path):
    runtime = _runtime(tmp_path, [])
    alias_expectations = {
        'business_model': 'business_model_and_products',
        'industry_competitive': 'industry_structure_and_competition',
        'industry_market_and_competition': 'industry_structure_and_competition',
        'historical_financials_and_capital_structure': 'historical_financials',
        'forecasts_guidance_and_consensus': 'forecasts_guidance_and_news',
        'news_catalysts': 'forecasts_guidance_and_news',
        'newsflow_catalysts_corporate_actions': 'forecasts_guidance_and_news',
        'ownership_governance_and_management': 'ownership_governance_management',
        'peers_ownership': 'peers_and_valuation_inputs',
        'peer_set_and_valuation_inputs': 'peers_and_valuation_inputs',
    }

    for alias, canonical in alias_expectations.items():
        prompt_path = runtime._build_subagent_prompt_path(
            brief=_minimal_brief(alias),
            run_id=f'run-{alias}',
        )
        assert prompt_path.exists()
        assert prompt_path.name == f'{canonical}.md'
        text = prompt_path.read_text(encoding='utf-8')
        assert f'# Facet: {canonical}' in text


def test_run_subagent_persists_rendered_dedicated_prompt_path_in_artifacts(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'sub_2', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'c1', 'arguments': '{"payload": {"facet": "industry_structure_and_competition", "ticker": "ACME", "tool_calls_used": 1, "findings": [], "not_found": [], "contradictions": [], "summary": "done"}}'}]})
    ])

    runtime.run_subagent(_minimal_brief('industry_structure_and_competition'), run_id='run-dedicated-artifact')

    summary_path = tmp_path / 'memory' / 'run-dedicated-artifact' / 'agent_artifacts' / 'subagent_industry_structure_and_competition' / 'summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    assert summary['prompt_path'].endswith('_rendered_prompts/industry_structure_and_competition.md')
    rendered_prompt = Path(summary['prompt_path'])
    assert rendered_prompt.exists()
    rendered_text = rendered_prompt.read_text(encoding='utf-8')
    assert '# Facet: industry_structure_and_competition' in rendered_text


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
    assert {'ticker', 'tier', 'header_block', 'sections', 'canonical_valuation_inputs', 'rating', 'price_target_aud', 'implied_return_pct'} <= required


def test_run_subagent_tool_uses_strict_subagent_brief_schema(tmp_path: Path):
    runtime = _runtime(tmp_path, [])
    tools = build_default_agent_tools(
        web_search=runtime.web_search,
        web_fetch=runtime.web_fetch,
        code_execution=runtime.code_execution,
        memory_store=runtime.memory_store,
        subagent_runner=runtime._run_subagent_callback,
    )

    params = tools['run_subagent'].parameters
    assert params['required'] == ['brief']
    assert params['additionalProperties'] is False
    brief_schema = params['properties']['brief']
    assert set(['facet', 'ticker', 'objective', 'required_fields', 'source_guidance', 'task_boundaries']) <= set(brief_schema['required'])


def test_final_report_requires_canonical_valuation_inputs():
    payload = _valid_final_report_payload()
    payload.pop('canonical_valuation_inputs')

    with pytest.raises(Exception) as exc_info:
        FinalReport.model_validate(payload)

    assert 'canonical_valuation_inputs' in str(exc_info.value)


def test_lead_quality_gate_requires_resolved_canonical_valuation_inputs(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': _valid_final_report_payload() | {'canonical_valuation_inputs': _valid_final_report_payload()['canonical_valuation_inputs'] | {'reconciliation_status': 'unresolved'}}})}]}),
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert 'canonical valuation inputs' in str(exc_info.value).lower()


def test_liquidity_caveat_notes_do_not_abort_if_not_a_contradiction(tmp_path: Path):
    runtime = _runtime(tmp_path, [])
    findings = [
        SubagentFindings.model_validate({
            'facet': 'historical_financials',
            'ticker': 'ACME',
            'completed_at': '2026-04-21T00:00:00Z',
            'tool_calls_used': 1,
            'findings': [
                {
                    'claim': 'Company held cash and term deposits at period end.',
                    'data': {'cash': 10, 'term_deposits': 20},
                    'source_url': 'https://example.com',
                    'source_tier': 1,
                    'source_title': 'Results',
                    'source_date': '2026-02-26',
                    'data_as_of': '2025-12-31',
                    'period_label': 'H1 FY2026',
                    'retrieval_date': '2026-04-21',
                    'confidence': 'high',
                    'notes': 'Cash excluding term deposits is lower than total liquid resources; reconcile before compressing net cash.',
                    'source_metadata': {'authority_class': 'primary_truth', 'source_family': 'company', 'source_type': 'filing', 'origin': 'direct', 'verification_status': 'verified_primary_match', 'captured_at': None, 'raw_payload_path': None, 'quality_flags': [], 'comparability_flags': []},
                }
            ],
            'not_found': [],
            'contradictions': [],
            'summary': 'Liquidity caveat noted but no unresolved contradiction.'
        })
    ]

    runtime._require_no_unresolved_liquidity_conflict(
        task=TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'),
        stage_dir=tmp_path,
        findings=findings,
    )


def test_liquidity_contradiction_still_aborts(tmp_path: Path):
    runtime = _runtime(tmp_path, [])
    findings = [
        SubagentFindings.model_validate({
            'facet': 'historical_financials',
            'ticker': 'ACME',
            'completed_at': '2026-04-21T00:00:00Z',
            'tool_calls_used': 1,
            'findings': [],
            'not_found': [],
            'contradictions': [
                {
                    'topic': 'Net cash / term deposits conflict',
                    'source_a': 'https://example.com/a',
                    'source_a_claim': 'Cash excludes term deposits.',
                    'source_b': 'https://example.com/b',
                    'source_b_claim': 'Cash plus term deposits presented as liquid resources.',
                    'notes': 'Unresolved liquidity contradiction.'
                }
            ],
            'summary': 'Contradiction remains unresolved.'
        })
    ]

    with pytest.raises(PipelineStageError) as exc_info:
        runtime._require_no_unresolved_liquidity_conflict(
            task=TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'),
            stage_dir=tmp_path,
            findings=findings,
        )

    assert 'liquidity conflict' in str(exc_info.value).lower()


def test_peer_mismatch_contradictions_do_not_trip_liquidity_gate(tmp_path: Path):
    runtime = _runtime(tmp_path, [])
    findings = [
        SubagentFindings.model_validate({
            'facet': 'peers_and_valuation_inputs',
            'ticker': 'ACME',
            'completed_at': '2026-04-21T00:00:00Z',
            'tool_calls_used': 1,
            'findings': [],
            'not_found': [],
            'contradictions': [
                {
                    'topic': 'Peer-set purity versus breadth',
                    'source_a': 'https://example.com/a',
                    'source_a_claim': 'Peer A has a different business model.',
                    'source_b': 'https://example.com/b',
                    'source_b_claim': 'Target has a net-cash balance sheet.',
                    'notes': 'Business-model mismatch for comparability haircut, not a factual contradiction.'
                }
            ],
            'summary': 'Peer mismatch only.'
        })
    ]

    runtime._require_no_unresolved_liquidity_conflict(
        task=TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'),
        stage_dir=tmp_path,
        findings=findings,
    )


def test_governance_context_mismatch_does_not_trip_role_conflict_gate(tmp_path: Path):
    runtime = _runtime(tmp_path, [])
    findings = [
        SubagentFindings.model_validate({
            'facet': 'open_questions_gap_fill',
            'ticker': 'ACME',
            'completed_at': '2026-04-21T00:00:00Z',
            'tool_calls_used': 1,
            'findings': [],
            'not_found': [],
            'contradictions': [
                {
                    'topic': 'North American centres count vs later chair letter wording',
                    'source_a': 'https://example.com/a',
                    'source_a_claim': 'Operational disclosure says 104 centres.',
                    'source_b': 'https://example.com/b',
                    'source_b_claim': 'Chair letter says over 120 centres.',
                    'notes': 'Date-specific operating disclosure is more reliable; this is not a governance role contradiction.'
                }
            ],
            'summary': 'Operational context mismatch only.'
        })
    ]

    runtime._require_no_governance_conflict(
        task=TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'),
        stage_dir=tmp_path,
        findings=findings,
    )


def test_unresolved_governance_role_conflict_still_aborts(tmp_path: Path):
    runtime = _runtime(tmp_path, [])
    findings = [
        SubagentFindings.model_validate({
            'facet': 'ownership_governance_management',
            'ticker': 'ACME',
            'completed_at': '2026-04-21T00:00:00Z',
            'tool_calls_used': 1,
            'findings': [],
            'not_found': [],
            'contradictions': [
                {
                    'topic': 'CEO / Acting CEO contradiction',
                    'source_a': 'https://example.com/a',
                    'source_a_claim': 'Company page lists CEO A.',
                    'source_b': 'https://example.com/b',
                    'source_b_claim': 'Latest announcement lists Acting CEO B.',
                    'notes': 'Unresolved governance mismatch on current role.'
                }
            ],
            'summary': 'Current role conflict unresolved.'
        })
    ]

    with pytest.raises(PipelineStageError) as exc_info:
        runtime._require_no_governance_conflict(
            task=TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'),
            stage_dir=tmp_path,
            findings=findings,
        )

    assert 'governance/current-role conflict' in str(exc_info.value).lower()


def test_lead_prompt_mentions_canonical_valuation_inputs_block():
    prompt_path = Path('/mnt/c/Users/Daniel/Azimuth Equity Research AZIMUTHFM/prompts/lead_analyst.md')
    text = prompt_path.read_text(encoding='utf-8')

    assert 'canonical_valuation_inputs' in text
    assert 'reconciliation_status' in text
    assert 'sensitivity' in text.lower()
    assert 'business_model_and_products' in text
    assert 'industry_structure_and_competition' in text
    assert 'peers_and_valuation_inputs' in text


def test_citation_prompt_includes_report_findings_and_computation_context():
    prompt_path = Path('/mnt/c/Users/Daniel/Azimuth Equity Research AZIMUTHFM/prompts/citation.md')
    text = prompt_path.read_text(encoding='utf-8')

    assert '{{.Report}}' in text
    assert '{{.FindingsIndex}}' in text
    assert '{{.ComputationLog}}' in text
    assert 'unsourced_claims' in text


def test_subagent_repair_prompt_mentions_time_regime_and_source_metadata():
    prompt_path = Path('/mnt/c/Users/Daniel/Azimuth Equity Research AZIMUTHFM/prompts/subagent_repair.md')
    text = prompt_path.read_text(encoding='utf-8')

    assert 'Preserve time regime exactly' in text
    assert 'source_metadata' in text
    assert 'period_label' in text


def test_dedicated_subagent_base_mentions_source_metadata():
    prompt_path = Path('/mnt/c/Users/Daniel/Azimuth Equity Research AZIMUTHFM/prompts/dedicated_subagents/_base.md')
    text = prompt_path.read_text(encoding='utf-8')

    assert 'source_metadata' in text
    assert 'verification_status' in text


def test_live_runtime_can_run_lead_with_nested_subagent_callback(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'run_subagent', 'call_id': 'lead_call_1', 'arguments': json.dumps({'brief': _minimal_brief('business_model')})}]}),
        FakeResponse({'id': 'sub_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'sub_done', 'arguments': '{"payload": {"facet": "business_model", "ticker": "ACME", "tool_calls_used": 1, "findings": [], "not_found": [], "contradictions": [], "summary": "done"}}'}]}),
        FakeResponse({'id': 'lead_2', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': '{"payload": {"ticker": "ACME", "company": "ACME Ltd", "current_price_aud": 10.0, "price_target_aud": 12.0, "implied_return_pct": 20.0, "sections": [{"section": "2. Business description", "content": {"summary": "Business"}}, {"section": "3. Industry and competitive position", "content": {"summary": "Industry"}}, {"section": "4. Financial analysis", "content": {"summary": "Financial"}}, {"section": "5. Forecasts", "content": {"summary": "Forecasts"}}, {"section": "6. Valuation", "content": {"summary": "Valuation"}}, {"section": "7. Catalysts", "content": {"items": ["Catalyst"]}}, {"section": "8. Risks", "content": {"items": ["Risk"]}}, {"section": "9. ESG and governance", "content": {"summary": "ESG"}}, {"section": "10. Key gaps and uncertainties", "content": {"items": ["Gap"]}}, {"section": "1. Investment thesis", "content": {"thesis": "Thesis"}}]}}'}]}),
    ])
    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))
    exc = exc_info.value
    assert exc.stage == 'lead'
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead' / 'raw_api_payloads.json').exists()
    assert (tmp_path / 'memory' / 'run-1' / 'restart_plan.json').exists()
    findings = runtime.memory_store.read('run-1', 'findings_wave_1', [])
    briefs = runtime.memory_store.read('run-1', 'subagent_briefs', [])
    assert any(item['facet'] == 'business_model' for item in findings)
    assert any(item['facet'] == 'business_model' for item in briefs)


def test_run_pipeline_executes_red_team_and_citation_after_valid_lead(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]}),
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'web_search', 'call_id': 'rt_search', 'arguments': '{"query": "ACME latest results"}'}, {'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Hold", "verdict": "weak_counter_case", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "ok"}}'}]}),
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
            'valuation_summary': 'Revised after red-team feedback with broadly fair risk/reward framing.',
        },
        'sections': _valid_final_report_payload()['sections'] | {
            'investment_thesis': 'Hold with broadly fair risk/reward after reopen.',
            'valuation': 'Sensitivity shows a knife-edge setup and broadly fair risk/reward near spot.',
        },
    }
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done_1', 'arguments': json.dumps({'payload': initial_report})}]}),
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'web_search', 'call_id': 'rt_search_1', 'arguments': '{"query": "ACME latest results"}'}, {'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done_1', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Sell", "verdict": "strong_counter_case", "counter_thesis": "counter", "three_strongest_challenges": [{"challenge": "forecast too aggressive", "evidence_or_logic": "evidence", "where_report_fails": "forecasts", "severity": "critical"}], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "reopen"}}'}]}),
        FakeResponse({'id': 'lead_2', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done_2', 'arguments': json.dumps({'payload': reopened_report})}]}),
        FakeResponse({'id': 'rt_2', 'output': [{'type': 'function_call', 'name': 'web_search', 'call_id': 'rt_search_2', 'arguments': '{"query": "ACME governance update"}'}, {'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done_2', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Hold", "red_team_counter_rating": "Sell", "verdict": "covered_ground", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "resolved"}}'}]}),
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
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'web_search', 'call_id': 'rt_search_1', 'arguments': '{"query": "ACME latest results"}'}, {'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done_1', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Sell", "verdict": "strong_counter_case", "counter_thesis": "counter", "three_strongest_challenges": [{"challenge": "forecast too aggressive", "evidence_or_logic": "evidence", "where_report_fails": "forecasts", "severity": "critical"}], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "reopen"}}'}]}),
        FakeResponse({'id': 'lead_2', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done_2', 'arguments': json.dumps({'payload': valid_report | {'rating': 'Hold', 'header_block': valid_report['header_block'] | {'rating': 'Hold'}}})}]}),
        FakeResponse({'id': 'rt_2', 'output': [{'type': 'function_call', 'name': 'web_search', 'call_id': 'rt_search_2', 'arguments': '{"query": "ACME valuation issue"}'}, {'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done_2', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Hold", "red_team_counter_rating": "Sell", "verdict": "strong_counter_case", "counter_thesis": "still broken", "three_strongest_challenges": [{"challenge": "still broken", "evidence_or_logic": "evidence", "where_report_fails": "valuation", "severity": "critical"}], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "fail closed"}}'}]}),
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
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'web_search', 'call_id': 'rt_search', 'arguments': '{"query": "ACME latest results"}'}, {'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Hold", "verdict": "covered_ground", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "ok"}}'}]}),
        FakeResponse({'id': 'ct_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'ct_done', 'arguments': '{"payload": {"annotated_report": "# report", "source_list": [], "computation_log": [], "unsourced_claims": ["claim without source"]}}'}]}),
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert exc_info.value.stage == 'citation'
    assert (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'citation' / 'failure_envelope.json').exists()


def test_run_pipeline_fails_closed_when_red_team_schema_is_invalid(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]}),
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'web_search', 'call_id': 'rt_search', 'arguments': '{"query": "ACME latest results"}'}, {'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "verdict": "covered_ground"}}'}]}),
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert exc_info.value.stage == 'red_team'
    assert 'strict redteamverdict validation' in exc_info.value.message.lower()


def test_run_pipeline_fails_closed_when_citation_schema_is_invalid(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]}),
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'web_search', 'call_id': 'rt_search', 'arguments': '{"query": "ACME latest results"}'}, {'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Hold", "verdict": "covered_ground", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "ok"}}'}]}),
        FakeResponse({'id': 'ct_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'ct_done', 'arguments': '{"payload": {"source_list": []}}'}]}),
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert exc_info.value.stage == 'citation'
    assert 'strict citationoutput validation' in exc_info.value.message.lower()


def test_run_pipeline_fails_closed_when_lead_schema_is_invalid(tmp_path: Path):
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': '{"payload": {"ticker": "ACME", "status": "partial only", "rating": "Hold"}}'}]}),
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert exc_info.value.stage == 'lead'
    lead_dir = tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead'
    assert (lead_dir / 'validation_error.json').exists()
    assert not (lead_dir / 'degraded_report.json').exists()
    assert not (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'red_team').exists()
    assert not (tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'citation').exists()


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
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'web_search', 'call_id': 'rt_search', 'arguments': '{"query": "ACME latest results"}'}, {'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Hold", "verdict": "weak_counter_case", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "ok"}}'}]}),
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
    packet = runtime.run_subagent(_minimal_brief('business_model'), run_id='run-1')
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


def test_run_lead_injects_deterministic_context_into_prompt_and_memory(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]})
    ])

    runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    stored = runtime.memory_store.read('run-1', 'deterministic_lead_context', {})
    assert stored['has_primary_market_snapshot'] is True
    raw_payloads = json.loads((tmp_path / 'memory' / 'run-1' / 'agent_artifacts' / 'lead' / 'raw_api_payloads.json').read_text(encoding='utf-8'))
    request = raw_payloads[0]['request']
    assert 'deterministic_lead_context' in json.dumps(request['input'])
    assert 'DeterministicLeadContext' in request['instructions']


def test_run_lead_fails_closed_when_deterministic_market_data_is_unavailable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        live_runtime_module,
        'build_deterministic_lead_context',
        lambda ticker: {
            'ticker': ticker,
            'has_primary_market_snapshot': False,
            'market_data_status': 'unavailable',
            'market_data_conflicted': False,
            'conflicts': [],
            'market_snapshot': {'share_price': None, 'market_cap_aud': None, 'shares_on_issue': None},
            'identity': {'company_name': 'ACME Ltd'},
        },
    )
    runtime = _runtime(tmp_path, [])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert exc_info.value.stage == 'lead'
    assert 'deterministic market data' in exc_info.value.message.lower()


def test_run_pipeline_fails_closed_when_deterministic_market_data_is_unavailable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        live_runtime_module,
        'build_deterministic_lead_context',
        lambda ticker: {
            'ticker': ticker,
            'has_primary_market_snapshot': False,
            'market_data_status': 'unavailable',
            'market_data_conflicted': False,
            'conflicts': [],
            'market_snapshot': {'share_price': None, 'market_cap_aud': None, 'shares_on_issue': None},
            'identity': {'company_name': 'ACME Ltd'},
        },
    )
    runtime = _runtime(tmp_path, [])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert exc_info.value.stage == 'lead'
    assert 'deterministic market data' in exc_info.value.message.lower()


def test_run_lead_fails_closed_when_market_data_conflicts(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        live_runtime_module,
        'build_deterministic_lead_context',
        lambda ticker: {
            'ticker': ticker,
            'has_primary_market_snapshot': True,
            'market_data_status': 'conflicted',
            'market_data_conflicted': True,
            'conflicts': ['ASX vs FMP price mismatch'],
            'market_snapshot': {'share_price': {'value': 10.0}, 'market_cap_aud': {'value': 100.0}, 'shares_on_issue': {'value': 10000000}},
            'identity': {'company_name': 'ACME Ltd'},
        },
    )
    runtime = _runtime(tmp_path, [])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert exc_info.value.stage == 'lead'
    assert 'conflict' in exc_info.value.message.lower()


def test_run_lead_fails_when_recent_result_is_missing_from_subagent_findings(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]})
    ])
    runtime.memory_store.write('run-1', 'findings_wave_1', [
        {
            'facet': 'newsflow_catalysts_corporate_actions',
            'ticker': 'ACME',
            'tool_calls_used': 1,
            'findings': [
                {
                    'claim': 'Old half-year result',
                    'data': {'revenue': 10},
                    'source_url': 'https://example.test/old-result.pdf',
                    'source_tier': 1,
                    'source_title': 'First half results FY2025',
                    'source_date': '2025-02-27',
                    'data_as_of': '2024-12-31',
                    'period_label': 'H1 FY2025',
                    'retrieval_date': '2026-04-20',
                    'confidence': 'high',
                    'notes': 'Primary PDF',
                }
            ],
            'not_found': [],
            'contradictions': [],
            'summary': 'Only old result found',
        }
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert 'latest result' in exc_info.value.message.lower()


def test_run_lead_fails_when_material_caveat_is_unresolved(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]})
    ])
    runtime.memory_store.write('run-1', 'findings_wave_1', [
        {
            'facet': 'newsflow_catalysts_corporate_actions',
            'ticker': 'ACME',
            'tool_calls_used': 1,
            'findings': [
                {
                    'claim': 'Latest half-year result',
                    'data': {'revenue': 20},
                    'source_url': 'https://example.test/h1fy26.pdf',
                    'source_tier': 1,
                    'source_title': 'First half results FY2026',
                    'source_date': '2026-02-26',
                    'data_as_of': '2025-12-31',
                    'period_label': 'H1 FY2026',
                    'retrieval_date': '2026-04-20',
                    'confidence': 'high',
                    'notes': 'Primary PDF',
                }
            ],
            'not_found': [],
            'contradictions': [],
            'summary': 'Recent result found',
        },
        {
            'facet': 'historical_financials_and_capital_structure',
            'ticker': 'ACME',
            'tool_calls_used': 1,
            'findings': [
                {
                    'claim': 'FY2025 cash and lease liabilities',
                    'data': {'cash_aud_m': 28.0, 'lease_liabilities_aud_m': 0.5},
                    'source_url': 'https://example.test/ar.pdf',
                    'source_tier': 1,
                    'source_title': 'Annual report',
                    'source_date': '2025-08-28',
                    'data_as_of': '2025-06-30',
                    'period_label': 'FY2025',
                    'retrieval_date': '2026-04-20',
                    'confidence': 'high',
                    'notes': 'Annual report also highlighted cash plus term deposits above cash balance.',
                }
            ],
            'not_found': [],
            'contradictions': [],
            'summary': 'Caveated cash line',
        }
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert 'caveat' in exc_info.value.message.lower() or 'term deposit' in exc_info.value.message.lower()


def test_run_pipeline_fails_when_red_team_does_not_reground(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]}),
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Hold", "verdict": "covered_ground", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "ok"}}'}]}),
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert exc_info.value.stage == 'red_team'
    assert 'ground' in exc_info.value.message.lower()


def test_run_pipeline_fails_when_red_team_only_uses_code_execution(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]}),
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'code_execution', 'call_id': 'rt_calc', 'arguments': '{"python_code": "print(1+1)"}'}, {'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Hold", "verdict": "covered_ground", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "ok"}}'}]}),
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert exc_info.value.stage == 'red_team'
    assert 'retrieval' in exc_info.value.message.lower()


def test_run_pipeline_passes_when_red_team_uses_grounding_tools(tmp_path: Path):
    valid_report = _valid_final_report_payload()
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]}),
        FakeResponse({'id': 'rt_1', 'output': [{'type': 'function_call', 'name': 'web_search', 'call_id': 'rt_search', 'arguments': '{"query": "ACME latest results"}'}, {'type': 'function_call', 'name': 'complete_task', 'call_id': 'rt_done', 'arguments': '{"payload": {"ticker": "ACME", "report_rating": "Buy", "red_team_counter_rating": "Hold", "verdict": "covered_ground", "counter_thesis": "counter", "three_strongest_challenges": [], "missed_risks": [], "disagreements_with_calculations": [], "verdict_reasoning": "ok"}}'}]}),
        FakeResponse({'id': 'ct_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'ct_done', 'arguments': '{"payload": {"annotated_report": "# report", "source_list": [], "computation_log": [], "unsourced_claims": []}}'}]}),
    ])

    packet = runtime.run(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))
    assert packet.red_team.verdict == 'covered_ground'


def test_run_lead_fails_when_near_spot_rating_lacks_knife_edge_language(tmp_path: Path):
    valid_report = _valid_final_report_payload() | {
        'rating': 'Hold',
        'price_target_aud': 10.5,
        'implied_return_pct': 5.0,
        'header_block': _valid_final_report_payload()['header_block'] | {
            'rating': 'Hold',
            'price_target_aud': 10.5,
            'implied_return_pct': 5.0,
        },
        'sections': _valid_final_report_payload()['sections'] | {
            'investment_thesis': 'We initiate with Hold. Good company.',
            'valuation': 'DCF says value is around today price.',
        },
    }
    runtime = _runtime(tmp_path, [
        FakeResponse({'id': 'lead_1', 'output': [{'type': 'function_call', 'name': 'complete_task', 'call_id': 'lead_done', 'arguments': json.dumps({'payload': valid_report})}]})
    ])

    with pytest.raises(PipelineStageError) as exc_info:
        runtime.run_lead(TaskInput(ticker='ACME', tier=ReportTier.INITIATION, run_id='run-1'))

    assert 'knife-edge' in exc_info.value.message.lower() or 'risk/reward' in exc_info.value.message.lower()
