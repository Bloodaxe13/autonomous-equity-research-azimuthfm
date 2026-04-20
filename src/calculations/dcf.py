from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class DCFResult:
    discounted_free_cash_flows: list[float]
    terminal_value: float
    discounted_terminal_value: float
    enterprise_value: float
    equity_value: float
    value_per_share: float | None


def terminal_value_gordon_growth(*, final_year_fcf: float, wacc: float, terminal_growth: float) -> float:
    if wacc <= terminal_growth:
        raise ValueError("wacc must be greater than terminal_growth")
    return final_year_fcf * (1.0 + terminal_growth) / (wacc - terminal_growth)


def terminal_value_exit_multiple(*, metric: float, exit_multiple: float) -> float:
    return metric * exit_multiple


def discount_cash_flows(cash_flows: Sequence[float], discount_rate: float) -> list[float]:
    return [cash_flow / ((1.0 + discount_rate) ** period) for period, cash_flow in enumerate(cash_flows, start=1)]


def dcf_valuation(
    *,
    free_cash_flows: Sequence[float],
    wacc: float,
    terminal_growth: float | None = None,
    terminal_metric: float | None = None,
    exit_multiple: float | None = None,
    cash: float = 0.0,
    debt: float = 0.0,
    shares_outstanding: float | None = None,
) -> DCFResult:
    if not free_cash_flows:
        raise ValueError("free_cash_flows must not be empty")
    discounted_free_cash_flows = discount_cash_flows(free_cash_flows, wacc)
    if terminal_growth is not None:
        terminal_value = terminal_value_gordon_growth(
            final_year_fcf=free_cash_flows[-1],
            wacc=wacc,
            terminal_growth=terminal_growth,
        )
    elif terminal_metric is not None and exit_multiple is not None:
        terminal_value = terminal_value_exit_multiple(metric=terminal_metric, exit_multiple=exit_multiple)
    else:
        raise ValueError("provide terminal_growth or terminal_metric with exit_multiple")

    discounted_terminal_value = terminal_value / ((1.0 + wacc) ** len(free_cash_flows))
    enterprise_value = sum(discounted_free_cash_flows) + discounted_terminal_value
    equity_value = enterprise_value + cash - debt
    value_per_share = None if not shares_outstanding else equity_value / shares_outstanding
    return DCFResult(
        discounted_free_cash_flows=discounted_free_cash_flows,
        terminal_value=terminal_value,
        discounted_terminal_value=discounted_terminal_value,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        value_per_share=value_per_share,
    )
