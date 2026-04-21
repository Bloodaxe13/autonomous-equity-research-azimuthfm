from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable


ASX_BASE_URL = 'https://asx.api.markitdigital.com/asx-research/1.0/companies'
FMP_BASE_URL = 'https://financialmodelingprep.com/stable'


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def _http_get_json(url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any] | list[Any] | None:
    req = urllib.request.Request(url, headers=headers or {'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None


def _fetch_asx_market_snapshot(ticker: str) -> dict[str, Any] | None:
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json',
    }
    header = _http_get_json(f'{ASX_BASE_URL}/{ticker}/header', headers=headers)
    key_stats = _http_get_json(f'{ASX_BASE_URL}/{ticker}/key-statistics', headers=headers)
    return {
        'header': (header or {}).get('data', {}) if isinstance(header, dict) else {},
        'key_statistics': (key_stats or {}).get('data', {}) if isinstance(key_stats, dict) else {},
    }


def _fetch_fmp_profile(ticker: str) -> dict[str, Any] | None:
    api_key = (os.getenv('FMP_API_KEY') or '').strip()
    if not api_key:
        return None
    query = urllib.parse.urlencode({'query': ticker, 'exchange': 'ASX', 'limit': 1, 'apikey': api_key})
    search = _http_get_json(f'{FMP_BASE_URL}/search-symbol?{query}')
    if not isinstance(search, list) or not search:
        return None
    symbol = search[0].get('symbol') or ticker
    profile_query = urllib.parse.urlencode({'symbol': symbol, 'apikey': api_key})
    profile = _http_get_json(f'{FMP_BASE_URL}/profile?{profile_query}')
    if isinstance(profile, list) and profile:
        profile = profile[0]
    if not isinstance(profile, dict):
        return None
    return {
        'name': profile.get('companyName') or search[0].get('name'),
        'symbol': symbol,
        'exchange': profile.get('exchange') or search[0].get('exchange'),
        'exchange_full_name': profile.get('exchangeShortName') or search[0].get('exchangeFullName'),
        'currency': profile.get('currency') or search[0].get('currency'),
        'sector': profile.get('sector'),
        'industry': profile.get('industry'),
        'country': profile.get('country'),
        'description': profile.get('description'),
        'market_cap': profile.get('mktCap') or profile.get('marketCap'),
        'price': profile.get('price'),
        'ceo': profile.get('ceo'),
        'website': profile.get('website'),
    }


def _fetch_yahoo_secondary_context(ticker: str) -> dict[str, Any] | None:
    try:
        import yfinance as yf
    except Exception:
        return None
    symbol = f'{ticker}.AX'
    try:
        obj = yf.Ticker(symbol)
        info = obj.info or {}
    except Exception:
        return None

    balance_sheet_rows: dict[str, Any] = {}
    try:
        balance_sheet = getattr(obj, 'balance_sheet', None)
        if balance_sheet is not None and not getattr(balance_sheet, 'empty', True):
            for idx in balance_sheet.index:
                label = str(idx)
                try:
                    value = balance_sheet.loc[idx].iloc[0]
                except Exception:
                    continue
                balance_sheet_rows[label] = value.item() if hasattr(value, 'item') else value
    except Exception:
        balance_sheet_rows = {}

    return {
        'symbol': symbol,
        'current_price': info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose'),
        'market_cap_diluted': info.get('marketCap'),
        'shares_outstanding_diluted': info.get('sharesOutstanding'),
        'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
        'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
        'dividend_rate': info.get('dividendRate'),
        'dividend_yield': info.get('dividendYield'),
        'target_mean_price': info.get('targetMeanPrice'),
        'target_high_price': info.get('targetHighPrice'),
        'target_low_price': info.get('targetLowPrice'),
        'analyst_count': info.get('numberOfAnalystOpinions'),
        'recommendation_key': info.get('recommendationKey'),
        'balance_sheet': balance_sheet_rows,
        'financial_currency': info.get('financialCurrency') or info.get('currency'),
        'sector': info.get('sector'),
        'industry': info.get('industry'),
        'long_business_summary': info.get('longBusinessSummary'),
    }


def _money_field(value: Any, *, source: str, as_of: str, scale_to_millions: bool = False, note: str | None = None) -> dict[str, Any] | None:
    if not isinstance(value, (int, float)):
        return None
    out = float(value)
    if scale_to_millions:
        out /= 1_000_000.0
    payload = {'value': out, 'source': source, 'as_of': as_of}
    if note:
        payload['note'] = note
    return payload


def _count_field(value: Any, *, source: str, as_of: str, note: str | None = None) -> dict[str, Any] | None:
    if not isinstance(value, (int, float)):
        return None
    payload = {'value': int(value), 'source': source, 'as_of': as_of}
    if note:
        payload['note'] = note
    return payload


def _text_field(value: Any, *, source: str, as_of: str, note: str | None = None) -> dict[str, Any] | None:
    if not value:
        return None
    payload = {'value': str(value), 'source': source, 'as_of': as_of}
    if note:
        payload['note'] = note
    return payload


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _extract_balance_sheet_value(balance_sheet: dict[str, Any], *labels: str) -> float | None:
    for label in labels:
        value = _coerce_float(balance_sheet.get(label))
        if value is not None:
            return value
    return None


def _build_ev_bridge(*, market_cap_aud_m: dict[str, Any] | None, yahoo_payload: dict[str, Any] | None, as_of: str) -> dict[str, Any] | None:
    if not market_cap_aud_m or not yahoo_payload:
        return None
    balance_sheet = yahoo_payload.get('balance_sheet') or {}
    total_debt = _extract_balance_sheet_value(balance_sheet, 'Total Debt', 'Current Debt', 'Long Term Debt')
    cash = _extract_balance_sheet_value(balance_sheet, 'Cash And Cash Equivalents', 'Cash And Cash Equivalents And Short Term Investments')
    net_debt = _extract_balance_sheet_value(balance_sheet, 'Net Debt')
    if net_debt is None and total_debt is not None and cash is not None:
        net_debt = total_debt - cash
    if net_debt is None:
        return None
    ev_value = float(market_cap_aud_m['value']) + (net_debt / 1_000_000.0)
    return {
        'enterprise_value_aud_m': {
            'value': ev_value,
            'source': 'derived_asx_yahoo_bridge',
            'as_of': as_of,
            'formula': 'market_cap_official + net_debt',
        },
        'inputs': {
            'market_cap_aud_m': market_cap_aud_m,
            'net_debt_aud_m': _money_field(net_debt, source='yahoo_finance', as_of=as_of, scale_to_millions=True),
            'total_debt_aud_m': _money_field(total_debt, source='yahoo_finance', as_of=as_of, scale_to_millions=True) if total_debt is not None else None,
            'cash_aud_m': _money_field(cash, source='yahoo_finance', as_of=as_of, scale_to_millions=True) if cash is not None else None,
        },
    }


def build_deterministic_lead_context(
    ticker: str,
    *,
    asx_fetcher: Callable[[str], dict[str, Any] | None] | None = None,
    fmp_fetcher: Callable[[str], dict[str, Any] | None] | None = None,
    yahoo_fetcher: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    ticker_upper = ticker.upper()
    today = _today_utc()
    asx_payload = (asx_fetcher or _fetch_asx_market_snapshot)(ticker_upper) or {}
    fmp_payload = (fmp_fetcher or _fetch_fmp_profile)(ticker_upper) or {}
    yahoo_payload = (yahoo_fetcher or _fetch_yahoo_secondary_context)(ticker_upper) or {}

    header = asx_payload.get('header') or {}
    key_stats = asx_payload.get('key_statistics') or {}

    market_snapshot = {
        'share_price': _money_field(header.get('priceLast'), source='asx_api', as_of=today),
        'market_cap_aud': _money_field(header.get('marketCap'), source='asx_api', as_of=today, scale_to_millions=True),
        'shares_on_issue': _count_field(key_stats.get('numOfShares'), source='asx_api', as_of=today),
        'fifty_two_week_high': _money_field(key_stats.get('priceFiftyTwoWeekHigh'), source='asx_api', as_of=today),
        'fifty_two_week_low': _money_field(key_stats.get('priceFiftyTwoWeekLow'), source='asx_api', as_of=today),
        'trading_volume': _count_field(header.get('volume'), source='asx_api', as_of=today),
        'eps_basic': _money_field(key_stats.get('earningsPerShare'), source='asx_api', as_of=today),
        'pe_ratio': _money_field(key_stats.get('priceEarningsRatio'), source='asx_api', as_of=today),
    }

    identity = {
        'company_name': header.get('displayName') or fmp_payload.get('name'),
        'ticker': ticker_upper,
        'resolved_symbol': fmp_payload.get('symbol'),
        'exchange': fmp_payload.get('exchange') or 'ASX',
        'exchange_full_name': fmp_payload.get('exchange_full_name'),
        'currency': fmp_payload.get('currency') or 'AUD',
        'sector': header.get('sector') or fmp_payload.get('sector') or yahoo_payload.get('sector'),
        'industry': header.get('industryGroup') or fmp_payload.get('industry') or yahoo_payload.get('industry'),
        'country': fmp_payload.get('country'),
        'description': fmp_payload.get('description') or yahoo_payload.get('long_business_summary'),
        'ceo': fmp_payload.get('ceo'),
        'website': fmp_payload.get('website'),
        'listing_date': header.get('dateListed'),
    }

    consensus_snapshot = {
        'analyst_target_price_avg': _money_field(yahoo_payload.get('target_mean_price'), source='yahoo_finance', as_of=today, note='Secondary consensus surface'),
        'analyst_target_price_high': _money_field(yahoo_payload.get('target_high_price'), source='yahoo_finance', as_of=today, note='Secondary consensus surface'),
        'analyst_target_price_low': _money_field(yahoo_payload.get('target_low_price'), source='yahoo_finance', as_of=today, note='Secondary consensus surface'),
        'analyst_count': _count_field(yahoo_payload.get('analyst_count'), source='yahoo_finance', as_of=today, note='Secondary consensus surface'),
        'analyst_consensus_rating': _text_field(yahoo_payload.get('recommendation_key'), source='yahoo_finance', as_of=today, note='Secondary consensus surface'),
        'dividend_per_share': _money_field(yahoo_payload.get('dividend_rate'), source='yahoo_finance', as_of=today, note='Secondary market surface'),
        'dividend_yield_pct': _money_field((yahoo_payload.get('dividend_yield') or 0) * 100 if isinstance(yahoo_payload.get('dividend_yield'), (int, float)) else None, source='yahoo_finance', as_of=today, note='Secondary market surface'),
    }

    ev_bridge = _build_ev_bridge(market_cap_aud_m=market_snapshot['market_cap_aud'], yahoo_payload=yahoo_payload, as_of=today)

    conflicts: list[str] = []
    asx_price = market_snapshot['share_price']['value'] if market_snapshot['share_price'] else None
    fmp_price = fmp_payload.get('price')
    if asx_price and isinstance(fmp_price, (int, float)) and asx_price > 0:
        diff = abs(float(fmp_price) - asx_price) / asx_price
        if diff > 0.05:
            conflicts.append(f'Price conflict: ASX={asx_price} vs FMP={float(fmp_price)}')
    asx_mcap = market_snapshot['market_cap_aud']['value'] if market_snapshot['market_cap_aud'] else None
    fmp_mcap = fmp_payload.get('market_cap')
    if asx_mcap and isinstance(fmp_mcap, (int, float)) and asx_mcap > 0:
        fmp_mcap_m = float(fmp_mcap) / 1_000_000.0
        diff = abs(fmp_mcap_m - asx_mcap) / asx_mcap
        if diff > 0.05:
            conflicts.append(f'Market cap conflict: ASX={asx_mcap}m vs FMP={fmp_mcap_m}m')

    has_primary_market_snapshot = all(
        market_snapshot.get(key) is not None
        for key in ('share_price', 'market_cap_aud', 'shares_on_issue')
    )
    market_data_status = 'ok' if has_primary_market_snapshot and not conflicts else 'conflicted' if conflicts else 'unavailable'

    return {
        'ticker': ticker_upper,
        'as_of': today,
        'has_primary_market_snapshot': has_primary_market_snapshot,
        'market_data_status': market_data_status,
        'market_data_conflicted': bool(conflicts),
        'conflicts': conflicts,
        'market_snapshot': market_snapshot,
        'identity': identity,
        'consensus_snapshot': consensus_snapshot,
        'ev_bridge': ev_bridge,
        'secondary_market_data': {
            'fmp_price': _money_field(fmp_payload.get('price'), source='fmp_api', as_of=today),
            'fmp_market_cap_aud': _money_field(fmp_payload.get('market_cap'), source='fmp_api', as_of=today, scale_to_millions=True),
            'yahoo_market_cap_diluted_aud': _money_field(yahoo_payload.get('market_cap_diluted'), source='yahoo_finance', as_of=today, scale_to_millions=True, note='Diluted market cap; not authoritative for ASX'),
            'yahoo_shares_outstanding_diluted': _count_field(yahoo_payload.get('shares_outstanding_diluted'), source='yahoo_finance', as_of=today, note='Diluted shares; not shares on issue'),
            'yahoo_fifty_two_week_high': _money_field(yahoo_payload.get('fifty_two_week_high'), source='yahoo_finance', as_of=today),
            'yahoo_fifty_two_week_low': _money_field(yahoo_payload.get('fifty_two_week_low'), source='yahoo_finance', as_of=today),
        },
        'policy': {
            'primary_market_source': 'asx_api',
            'fallback_market_sources': ['fmp_api', 'yahoo_finance', 'web_search'],
            'consensus_source': 'yahoo_finance',
            'enterprise_value_policy': 'derive_from_market_cap_plus_net_debt_when_bridge_inputs_exist',
            'halt_on_conflict': True,
            'halt_on_missing_primary_market_snapshot': True,
        },
    }
