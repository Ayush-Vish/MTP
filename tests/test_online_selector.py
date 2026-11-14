from types import SimpleNamespace as Entity

import numpy as np
import pytest

from secguard.online_selector import (
    PerformanceSelector, ReplayState, common_state_audit, fgr_choice, oracle_label, state_features,
    summarize,
)


def outcomes():
    return {
        a: {"profit": profit, "wall_seconds": seconds, "feasible": True,
            "timeout": False, "error": None}
        for a, profit, seconds in (
            ("opt", 100, 1.0), ("iar", 80, 0.01),
            ("dtr", 99, 0.2), ("rnr", 96, 0.1),
        )
    }


def test_fgr_reference_preserves_opt_priority_and_timeout_fallback():
    values = outcomes()
    assert fgr_choice(values) == "opt"
    values["opt"]["timeout"] = True
    assert fgr_choice(values) == "dtr"


def test_oracle_keeps_all_failure_rows_explicit():
    values = outcomes()
    assert oracle_label(values) == "rnr"
    for value in values.values():
        value["feasible"] = False
    assert oracle_label(values) == "none"


def test_performance_ranking_excludes_fast_low_quality_and_late_candidates():
    model = PerformanceSelector()
    model.quality_floor, model.feasibility_floor = 0.95, 0.75
    model.predictions = lambda _: {
        "opt": {"seconds": 5, "gain": 100, "success": 1},
        "iar": {"seconds": 0.01, "gain": 50, "success": 1},
        "dtr": {"seconds": 0.2, "gain": 100, "success": 1},
        "rnr": {"seconds": 0.1, "gain": 98, "success": 0.2},
    }
    assert model.rank({"deadline": 1})[0] == "dtr"


def test_features_use_actual_allocations_without_mutating_state():
    active = Entity(V_S=[Entity(C_REQ=20)], V_R=[Entity(K_REQ=2)], E=[Entity(B_REQ=3)])
    request = Entity(V_S=[Entity(C_REQ=90, Xi_REQ=2)], V_R=[Entity(K_REQ=1)],
                     E=[Entity(B_REQ=4, D_REQ=1)], gamma=0, kappa=0,
                     R=10, timeout=2, beta=1)
    state = ReplayState([active], [[[1, 0]]], [[[[[0, 0, 1]]]]])
    topology = ([Entity(C_MAX=100), Entity(C_MAX=100)],
                [Entity(Pi_MAX=[10])], [Entity()], [], [Entity(B_MAX=[20])], [])
    features = state_features(request, state, topology)
    assert features["cpu_load_proxy"] == pytest.approx(0.1)
    assert features["cpu_remaining"] == 180
    assert features["eligible_servers_proxy"] == 1
    assert features["radio_load_proxy"] == pytest.approx(0.2)
    assert features["active_bandwidth_demand_fraction"] == pytest.approx(0.15)
    assert len(state.requests) == 1


def test_summary_uses_final_profit_per_seed_not_sum_of_cumulative_profit():
    rows = []
    for seed, profits in ((1, [10, 20]), (2, [30, 40])):
        for step, profit in enumerate(profits):
            rows.append({"policy": "test", "seed": seed, "step": step,
                         "profit": profit, "wall_seconds": 0.1, "cpu_seconds": 0.05,
                         "solver_calls": 1, "accepted": True, "outcomes": {}})
    result = summarize(rows)["test"]
    assert result["mean_final_profit"] == 30
    assert result["mean_wall_seconds"] == pytest.approx(0.1)


def test_replay_state_does_not_share_mutable_defaults():
    first, second = ReplayState(), ReplayState()
    first.requests.append("request")
    assert second.requests == []


def test_audit_keeps_no_feasible_candidate_in_success_denominator():
    good = outcomes()
    failed = outcomes()
    for item in failed.values():
        item["feasible"] = False
    rows = [
        {"features": {"x": 1}, "outcomes": good, "oracle": "rnr"},
        {"features": {"x": 2}, "outcomes": failed, "oracle": "none"},
    ]
    model = PerformanceSelector()
    model.feature_names = ["x"]
    model.rank = lambda _: ["rnr"]
    classifier = Entity(classes_=np.asarray(["rnr"]), predict_proba=lambda _: np.asarray([[1.0]]))
    audit = common_state_audit(rows, model, classifier)["performance_selector"]
    assert audit["oracle_label_accuracy"] == 1.0
    assert audit["oracle_eligible_rows"] == 1
    assert audit["all_rows"] == 2
    assert audit["feasibility_all_rows"] == 0.5


def test_calibration_does_not_invent_second_class():
    model = PerformanceSelector()
    model.calibrators = {}
    model.predictions = lambda _: {a: {"success": 0.8} for a in outcomes()}
    status = model.calibrate([{"features": {}, "outcomes": outcomes()}])
    assert not model.calibrators
    assert all("unavailable" in message for message in status.values())


def test_quality_budget_is_relative_to_total_profit_not_incremental_gain():
    model = PerformanceSelector()
    model.quality_floor, model.feasibility_floor = 0.95, 0.75
    model.predictions = lambda _: {
        "opt": {"seconds": 1, "gain": 100, "success": 1},
        "iar": {"seconds": 0.01, "gain": 60, "success": 1},
        "dtr": {"seconds": 0.2, "gain": 99, "success": 1},
        "rnr": {"seconds": 0.1, "gain": 98, "success": 1},
    }
    assert model.rank({"deadline": 2, "previous_profit": 0})[0] == "rnr"
    assert model.rank({"deadline": 2, "previous_profit": 1000})[0] == "iar"
