from __future__ import annotations

import math

from src.calculations.sensitivity import dcf_sensitivity_table


def test_sensitivity_table_returns_wacc_by_growth_grid() -> None:
    table = dcf_sensitivity_table(
        free_cash_flows=[100.0, 110.0, 120.0],
        wacc_values=[0.09, 0.10],
        terminal_growth_values=[0.02, 0.03],
        cash=50.0,
        debt=20.0,
        shares_outstanding=10.0,
    )

    assert list(table.index) == [0.09, 0.10]
    assert list(table.columns) == [0.02, 0.03]
    assert math.isclose(table.loc[0.10, 0.03], 162.8583234946871, rel_tol=1e-9)
    assert table.loc[0.09, 0.03] > table.loc[0.10, 0.03]
