from __future__ import annotations

from typing import Sequence

from .dcf import dcf_valuation


def implied_terminal_growth_rate(
    *,
    target_enterprise_value: float,
    free_cash_flows: Sequence[float],
    wacc: float,
    lower_bound: float = -0.99,
    upper_bound: float = 0.50,
    tolerance: float = 1e-8,
    max_iterations: int = 200,
) -> float:
    if wacc <= lower_bound:
        raise ValueError("wacc must exceed lower_bound")
    upper_bound = min(upper_bound, wacc - 1e-9)

    low = lower_bound
    high = upper_bound
    for _ in range(max_iterations):
        mid = (low + high) / 2.0
        value = dcf_valuation(
            free_cash_flows=free_cash_flows,
            wacc=wacc,
            terminal_growth=mid,
        ).enterprise_value
        diff = value - target_enterprise_value
        if abs(diff) <= tolerance:
            return mid
        if diff < 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0
