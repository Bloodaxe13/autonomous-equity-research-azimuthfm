from pathlib import Path

from src.deterministic_lead_context import build_deterministic_lead_context


def test_build_deterministic_lead_context_returns_unavailable_without_sources(tmp_path: Path):
    context = build_deterministic_lead_context(
        'ACME',
        asx_fetcher=lambda ticker: None,
        fmp_fetcher=lambda ticker: None,
        yahoo_fetcher=lambda ticker: None,
    )

    assert context['ticker'] == 'ACME'
    assert context['has_primary_market_snapshot'] is False
    assert context['market_data_status'] == 'unavailable'
    assert context['market_snapshot']['share_price'] is None
    assert context['identity']['company_name'] is None
    assert context['consensus_snapshot']['analyst_target_price_avg'] is None
    assert context['ev_bridge'] is None


def test_build_deterministic_lead_context_prefers_asx_primary_snapshot_and_fmp_identity():
    asx_payload = {
        'header': {
            'displayName': 'ACME Ltd',
            'priceLast': 10.5,
            'marketCap': 500_000_000,
            'sector': 'Industrials',
            'industryGroup': 'Engineering Services',
            'dateListed': '2015-06-01',
            'volume': 123456,
        },
        'key_statistics': {
            'numOfShares': 47619047,
            'priceFiftyTwoWeekHigh': 13.2,
            'priceFiftyTwoWeekLow': 8.4,
            'earningsPerShare': 0.42,
            'priceEarningsRatio': 25.0,
        },
    }
    fmp_payload = {
        'name': 'ACME Ltd',
        'symbol': 'ACME.AX',
        'exchange': 'ASX',
        'exchange_full_name': 'Australian Securities Exchange',
        'currency': 'AUD',
        'sector': 'Industrials',
        'industry': 'Engineering Services',
        'country': 'AU',
        'description': 'Builds things.',
        'ceo': 'Jane Doe',
        'website': 'https://acme.example',
    }
    yahoo_payload = {
        'target_mean_price': 12.4,
        'target_high_price': 14.0,
        'target_low_price': 10.8,
        'analyst_count': 7,
        'recommendation_key': 'buy',
        'dividend_rate': 0.12,
        'dividend_yield': 0.015,
        'balance_sheet': {
            'Total Debt': 80_000_000,
            'Cash And Cash Equivalents': 20_000_000,
        },
        'market_cap_diluted': 510_000_000,
        'shares_outstanding_diluted': 50000000,
        'fifty_two_week_high': 13.1,
        'fifty_two_week_low': 8.5,
    }

    context = build_deterministic_lead_context(
        'ACME',
        asx_fetcher=lambda ticker: asx_payload,
        fmp_fetcher=lambda ticker: fmp_payload,
        yahoo_fetcher=lambda ticker: yahoo_payload,
    )

    assert context['has_primary_market_snapshot'] is True
    assert context['market_data_status'] == 'ok'
    assert context['market_snapshot']['share_price']['value'] == 10.5
    assert context['market_snapshot']['market_cap_aud']['value'] == 500.0
    assert context['market_snapshot']['shares_on_issue']['value'] == 47_619_047
    assert context['market_snapshot']['fifty_two_week_high']['value'] == 13.2
    assert context['market_snapshot']['fifty_two_week_low']['value'] == 8.4
    assert context['identity']['company_name'] == 'ACME Ltd'
    assert context['identity']['ceo'] == 'Jane Doe'
    assert context['consensus_snapshot']['analyst_target_price_avg']['value'] == 12.4
    assert context['consensus_snapshot']['analyst_count']['value'] == 7
    assert context['ev_bridge']['enterprise_value_aud_m']['value'] == 560.0
    assert context['ev_bridge']['inputs']['net_debt_aud_m']['value'] == 60.0


def test_build_deterministic_lead_context_flags_conflict_when_sources_disagree_materially():
    asx_payload = {
        'header': {'displayName': 'ACME Ltd', 'priceLast': 10.0, 'marketCap': 400_000_000},
        'key_statistics': {'numOfShares': 40_000_000},
    }
    fmp_payload = {
        'name': 'ACME Ltd',
        'symbol': 'ACME.AX',
        'exchange': 'ASX',
        'exchange_full_name': 'Australian Securities Exchange',
        'currency': 'AUD',
        'price': 13.5,
        'market_cap': 540_000_000,
    }

    context = build_deterministic_lead_context(
        'ACME',
        asx_fetcher=lambda ticker: asx_payload,
        fmp_fetcher=lambda ticker: fmp_payload,
        yahoo_fetcher=lambda ticker: None,
    )

    assert context['market_data_status'] == 'conflicted'
    assert context['market_data_conflicted'] is True
    assert any('price' in item.lower() or 'market cap' in item.lower() for item in context['conflicts'])
