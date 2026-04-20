from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ScenarioCase:
    name: str
    probability: float
    value_per_share: float


@dataclass(frozen=True)
class ScenarioWeightingResult:
    scenarios: list[ScenarioCase]
    total_probability: float
    weighted_value_per_share: float
    implied_return_pct: float | None


def probability_weighted_value(*, current_price: float | None, scenarios: Iterable[ScenarioCase]) -> ScenarioWeightingResult:
    scenario_list = list(scenarios)
    if not scenario_list:
        raise ValueError("scenarios must not be empty")

    raw_total_probability = sum(case.probability for case in scenario_list)
    if raw_total_probability <= 0:
        raise ValueError("probabilities must sum to a positive number")

    normalized_scenarios = [
        ScenarioCase(
            name=case.name,
            probability=case.probability / raw_total_probability,
            value_per_share=case.value_per_share,
        )
        for case in scenario_list
    ]
    weighted_value = sum(case.probability * case.value_per_share for case in normalized_scenarios)
    implied_return_pct = None if current_price in (None, 0) else (weighted_value / current_price) - 1.0
    return ScenarioWeightingResult(
        scenarios=normalized_scenarios,
        total_probability=sum(case.probability for case in normalized_scenarios),
        weighted_value_per_share=weighted_value,
        implied_return_pct=implied_return_pct,
    )
