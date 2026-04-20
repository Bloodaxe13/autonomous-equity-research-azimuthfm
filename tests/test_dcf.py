from __future__ import annotations

import math

from src.calculations.dcf import dcf_valuation, terminal_value_exit_multiple, terminal_value_gordon_growth


def test_terminal_value_formulas() -> None:
    assert math.isclose(terminal_value_gordon_growth(final_year_fcf=100.0, wacc=0.10, terminal_growth=0.03), 1_471.4285714285716)
    assert terminal_value_exit_multiple(metric=120.0, exit_multiple=10.0) == 1_200.0


def test_dcf_valuation_with_gordon_growth_terminal_value() -> None:
    result = dcf_valuation(
        free_cash_flows=[100.0, 110.0, 120.0],
        wacc=0.10,
        terminal_growth=0.03,
        cash=50.0,
        debt=20.0,
        shares_outstanding=10.0,
    )

    assert math.isclose(result.enterprise_value, 1_598.583234946871, rel_tol=1e-9)
    assert math.isclose(result.equity_value, 1_628.583234946871, rel_tol=1e-9)
    assert math.isclose(result.value_per_share, 162.8583234946871, rel_tol=1e-9)
    assert len(result.discounted_free_cash_flows) == 3
