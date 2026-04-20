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
