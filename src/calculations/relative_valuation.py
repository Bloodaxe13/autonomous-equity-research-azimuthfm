from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class PeerMultiples:
    ticker: str
    ev_to_revenue: float | None = None
    ev_to_ebitda: float | None = None
    pe: float | None = None


@dataclass(frozen=True)
class CompanyMultiples:
    revenue: float | None = None
    ebitda: float | None = None
    earnings: float | None = None
    net_debt: float = 0.0
    shares_outstanding: float | None = None


@dataclass(frozen=True)
class RelativeValuationResult:
    peer_count: int
    median_multiples: dict[str, float]
    implied_values_per_share: dict[str, float]
    weighted_value_per_share: float | None


def _median(values: list[float]) -> float | None:
    return median(values) if values else None


def relative_valuation(
    *,
    company: CompanyMultiples,
    peers: Iterable[PeerMultiples],
    method_weights: dict[str, float] | None = None,
) -> RelativeValuationResult:
    peer_list = list(peers)
    method_weights = method_weights or {"ev_to_revenue": 1.0, "ev_to_ebitda": 1.0, "pe": 1.0}

    ev_to_revenue_values = [peer.ev_to_revenue for peer in peer_list if peer.ev_to_revenue is not None]
    ev_to_ebitda_values = [peer.ev_to_ebitda for peer in peer_list if peer.ev_to_ebitda is not None]
    pe_values = [peer.pe for peer in peer_list if peer.pe is not None]

    median_multiples: dict[str, float] = {}
    implied_values_per_share: dict[str, float] = {}

    median_ev_to_revenue = _median(ev_to_revenue_values)
    if median_ev_to_revenue is not None and company.revenue is not None and company.shares_outstanding:
        median_multiples["ev_to_revenue"] = median_ev_to_revenue
        equity_value = median_ev_to_revenue * company.revenue - company.net_debt
        implied_values_per_share["ev_to_revenue"] = equity_value / company.shares_outstanding

    median_ev_to_ebitda = _median(ev_to_ebitda_values)
    if median_ev_to_ebitda is not None and company.ebitda is not None and company.shares_outstanding:
        median_multiples["ev_to_ebitda"] = median_ev_to_ebitda
        equity_value = median_ev_to_ebitda * company.ebitda - company.net_debt
        implied_values_per_share["ev_to_ebitda"] = equity_value / company.shares_outstanding

    median_pe = _median(pe_values)
    if median_pe is not None and company.earnings is not None and company.shares_outstanding:
        median_multiples["pe"] = median_pe
        equity_value = median_pe * company.earnings
        implied_values_per_share["pe"] = equity_value / company.shares_outstanding

    weighted_numerator = 0.0
    total_weight = 0.0
    for method, value in implied_values_per_share.items():
        weight = method_weights.get(method, 0.0)
        if weight <= 0:
            continue
        weighted_numerator += weight * value
        total_weight += weight
    weighted_value_per_share = None if total_weight == 0 else weighted_numerator / total_weight

    return RelativeValuationResult(
        peer_count=len(peer_list),
        median_multiples=median_multiples,
        implied_values_per_share=implied_values_per_share,
        weighted_value_per_share=weighted_value_per_share,
    )
