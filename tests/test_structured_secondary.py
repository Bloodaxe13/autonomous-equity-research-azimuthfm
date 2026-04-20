import json
from pathlib import Path

from src.contracts_runtime import SourceMetadata
from src.structured_secondary import load_structured_secondary_metrics


def test_load_structured_secondary_metrics_from_marketscreener_cache(tmp_path: Path):
    cache_dir = tmp_path / 'marketscreener_cache'
    cache_dir.mkdir()
    (cache_dir / 'sample_url.json').write_text(
        json.dumps(
            {
                'ticker': 'ACME',
                'exchange': 'ASX',
                'url': 'https://www.marketscreener.com/quote/stock/ACME/',
                'cached_at': '2026-02-04T06:54:07Z',
            }
        ),
        encoding='utf-8',
    )
    (cache_dir / 'sample_data.json').write_text(
        json.dumps(
            {
                'ticker': 'ACME',
                'exchange': 'ASX',
                'url': 'https://www.marketscreener.com/quote/stock/ACME/',
                'roic': {'2024': 9.5, '2025': 11.14},
                'consensus_revisions': [
                    {'period': '2025', 'change_percent': -1.5},
                    {'period': '2026', 'change_percent': 4.25},
                ],
            }
        ),
        encoding='utf-8',
    )

    metrics = load_structured_secondary_metrics('ACME', cache_dir=cache_dir)

    by_name = {item.metric: item for item in metrics}
    assert set(by_name) == {'roic_pct', 'eps_revision_3m_pct'}
    assert by_name['roic_pct'].value == 11.14
    assert by_name['eps_revision_3m_pct'].value == 4.25
    assert by_name['roic_pct'].source_metadata.authority_class == 'trusted_structured_secondary'
    assert by_name['roic_pct'].source_metadata.source_family == 'marketscreener'
    assert by_name['roic_pct'].source_metadata.origin == 'marketscreener_cache'
    assert by_name['roic_pct'].source_metadata.verification_status == 'unverified'
    assert by_name['roic_pct'].source_metadata.captured_at == '2026-02-04T06:54:07Z'
    assert by_name['roic_pct'].source_metadata.raw_payload_path.endswith('sample_data.json')
    assert 'period_alignment_required' in by_name['roic_pct'].source_metadata.comparability_flags


def test_load_structured_secondary_metrics_returns_empty_for_unknown_ticker(tmp_path: Path):
    cache_dir = tmp_path / 'marketscreener_cache'
    cache_dir.mkdir()
    (cache_dir / 'sample_data.json').write_text(json.dumps({'ticker': 'OTHER', 'roic': {'2025': 3.0}}), encoding='utf-8')

    assert load_structured_secondary_metrics('ACME', cache_dir=cache_dir) == []


def test_source_metadata_accepts_common_authority_aliases():
    metadata = SourceMetadata.model_validate(
        {
            'authority_class': 'secondary',
            'source_family': 'marketscreener',
            'source_type': 'cached_aggregator_financials',
            'origin': 'marketscreener_cache',
            'verification_status': 'unverified',
        }
    )

    assert metadata.authority_class.value == 'trusted_structured_secondary'
