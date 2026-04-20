from __future__ import annotations

import math

from src.calculations.reverse_dcf import implied_terminal_growth_rate


def test_reverse_dcf_solves_for_implied_terminal_growth_rate() -> None:
    implied_growth = implied_terminal_growth_rate(
        target_enterprise_value=1_598.583234946871,
        free_cash_flows=[100.0, 110.0, 120.0],
        wacc=0.10,
    )

    assert math.isclose(implied_growth, 0.03, abs_tol=1e-6)
