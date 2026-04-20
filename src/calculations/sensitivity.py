from __future__ import annotations

from typing import Sequence

import pandas as pd

from .dcf import dcf_valuation


def dcf_sensitivity_table(
    *,
    free_cash_flows: Sequence[float],
    wacc_values: Sequence[float],
    terminal_growth_values: Sequence[float],
    cash: float = 0.0,
    debt: float = 0.0,
    shares_outstanding: float | None = None,
) -> pd.DataFrame:
    data: dict[float, dict[float, float | None]] = {}
    for wacc in wacc_values:
        row: dict[float, float | None] = {}
        for terminal_growth in terminal_growth_values:
            row[terminal_growth] = dcf_valuation(
                free_cash_flows=free_cash_flows,
                wacc=wacc,
                terminal_growth=terminal_growth,
                cash=cash,
                debt=debt,
                shares_outstanding=shares_outstanding,
            ).value_per_share
        data[wacc] = row
    table = pd.DataFrame.from_dict(data, orient="index")
    table.index.name = "wacc"
    table.columns.name = "terminal_growth"
    return table.sort_index().sort_index(axis=1)
