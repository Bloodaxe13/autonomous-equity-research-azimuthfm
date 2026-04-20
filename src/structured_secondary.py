from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.contracts_runtime import SourceAuthorityClass, SourceMetadata, StructuredSecondaryMetric, VerificationStatus


DEFAULT_MARKETSCREENER_CACHE_DIR = Path('/mnt/c/Users/Daniel/AzimuthAI-Research-V2/artifacts/marketscreener_cache')
ALLOWED_METRICS = {'roic_pct', 'eps_revision_3m_pct'}


def load_structured_secondary_metrics(
    ticker: str,
    *,
    cache_dir: str | Path | None = None,
) -> list[StructuredSecondaryMetric]:
    base = Path(cache_dir) if cache_dir is not None else DEFAULT_MARKETSCREENER_CACHE_DIR
    if not base.exists():
        return []
    ticker_upper = ticker.upper()
    for data_path in sorted(base.glob('*_data.json')):
        payload = _read_json(data_path)
        if not isinstance(payload, dict):
            continue
        if str(payload.get('ticker') or '').upper() != ticker_upper:
            continue
        prefix = data_path.name[:-len('_data.json')]
        url_path = data_path.with_name(f'{prefix}_url.json')
        url_payload = _read_json(url_path)
        return _extract_metrics(ticker_upper, payload, data_path=data_path, url_payload=url_payload)
    return []


def build_structured_secondary_context(
    ticker: str,
    *,
    cache_dir: str | Path | None = None,
) -> dict[str, Any]:
    metrics = load_structured_secondary_metrics(ticker, cache_dir=cache_dir)
    return {
        'ticker': ticker.upper(),
        'metrics': [item.model_dump(mode='json') for item in metrics],
        'has_data': bool(metrics),
        'policy': {
            'role': 'trusted_structured_secondary_scaffolding',
            'allowed_metrics': sorted(ALLOWED_METRICS),
            'must_verify_before_final_claim': True,
            'must_not_override_primary_truth': True,
        },
    }


def _extract_metrics(
    ticker: str,
    payload: dict[str, Any],
    *,
    data_path: Path,
    url_payload: dict[str, Any] | None,
) -> list[StructuredSecondaryMetric]:
    source_url = str((url_payload or {}).get('url') or payload.get('url') or 'unknown')
    captured_at = (url_payload or {}).get('cached_at') or payload.get('cached_at')
    title = f"MarketScreener cached structured financials ({ticker})"
    metrics: list[StructuredSecondaryMetric] = []

    roic = _latest_numeric(payload.get('roic'))
    if roic is not None:
        metrics.append(
            StructuredSecondaryMetric(
                ticker=ticker,
                metric='roic_pct',
                value=round(roic, 3),
                unit='pct',
                source_url=source_url,
                source_title=title,
                source_metadata=_source_metadata(
                    captured_at=captured_at,
                    raw_payload_path=data_path,
                    quality_flags=['aggregator', 'cached_snapshot', 'ratio_series'],
                    comparability_flags=['period_alignment_required', 'definition_alignment_required'],
                ),
            )
        )

    eps_revision = _latest_revision_percent(payload.get('consensus_revisions'))
    if eps_revision is not None:
        metrics.append(
            StructuredSecondaryMetric(
                ticker=ticker,
                metric='eps_revision_3m_pct',
                value=round(eps_revision, 3),
                unit='pct',
                source_url=source_url,
                source_title=title,
                source_metadata=_source_metadata(
                    captured_at=captured_at,
                    raw_payload_path=data_path,
                    quality_flags=['aggregator', 'cached_snapshot', 'analyst_consensus'],
                    comparability_flags=['estimate_horizon_alignment_required', 'consensus_methodology_vendor_defined'],
                ),
            )
        )

    return metrics


def _source_metadata(
    *,
    captured_at: str | None,
    raw_payload_path: Path,
    quality_flags: list[str],
    comparability_flags: list[str],
) -> SourceMetadata:
    return SourceMetadata(
        authority_class=SourceAuthorityClass.TRUSTED_STRUCTURED_SECONDARY,
        source_family='marketscreener',
        source_type='cached_aggregator_financials',
        origin='marketscreener_cache',
        verification_status=VerificationStatus.UNVERIFIED,
        captured_at=captured_at,
        raw_payload_path=str(raw_payload_path),
        quality_flags=quality_flags,
        comparability_flags=comparability_flags,
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _latest_numeric(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in sorted(value.keys(), reverse=True):
            raw = value[key]
            if isinstance(raw, (int, float)):
                return float(raw)
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _latest_revision_percent(value: Any) -> float | None:
    if not isinstance(value, list):
        return None
    for item in reversed(value):
        if not isinstance(item, dict):
            continue
        raw = item.get('change_percent')
        if isinstance(raw, (int, float)):
            return float(raw)
    return None
