from __future__ import annotations

from typing import Optional


def _round_or_none(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def safe_divide(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def gross_margin(gross_profit: float, revenue: float) -> float | None:
    return safe_divide(gross_profit, revenue)


def ebit_margin(ebit: float, revenue: float) -> float | None:
    return safe_divide(ebit, revenue)


def net_margin(net_income: float, revenue: float) -> float | None:
    return safe_divide(net_income, revenue)


def revenue_growth(current_period_revenue: float, prior_period_revenue: float) -> float | None:
    return safe_divide(current_period_revenue - prior_period_revenue, prior_period_revenue)


def net_debt(debt: float, cash: float) -> float:
    return debt - cash


def enterprise_value(*, market_cap: float, debt: float, cash: float) -> float:
    return market_cap + debt - cash


def ev_to_revenue(*, enterprise_value: float, revenue: float) -> float | None:
    value = safe_divide(enterprise_value, revenue)
    return _round_or_none(value, 4)


def ev_to_ebitda(*, enterprise_value: float, ebitda: float) -> float | None:
    value = safe_divide(enterprise_value, ebitda)
    return _round_or_none(value, 4)


def pe_ratio(*, price_per_share: float, earnings_per_share: float) -> float | None:
    value = safe_divide(price_per_share, earnings_per_share)
    return _round_or_none(value, 4)


def return_on_equity(*, net_income: float, average_equity: float) -> float | None:
    return safe_divide(net_income, average_equity)


def return_on_assets(*, net_income: float, average_assets: float) -> float | None:
    return safe_divide(net_income, average_assets)


def return_on_invested_capital(*, ebit: float, tax_rate: float, debt: float, equity: float, cash: float = 0.0) -> float | None:
    invested_capital = debt + equity - cash
    if invested_capital == 0:
        return None
    nopat = ebit * (1.0 - tax_rate)
    return nopat / invested_capital
