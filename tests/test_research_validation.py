import pytest

from secguard.policy_learning import threshold_candidates
from secguard.research_validation import (
    paired_test,
    pareto_frontier,
    sampled_candidate_indices,
)


def test_pareto_frontier_removes_dominated_policy() -> None:
    rows = [
        {"thresholds": (0.1, 0.2, 0.8), "mean_profit": 10.0, "mean_exposure": 0.4},
        {"thresholds": (0.2, 0.3, 0.8), "mean_profit": 12.0, "mean_exposure": 0.3},
        {"thresholds": (0.3, 0.4, 0.8), "mean_profit": 8.0, "mean_exposure": 0.2},
    ]
    frontier = pareto_frontier(rows)
    assert [row["thresholds"] for row in frontier] == [
        (0.3, 0.4, 0.8),
        (0.2, 0.3, 0.8),
    ]


def test_paired_test_reports_direction_and_ties() -> None:
    reference = [{"profit": 1.0}, {"profit": 2.0}, {"profit": 3.0}]
    proposed = [{"profit": 2.0}, {"profit": 2.0}, {"profit": 5.0}]
    result = paired_test(reference, proposed, "profit")
    assert result["positive"] == 2
    assert result["negative"] == 0
    assert result["ties"] == 1
    assert result["mean_difference"] == 1.0


def test_sampled_candidate_indices_honours_exact_budget_and_fixed_policy() -> None:
    candidates = threshold_candidates()
    sampled = sampled_candidate_indices(candidates, budget=81)
    assert len(sampled) == 81
    assert candidates.index((0.15, 0.40, 0.75)) in sampled


def test_sampled_candidate_indices_rejects_invalid_budget() -> None:
    with pytest.raises(ValueError):
        sampled_candidate_indices(threshold_candidates(), budget=0)
