import numpy as np

from secguard.policy_learning import apply_thresholds, build_scenarios, threshold_candidates


def test_threshold_candidates_are_valid_and_include_fixed_policy() -> None:
    candidates = threshold_candidates()
    assert (0.15, 0.40, 0.75) in candidates
    assert all(l1 < l2 < quarantine for l1, l2, quarantine in candidates)


def test_scenario_generation_is_seed_reproducible() -> None:
    benign = np.array([0.0, 0.01, 0.02])
    attack = np.array([0.98, 0.99, 1.0])
    first = build_scenarios(benign, attack, [42])
    second = build_scenarios(benign, attack, [42])
    assert first == second


def test_learned_threshold_application_preserves_sla_floor() -> None:
    scenario = [
        {
            "slice_id": "mc",
            "service": "MC",
            "requested_level": 2,
            "risk_score": 0.01,
        }
    ]
    decision = apply_thresholds(scenario, (0.20, 0.45, 0.80))[0]
    assert decision["target_level"] == 2
    assert decision["action"] == "KEEP"

