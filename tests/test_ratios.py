from __future__ import annotations

import math

from src.calculations.ratios import (
    enterprise_value,
    ev_to_ebitda,
    ev_to_revenue,
    gross_margin,
    net_debt,
    return_on_invested_capital,
)


def test_basic_ratio_functions() -> None:
    assert gross_margin(400.0, 1_000.0) == 0.4
    assert net_debt(150.0, 40.0) == 110.0
    assert enterprise_value(market_cap=1_200.0, debt=150.0, cash=40.0) == 1_310.0
    assert ev_to_revenue(enterprise_value=1_310.0, revenue=500.0) == 2.62
    assert ev_to_ebitda(enterprise_value=1_310.0, ebitda=100.0) == 13.1


def test_roic_excludes_excess_cash() -> None:
    roic = return_on_invested_capital(
        ebit=120.0,
        tax_rate=0.30,
        debt=200.0,
        equity=500.0,
        cash=80.0,
    )
    assert math.isclose(roic, 84.0 / 620.0, rel_tol=1e-9)
