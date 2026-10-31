import numpy as np
import pytest

from secguard.admission_control import (
    AdmissionAction,
    AdmissionConfig,
    AdmissionEnvironment,
    AdmissionRequest,
    DQNAgent,
    DQNConfig,
    ResourceCapacity,
    generate_episode,
)


def request(**overrides) -> AdmissionRequest:
    values = {
        "request_id": "r-1", "service": "eMBB", "cpu": 20.0,
        "radio": 10.0, "bandwidth": 25.0, "revenue": 50.0,
        "duration": 3, "isolation_level": 1, "risk_score": 0.4,
    }
    values.update(overrides)
    return AdmissionRequest(**values)


def test_state_contains_normalized_load_security_and_request_features() -> None:
    environment = AdmissionEnvironment([request()], ResourceCapacity(100, 100, 100))
    state = environment.reset()
    assert state.shape == (AdmissionEnvironment.state_size,)
    assert np.all((state >= 0.0) & (state <= 1.0))
    assert state[10] == pytest.approx(0.5)
    assert state[11] == pytest.approx(0.4)


def test_admit_occupies_capacity_and_earns_security_adjusted_profit() -> None:
    environment = AdmissionEnvironment([request(), request(request_id="r-2")])
    _, reward, done, info = environment.step(AdmissionAction.ADMIT)
    assert not done
    assert reward > 0
    assert environment.admitted == 1
    assert environment.used.tolist() == pytest.approx([20.0, 10.0, 25.0])
    assert info["security_cost"] > 0


def test_infeasible_admission_is_rejected_without_overcommitting() -> None:
    environment = AdmissionEnvironment([request(cpu=101.0)])
    _, reward, done, info = environment.step(AdmissionAction.ADMIT)
    assert done and reward < 0
    assert info["outcome"] == "infeasible"
    assert environment.infeasible == 1
    assert np.all(environment.used == 0)


def test_defer_requeues_request_then_enforces_limit() -> None:
    environment = AdmissionEnvironment([request()], config=AdmissionConfig(max_deferrals=1))
    _, first_reward, done, _ = environment.step(AdmissionAction.DEFER)
    assert not done and first_reward < 0
    assert environment.current.deferred_count == 1
    _, second_reward, done, info = environment.step(AdmissionAction.DEFER)
    assert done and second_reward < 0
    assert info["outcome"] == "defer_limit_rejected"
    assert environment.rejected == 1


def test_dqn_learning_updates_q_values_and_target_network() -> None:
    config = DQNConfig(batch_size=2, replay_warmup=2, target_update_steps=1, epsilon_decay=0.5)
    agent = DQNAgent(AdmissionEnvironment.state_size, 3, config, seed=7)
    state = np.zeros(AdmissionEnvironment.state_size, dtype=np.float32)
    next_state = np.ones(AdmissionEnvironment.state_size, dtype=np.float32) * 0.1
    before = agent.online.predict(state).copy()
    agent.remember(state, 0, 5.0, next_state, False)
    agent.remember(next_state, 1, -1.0, state, True)
    loss = agent.learn()
    assert loss is not None
    assert not np.allclose(before, agent.online.predict(state))
    assert np.allclose(agent.online.w1, agent.target.w1)
    assert agent.epsilon == pytest.approx(0.5)


def test_action_mask_prevents_capacity_violating_admission() -> None:
    agent = DQNAgent(
        AdmissionEnvironment.state_size,
        AdmissionEnvironment.action_size,
        DQNConfig(),
        seed=11,
    )
    agent.online.b2[:] = [100.0, 0.0, 1.0]
    state = np.zeros(AdmissionEnvironment.state_size, dtype=np.float32)
    action = agent.act(
        state,
        explore=False,
        action_mask=np.asarray([False, True, True]),
    )
    assert action == AdmissionAction.DEFER


def test_episode_generation_is_reproducible_and_sla_safe() -> None:
    first = generate_episode(99, request_count=12)
    assert first == generate_episode(99, request_count=12)
    service_floor = {"eMBB": 0, "uRLLC": 1, "mMTC": 0, "MC": 2}
    assert all(item.isolation_level >= service_floor[item.service] for item in first)


def test_invalid_action_is_rejected() -> None:
    environment = AdmissionEnvironment([request()])
    with pytest.raises(ValueError, match="invalid admission action"):
        environment.step(99)
