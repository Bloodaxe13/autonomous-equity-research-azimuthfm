from __future__ import annotations

import math

from src.calculations.scenario_weighting import ScenarioCase, probability_weighted_value


def test_probability_weighted_value_normalizes_probabilities() -> None:
    result = probability_weighted_value(
        current_price=10.0,
        scenarios=[
            ScenarioCase(name="bear", probability=20.0, value_per_share=7.0),
            ScenarioCase(name="base", probability=50.0, value_per_share=11.0),
            ScenarioCase(name="bull", probability=30.0, value_per_share=15.0),
        ],
    )

    assert math.isclose(result.total_probability, 1.0, rel_tol=1e-9)
    assert math.isclose(result.weighted_value_per_share, 11.4, rel_tol=1e-9)
    assert math.isclose(result.implied_return_pct, 0.14, rel_tol=1e-9)
