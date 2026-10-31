import numpy as np
import pandas as pd
import pytest

from secguard.algorithm_selector import (
    choose_oracle,
    computation_savings,
    evaluate_choices,
    quality_retention,
    predict_with_fallback,
    request_schedule,
    split_by_iteration,
)
from sklearn.ensemble import RandomForestClassifier


def test_oracle_selects_fastest_algorithm_inside_quality_budget() -> None:
    profits = {"opt": 100.0, "iar": 94.0, "dtr": 97.0, "rnr": 96.0}
    latencies = {"opt": 2.0, "iar": 0.1, "dtr": 0.4, "rnr": 0.2}
    feasible = {name: True for name in profits}
    selected, best = choose_oracle(profits, latencies, feasible, 0.95)
    assert selected == "rnr"
    assert best == 100.0


def test_oracle_excludes_infeasible_fast_algorithm() -> None:
    profits = {"opt": 100.0, "iar": 99.0, "dtr": 98.0, "rnr": 97.0}
    latencies = {"opt": 2.0, "iar": 0.01, "dtr": 0.2, "rnr": 0.3}
    feasible = {"opt": True, "iar": False, "dtr": True, "rnr": True}
    selected, _ = choose_oracle(profits, latencies, feasible, 0.95)
    assert selected == "dtr"


def test_oracle_requires_a_feasible_candidate() -> None:
    values = {name: 1.0 for name in ("opt", "iar", "dtr", "rnr")}
    with pytest.raises(ValueError, match="at least one feasible"):
        choose_oracle(values, values, {name: False for name in values}, 0.95)


def test_quality_retention_is_bounded_and_penalizes_infeasibility() -> None:
    assert quality_retention(95.0, 100.0) == pytest.approx(0.95)
    assert quality_retention(110.0, 100.0) == 1.0
    assert quality_retention(100.0, 100.0, feasible=False) == 0.0


def test_computation_savings_separates_work_and_solver_calls() -> None:
    result = computation_savings(1.2, 1.6)
    assert result["solver_work_reduction"] == pytest.approx(0.25)
    assert result["solver_call_reduction"] == pytest.approx(0.75)


def test_group_split_keeps_iterations_disjoint() -> None:
    features = pd.DataFrame({"feature": np.arange(8)})
    outcomes = pd.DataFrame(
        {"iteration": [0, 0, 1, 1, 2, 2, 3, 3], "oracle": ["opt"] * 8}
    )
    x_train, x_test, train_rows, test_rows = split_by_iteration(
        features, outcomes, train_iterations=2
    )
    assert len(x_train) == len(x_test) == 4
    assert set(train_rows["iteration"]).isdisjoint(test_rows["iteration"])


def test_request_schedule_is_deterministic() -> None:
    first = request_schedule(3, 12)
    assert np.array_equal(first, request_schedule(3, 12))
    assert set(np.unique(first)).issubset({0, 1, 2, 3})


def test_low_confidence_prediction_uses_safe_fallback() -> None:
    features = pd.DataFrame({"x": [0.0, 0.0, 1.0, 1.0]})
    labels = ["iar", "rnr", "iar", "rnr"]
    model = RandomForestClassifier(n_estimators=20, random_state=1).fit(
        features, labels
    )
    predictions, confidence = predict_with_fallback(
        model, pd.DataFrame({"x": [0.5]}), confidence_threshold=1.0
    )
    assert predictions.tolist() == ["opt"]
    assert confidence[0] < 1.0


def test_choice_evaluation_reports_latency_quality_and_safety() -> None:
    row = {
        "deadline": 1.0,
        "best_profit": 100.0,
        "opt_profit": 100.0,
        "opt_latency": 0.5,
        "opt_feasible": True,
        "iar_profit": 90.0,
        "iar_latency": 0.1,
        "iar_feasible": True,
        "dtr_profit": 98.0,
        "dtr_latency": 0.2,
        "dtr_feasible": True,
        "rnr_profit": 97.0,
        "rnr_latency": 0.3,
        "rnr_feasible": True,
    }
    result = evaluate_choices(["dtr"], pd.DataFrame([row]))
    assert result["mean_latency_seconds"] == pytest.approx(0.2)
    assert result["mean_quality_retention"] == pytest.approx(0.98)
    assert result["within_5_percent_rate"] == 1.0
    assert result["deadline_success_rate"] == 1.0
