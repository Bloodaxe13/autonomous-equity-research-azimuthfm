from __future__ import annotations

import math

from src.calculations.relative_valuation import CompanyMultiples, PeerMultiples, relative_valuation


def test_relative_valuation_uses_peer_medians_and_method_weights() -> None:
    company = CompanyMultiples(
        revenue=400.0,
        ebitda=80.0,
        earnings=50.0,
        net_debt=100.0,
        shares_outstanding=20.0,
    )
    peers = [
        PeerMultiples(ticker="AAA", ev_to_revenue=2.0, ev_to_ebitda=9.0, pe=14.0),
        PeerMultiples(ticker="BBB", ev_to_revenue=3.0, ev_to_ebitda=11.0, pe=18.0),
        PeerMultiples(ticker="CCC", ev_to_revenue=4.0, ev_to_ebitda=13.0, pe=22.0),
    ]

    result = relative_valuation(company=company, peers=peers)

    assert result.peer_count == 3
    assert result.median_multiples == {"ev_to_revenue": 3.0, "ev_to_ebitda": 11.0, "pe": 18.0}
    assert math.isclose(result.implied_values_per_share["ev_to_revenue"], 55.0, rel_tol=1e-9)
    assert math.isclose(result.implied_values_per_share["ev_to_ebitda"], 39.0, rel_tol=1e-9)
    assert math.isclose(result.implied_values_per_share["pe"], 45.0, rel_tol=1e-9)
    assert math.isclose(result.weighted_value_per_share, 46.333333333333336, rel_tol=1e-9)
