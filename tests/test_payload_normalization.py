from pathlib import Path

from src.live_autonomous_runtime import normalize_subagent_payload


def test_normalize_subagent_payload_maps_common_aliases():
    payload = {
        'facet': 'business_model',
        'ticker': 'CUV',
        'completed_at': '2026-04-20T00:00:00Z',
        'tool_calls_used': 3,
        'findings': [
            {
                'statement': 'Primary commercial product is SCENESSE.',
                'url': 'https://example.test',
                'source_tier': 'Tier 1 (company IR)',
                'title': 'Company IR',
                'confidence': 0.95,
                'notes': 'note',
            }
        ],
        'not_found': [],
        'contradictions': [],
        'summary': 'ok',
    }
    normalized = normalize_subagent_payload(payload)
    item = normalized['findings'][0]
    assert item['claim'] == 'Primary commercial product is SCENESSE.'
    assert item['data'] == 'Primary commercial product is SCENESSE.'
    assert item['source_tier'] == 1
    assert item['source_title'] == 'Company IR'
    assert item['source_url'] == 'https://example.test'
    assert item['confidence'] == 'high'
    assert item['retrieval_date']


def test_normalize_subagent_payload_accepts_json_string():
    normalized = normalize_subagent_payload('{"facet":"business_model","ticker":"CUV","tool_calls_used":1,"findings":[],"not_found":[],"contradictions":[],"summary":"ok"}')
    assert normalized['ticker'] == 'CUV'


def test_normalize_subagent_payload_preserves_as_of_semantics_and_period_labels():
    payload = {
        'facet': 'historical_financials',
        'ticker': 'CUV',
        'tool_calls_used': 2,
        'findings': [
            {
                'claim': 'Cash balance',
                'data': 233.0,
                'url': 'https://example.test/cuv/h1fy26',
                'title': 'H1 FY2026 Appendix 4D',
                'source_tier': 1,
                'source_date': '2026-02-26T00:00:00Z',
                'as_of': '2025-12-31T00:00:00Z',
                'period': 'H1 FY2026',
                'retrieval_date': '2026-04-20T13:00:00Z',
                'confidence': 'high',
            }
        ],
        'not_found': [],
        'contradictions': [],
        'summary': 'ok',
    }

    normalized = normalize_subagent_payload(payload)
    item = normalized['findings'][0]

    assert item['source_date'] == '2026-02-26'
    assert item['data_as_of'] == '2025-12-31'
    assert item['period_label'] == 'H1 FY2026'
    assert item['retrieval_date'] == '2026-04-20'


def test_normalize_subagent_payload_maps_structured_secondary_source_metadata():
    payload = {
        'facet': 'forecasts',
        'ticker': 'CUV',
        'tool_calls_used': 1,
        'findings': [
            {
                'claim': 'ROIC scaffolding indicates double-digit returns',
                'data': 11.14,
                'url': 'https://www.marketscreener.com/quote/stock/RIO-TINTO-GROUP-6492854/',
                'title': 'MarketScreener cache',
                'source_tier': 2,
                'captured_at': '2026-02-04T06:54:07Z',
                'source_metadata': {
                    'authority_class': 'trusted_structured_secondary',
                    'source_family': 'marketscreener',
                    'source_type': 'cached_aggregator_financials',
                    'origin': 'marketscreener_cache',
                    'verification_status': 'unverified',
                    'raw_payload_path': '/tmp/sample.json',
                    'quality_flags': ['aggregator'],
                    'comparability_flags': ['period_alignment_required'],
                },
            }
        ],
        'not_found': [],
        'contradictions': [],
        'summary': 'ok',
    }

    normalized = normalize_subagent_payload(payload)
    item = normalized['findings'][0]

    assert item['source_metadata']['authority_class'] == 'trusted_structured_secondary'
    assert item['source_metadata']['source_family'] == 'marketscreener'
    assert item['source_metadata']['verification_status'] == 'unverified'
    assert item['source_metadata']['captured_at'] == '2026-02-04T06:54:07Z'
