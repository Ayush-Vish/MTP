"""Learning-based admission control for SecGuard (Objective 2).

The module intentionally uses NumPy rather than a heavyweight deep-learning
runtime. It provides an auditable DQN with experience replay and a target
network, plus an environment that exposes the long-term admission trade-off:
accepting a request earns profit now but occupies resources needed later.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import asdict, dataclass, replace
from enum import IntEnum
import json
from pathlib import Path
from typing import Callable, Iterable, Sequence

import matplotlib.pyplot as plt
import numpy as np


class AdmissionAction(IntEnum):
    """Actions exposed to the admission agent."""

    ADMIT = 0
    REJECT = 1
    DEFER = 2


@dataclass(frozen=True)
class ResourceCapacity:
    """Aggregate capacity visible to the admission controller."""

    cpu: float = 100.0
    radio: float = 100.0
    bandwidth: float = 100.0

    def __post_init__(self) -> None:
        if min(self.cpu, self.radio, self.bandwidth) <= 0:
            raise ValueError("all resource capacities must be positive")

    def array(self) -> np.ndarray:
        return np.asarray((self.cpu, self.radio, self.bandwidth), dtype=float)


@dataclass(frozen=True)
class AdmissionRequest:
    """A security-adapted slice request presented to the RL controller."""

    request_id: str
    service: str
    cpu: float
    radio: float
    bandwidth: float
    revenue: float
    duration: int
    isolation_level: int
    risk_score: float
    deferred_count: int = 0

    def __post_init__(self) -> None:
        if min(self.cpu, self.radio, self.bandwidth) < 0:
            raise ValueError("resource demands cannot be negative")
        if self.revenue < 0:
            raise ValueError("revenue cannot be negative")
        if self.duration < 1:
            raise ValueError("duration must be at least one step")
        if self.isolation_level not in (0, 1, 2):
            raise ValueError("isolation_level must be 0, 1, or 2")
        if not 0.0 <= self.risk_score <= 1.0:
            raise ValueError("risk_score must be in [0, 1]")
        if self.deferred_count < 0:
            raise ValueError("deferred_count cannot be negative")

    def demand(self) -> np.ndarray:
        return np.asarray((self.cpu, self.radio, self.bandwidth), dtype=float)


@dataclass
class _ActiveRequest:
    request: AdmissionRequest
    release_at: int


@dataclass(frozen=True)
class AdmissionConfig:
    """Environment reward and normalization parameters."""

    discount: float = 0.97
    resource_cost: float = 0.15
    isolation_cost: float = 0.08
    exposure_cost: float = 0.25
    rejection_cost: float = 0.04
    deferral_cost: float = 0.02
    infeasible_cost: float = 0.20
    max_deferrals: int = 2
    revenue_scale: float = 120.0
    duration_scale: float = 12.0

    def __post_init__(self) -> None:
        if not 0.0 < self.discount <= 1.0:
            raise ValueError("discount must be in (0, 1]")
        if self.max_deferrals < 0:
            raise ValueError("max_deferrals cannot be negative")
        if self.revenue_scale <= 0 or self.duration_scale <= 0:
            raise ValueError("normalization scales must be positive")


class AdmissionEnvironment:
    """Finite-horizon SecGuard slice-admission environment.

    State is ``[resource loads (3), active fraction, mean remaining lifetime,
    request demands (3), revenue, duration, isolation, risk, defer fraction,
    horizon fraction]``. Remaining lifetime makes deferral decisions Markovian:
    the same utilization can represent resources releasing soon or much later.
    """

    state_size = 14
    action_size = len(AdmissionAction)

    def __init__(
        self,
        requests: Sequence[AdmissionRequest],
        capacity: ResourceCapacity = ResourceCapacity(),
        config: AdmissionConfig = AdmissionConfig(),
    ) -> None:
        if not requests:
            raise ValueError("an episode requires at least one request")
        self._initial_requests = list(requests)
        self.capacity = capacity
        self.config = config
        self.reset()

    def reset(self) -> np.ndarray:
        self.pending: deque[AdmissionRequest] = deque(self._initial_requests)
        self.active: list[_ActiveRequest] = []
        self.time = 0
        self.done = False
        self.total_reward = 0.0
        self.raw_profit = 0.0
        self.security_cost = 0.0
        self.admitted = 0
        self.rejected = 0
        self.deferred = 0
        self.infeasible = 0
        self.action_counts = {action.name.lower(): 0 for action in AdmissionAction}
        self.current = self.pending.popleft()
        return self._state()

    @property
    def used(self) -> np.ndarray:
        if not self.active:
            return np.zeros(3, dtype=float)
        return np.sum([item.request.demand() for item in self.active], axis=0)

    def feasible(self, request: AdmissionRequest | None = None) -> bool:
        candidate = self.current if request is None else request
        return bool(np.all(self.used + candidate.demand() <= self.capacity.array() + 1e-9))

    def valid_action_mask(self) -> np.ndarray:
        """Return actions allowed by capacity and the bounded defer contract."""

        return np.asarray(
            [
                self.feasible(),
                True,
                self.current.deferred_count < self.config.max_deferrals,
            ],
            dtype=bool,
        )

    def _state(self) -> np.ndarray:
        request = self.current
        capacity = self.capacity.array()
        load = np.clip(self.used / capacity, 0.0, 1.0)
        request_load = np.clip(request.demand() / capacity, 0.0, 1.0)
        active_fraction = min(len(self.active) / len(self._initial_requests), 1.0)
        mean_remaining_lifetime = (
            min(
                float(np.mean([item.release_at - self.time for item in self.active]))
                / self.config.duration_scale,
                1.0,
            )
            if self.active
            else 0.0
        )
        horizon_fraction = min((len(self.pending) + 1) / len(self._initial_requests), 1.0)
        return np.asarray(
            [
                *load,
                active_fraction,
                mean_remaining_lifetime,
                *request_load,
                min(request.revenue / self.config.revenue_scale, 1.0),
                min(request.duration / self.config.duration_scale, 1.0),
                request.isolation_level / 2.0,
                request.risk_score,
                min(request.deferred_count / max(self.config.max_deferrals, 1), 1.0),
                horizon_fraction,
            ],
            dtype=np.float32,
        )

    def _admission_reward(self, request: AdmissionRequest) -> tuple[float, float, float]:
        demand_fraction = float(np.mean(request.demand() / self.capacity.array()))
        resource_charge = self.config.resource_cost * request.revenue * demand_fraction
        isolation_charge = (
            self.config.isolation_cost * request.revenue * request.isolation_level / 2.0
        )
        sharing_factor = (1.0, 0.5, 0.0)[request.isolation_level]
        security_charge = (
            self.config.exposure_cost * request.revenue * request.risk_score * sharing_factor
        )
        raw_profit = request.revenue - resource_charge - isolation_charge
        return raw_profit - security_charge, raw_profit, security_charge

    def _advance_time(self) -> None:
        self.time += 1
        self.active = [item for item in self.active if item.release_at > self.time]

    def step(self, action: int | AdmissionAction) -> tuple[np.ndarray, float, bool, dict]:
        if self.done:
            raise RuntimeError("step() called after the episode finished")
        try:
            selected = AdmissionAction(int(action))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid admission action: {action}") from exc

        request = self.current
        self.action_counts[selected.name.lower()] += 1
        reward = 0.0
        outcome = selected.name.lower()
        if selected is AdmissionAction.ADMIT:
            if self.feasible(request):
                reward, profit, security_cost = self._admission_reward(request)
                self.raw_profit += profit
                self.security_cost += security_cost
                self.admitted += 1
                self.active.append(_ActiveRequest(request, self.time + request.duration))
            else:
                reward = -self.config.infeasible_cost * max(request.revenue, 1.0)
                self.rejected += 1
                self.infeasible += 1
                outcome = "infeasible"
        elif selected is AdmissionAction.REJECT:
            reward = -self.config.rejection_cost * request.revenue
            self.rejected += 1
        elif request.deferred_count < self.config.max_deferrals:
            reward = -self.config.deferral_cost * request.revenue
            self.pending.append(replace(request, deferred_count=request.deferred_count + 1))
            self.deferred += 1
        else:
            reward = -self.config.rejection_cost * request.revenue
            self.rejected += 1
            outcome = "defer_limit_rejected"

        self.total_reward += reward
        self._advance_time()
        if self.pending:
            self.current = self.pending.popleft()
            next_state = self._state()
        else:
            self.done = True
            next_state = np.zeros(self.state_size, dtype=np.float32)

        info = {
            "request_id": request.request_id,
            "action": selected.name.lower(),
            "outcome": outcome,
            "feasible": outcome != "infeasible",
            "raw_profit": self.raw_profit,
            "security_cost": self.security_cost,
            "resource_load": (self.used / self.capacity.array()).tolist(),
        }
        return next_state, float(reward), self.done, info

    def summary(self) -> dict:
        return {
            "reward": float(self.total_reward),
            "raw_profit": float(self.raw_profit),
            "security_cost": float(self.security_cost),
            "security_adjusted_profit": float(self.raw_profit - self.security_cost),
            "admitted": self.admitted,
            "rejected": self.rejected,
            "deferred": self.deferred,
            "infeasible": self.infeasible,
            "actions": dict(self.action_counts),
            "steps": self.time,
        }


class ReplayBuffer:
    """Fixed-size replay memory with deterministic sampling."""

    def __init__(self, capacity: int, seed: int = 42) -> None:
        if capacity < 1:
            raise ValueError("replay capacity must be positive")
        self.data: deque[
            tuple[np.ndarray, int, float, np.ndarray, bool, np.ndarray]
        ] = deque(
            maxlen=capacity
        )
        self.rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return len(self.data)

    def append(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
        next_action_mask: np.ndarray,
    ) -> None:
        self.data.append(
            (
                state.copy(),
                int(action),
                float(reward),
                next_state.copy(),
                bool(done),
                next_action_mask.copy(),
            )
        )

    def sample(self, size: int) -> tuple[np.ndarray, ...]:
        if size > len(self.data):
            raise ValueError("cannot sample more transitions than replay contains")
        indices = self.rng.choice(len(self.data), size=size, replace=False)
        rows = [self.data[int(index)] for index in indices]
        states, actions, rewards, next_states, dones, next_action_masks = zip(*rows)
        return (
            np.asarray(states, dtype=np.float32),
            np.asarray(actions, dtype=np.int64),
            np.asarray(rewards, dtype=np.float32),
            np.asarray(next_states, dtype=np.float32),
            np.asarray(dones, dtype=bool),
            np.asarray(next_action_masks, dtype=bool),
        )


class QNetwork:
    """Two-layer fully connected Q-network trained with Huber loss."""

    def __init__(self, state_size: int, action_size: int, hidden_size: int, seed: int) -> None:
        rng = np.random.default_rng(seed)
        self.w1 = rng.normal(0.0, np.sqrt(2 / state_size), (state_size, hidden_size))
        self.b1 = np.zeros(hidden_size, dtype=float)
        self.w2 = rng.normal(0.0, np.sqrt(2 / hidden_size), (hidden_size, action_size))
        self.b2 = np.zeros(action_size, dtype=float)

    def predict(self, states: np.ndarray) -> np.ndarray:
        states = np.atleast_2d(states).astype(float)
        hidden = np.maximum(states @ self.w1 + self.b1, 0.0)
        return hidden @ self.w2 + self.b2

    def train(self, states: np.ndarray, targets: np.ndarray, learning_rate: float) -> float:
        hidden_linear = states @ self.w1 + self.b1
        hidden = np.maximum(hidden_linear, 0.0)
        predictions = hidden @ self.w2 + self.b2
        error = predictions - targets
        absolute = np.abs(error)
        loss = np.where(absolute <= 1.0, 0.5 * error**2, absolute - 0.5).mean()
        gradient = np.where(absolute <= 1.0, error, np.sign(error)) / error.size
        grad_w2 = hidden.T @ gradient
        grad_b2 = gradient.sum(axis=0)
        grad_hidden = (gradient @ self.w2.T) * (hidden_linear > 0)
        grad_w1 = states.T @ grad_hidden
        grad_b1 = grad_hidden.sum(axis=0)
        for grad in (grad_w1, grad_b1, grad_w2, grad_b2):
            np.clip(grad, -10.0, 10.0, out=grad)
        self.w1 -= learning_rate * grad_w1
        self.b1 -= learning_rate * grad_b1
        self.w2 -= learning_rate * grad_w2
        self.b2 -= learning_rate * grad_b2
        return float(loss)

    def copy_from(self, other: "QNetwork") -> None:
        for name in ("w1", "b1", "w2", "b2"):
            setattr(self, name, getattr(other, name).copy())


@dataclass(frozen=True)
class DQNConfig:
    hidden_size: int = 64
    learning_rate: float = 0.005
    batch_size: int = 32
    replay_capacity: int = 10_000
    replay_warmup: int = 64
    target_update_steps: int = 50
    epsilon_start: float = 1.0
    epsilon_end: float = 0.05
    epsilon_decay: float = 0.9997
    discount: float = 0.97


class DQNAgent:
    """DQN agent with replay memory, exploration, and a target network."""

    def __init__(self, state_size: int, action_size: int, config: DQNConfig, seed: int = 42):
        self.state_size = state_size
        self.action_size = action_size
        self.config = config
        self.rng = np.random.default_rng(seed)
        self.online = QNetwork(state_size, action_size, config.hidden_size, seed)
        self.target = QNetwork(state_size, action_size, config.hidden_size, seed + 1)
        self.target.copy_from(self.online)
        self.replay = ReplayBuffer(config.replay_capacity, seed + 2)
        self.epsilon = config.epsilon_start
        self.training_steps = 0

    def act(
        self,
        state: np.ndarray,
        explore: bool = True,
        action_mask: np.ndarray | None = None,
    ) -> int:
        mask = (
            np.ones(self.action_size, dtype=bool)
            if action_mask is None
            else np.asarray(action_mask, dtype=bool)
        )
        if mask.shape != (self.action_size,) or not mask.any():
            raise ValueError("action_mask must allow at least one action")
        allowed = np.flatnonzero(mask)
        if explore and self.rng.random() < self.epsilon:
            return int(self.rng.choice(allowed))
        values = self.online.predict(state)[0]
        values = np.where(mask, values, -np.inf)
        return int(np.argmax(values))

    def remember(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
        next_action_mask: np.ndarray | None = None,
    ) -> None:
        mask = (
            np.ones(self.action_size, dtype=bool)
            if next_action_mask is None
            else np.asarray(next_action_mask, dtype=bool)
        )
        self.replay.append(state, action, reward, next_state, done, mask)

    def learn(self) -> float | None:
        minimum = max(self.config.batch_size, self.config.replay_warmup)
        if len(self.replay) < minimum:
            return None
        states, actions, rewards, next_states, dones, next_action_masks = self.replay.sample(
            self.config.batch_size
        )
        targets = self.online.predict(states)
        next_predictions = self.target.predict(next_states)
        next_predictions = np.where(next_action_masks, next_predictions, -np.inf)
        next_values = next_predictions.max(axis=1)
        next_values[dones] = 0.0
        targets[np.arange(len(actions)), actions] = (
            rewards + self.config.discount * next_values
        )
        loss = self.online.train(states, targets, self.config.learning_rate)
        self.training_steps += 1
        if self.training_steps % self.config.target_update_steps == 0:
            self.target.copy_from(self.online)
        self.epsilon = max(
            self.config.epsilon_end, self.epsilon * self.config.epsilon_decay
        )
        return loss

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            w1=self.online.w1,
            b1=self.online.b1,
            w2=self.online.w2,
            b2=self.online.b2,
            state_size=self.state_size,
            action_size=self.action_size,
        )

    def load(self, path: Path) -> None:
        bundle = np.load(path)
        if int(bundle["state_size"]) != self.state_size or int(bundle["action_size"]) != self.action_size:
            raise ValueError("saved DQN dimensions do not match this agent")
        for name in ("w1", "b1", "w2", "b2"):
            setattr(self.online, name, bundle[name].copy())
        self.target.copy_from(self.online)


SERVICE_PROFILES = {
    "eMBB": (24.0, 18.0, 42.0, 48.0, 5, 0),
    "uRLLC": (32.0, 22.0, 18.0, 70.0, 4, 1),
    "mMTC": (12.0, 30.0, 10.0, 30.0, 7, 0),
    "MC": (45.0, 36.0, 48.0, 105.0, 6, 2),
}


def generate_episode(seed: int, request_count: int = 24) -> list[AdmissionRequest]:
    """Generate a repeatable trace based on four 5Guard service classes."""

    if request_count < 1:
        raise ValueError("request_count must be positive")
    rng = np.random.default_rng(seed)
    services = tuple(SERVICE_PROFILES)
    probabilities = np.asarray((0.32, 0.24, 0.28, 0.16))
    requests = []
    for index in range(request_count):
        service = str(rng.choice(services, p=probabilities))
        cpu, radio, bandwidth, revenue, duration, isolation = SERVICE_PROFILES[service]
        demand_noise = rng.uniform(0.80, 1.20, size=3)
        risk = float(rng.beta(1.4, 3.0))
        target_isolation = max(isolation, 2 if risk >= 0.75 else 1 if risk >= 0.40 else 0)
        requests.append(
            AdmissionRequest(
                request_id=f"episode-{seed}-{index}",
                service=service,
                cpu=cpu * demand_noise[0],
                radio=radio * demand_noise[1],
                bandwidth=bandwidth * demand_noise[2],
                revenue=revenue * float(rng.uniform(0.85, 1.20)),
                duration=max(1, int(round(duration * rng.uniform(0.75, 1.25)))),
                isolation_level=target_isolation,
                risk_score=risk,
            )
        )
    return requests


Policy = Callable[[AdmissionEnvironment, np.ndarray], int]


def greedy_policy(environment: AdmissionEnvironment, _state: np.ndarray) -> int:
    return int(AdmissionAction.ADMIT if environment.feasible() else AdmissionAction.REJECT)


def value_density_policy(environment: AdmissionEnvironment, _state: np.ndarray) -> int:
    request = environment.current
    if not environment.feasible():
        return int(
            AdmissionAction.DEFER
            if request.deferred_count < environment.config.max_deferrals
            else AdmissionAction.REJECT
        )
    demand = float(np.mean(request.demand() / environment.capacity.array()))
    adjusted_value = request.revenue * (1.0 - 0.5 * request.risk_score)
    return int(
        AdmissionAction.ADMIT
        if adjusted_value / max(demand * request.duration, 1e-6) >= 15.0
        else AdmissionAction.REJECT
    )


def run_episode(environment: AdmissionEnvironment, policy: Policy) -> dict:
    state = environment.reset()
    while not environment.done:
        action = policy(environment, state)
        state, _, _, _ = environment.step(action)
    return environment.summary()


def train_agent(
    episodes: int = 400,
    requests_per_episode: int = 24,
    seed: int = 42,
    capacity: ResourceCapacity = ResourceCapacity(),
    environment_config: AdmissionConfig = AdmissionConfig(),
    dqn_config: DQNConfig = DQNConfig(),
) -> tuple[DQNAgent, list[dict]]:
    if episodes < 1:
        raise ValueError("episodes must be positive")
    agent = DQNAgent(AdmissionEnvironment.state_size, AdmissionEnvironment.action_size, dqn_config, seed)
    history = []
    for episode in range(episodes):
        environment = AdmissionEnvironment(
            generate_episode(seed + episode, requests_per_episode), capacity, environment_config
        )
        state = environment.reset()
        losses = []
        while not environment.done:
            action = agent.act(state, explore=True, action_mask=environment.valid_action_mask())
            next_state, reward, done, _ = environment.step(action)
            # Scale rewards to the same approximate range as normalized state
            # features. The environment continues to report monetary units.
            agent.remember(
                state,
                action,
                reward / environment_config.revenue_scale,
                next_state,
                done,
                (
                    np.zeros(environment.action_size, dtype=bool)
                    if done
                    else environment.valid_action_mask()
                ),
            )
            loss = agent.learn()
            if loss is not None:
                losses.append(loss)
            state = next_state
        row = environment.summary()
        row.update(
            {
                "episode": episode,
                "epsilon": agent.epsilon,
                "mean_loss": float(np.mean(losses)) if losses else None,
            }
        )
        history.append(row)
    return agent, history


def _aggregate(rows: Sequence[dict]) -> dict:
    result = {"episodes": len(rows)}
    for key in (
        "reward",
        "raw_profit",
        "security_cost",
        "security_adjusted_profit",
        "admitted",
        "rejected",
        "deferred",
        "infeasible",
    ):
        values = np.asarray([row[key] for row in rows], dtype=float)
        margin = 0.0 if len(values) < 2 else 1.96 * values.std(ddof=1) / np.sqrt(len(values))
        result[key] = {
            "mean": float(values.mean()),
            "ci95_low": float(values.mean() - margin),
            "ci95_high": float(values.mean() + margin),
        }
    return result


def _paired_comparison(reference: Sequence[dict], proposed: Sequence[dict]) -> dict:
    """Summarize paired reward differences without assuming normality for wins."""

    differences = np.asarray(
        [new["reward"] - old["reward"] for old, new in zip(reference, proposed)],
        dtype=float,
    )
    margin = (
        0.0
        if len(differences) < 2
        else 1.96 * differences.std(ddof=1) / np.sqrt(len(differences))
    )
    return {
        "metric": "total_reward",
        "mean_delta": float(differences.mean()),
        "ci95_low": float(differences.mean() - margin),
        "ci95_high": float(differences.mean() + margin),
        "wins": int((differences > 0).sum()),
        "ties": int((differences == 0).sum()),
        "losses": int((differences < 0).sum()),
        "episodes": int(len(differences)),
    }


def evaluate_agent(
    agent: DQNAgent,
    seeds: Iterable[int],
    requests_per_episode: int = 24,
    capacity: ResourceCapacity = ResourceCapacity(),
    environment_config: AdmissionConfig = AdmissionConfig(),
) -> dict:
    policies: dict[str, Policy] = {
        "dqn": lambda environment, state: agent.act(
            state, explore=False, action_mask=environment.valid_action_mask()
        ),
        "greedy": greedy_policy,
        "value_density": value_density_policy,
    }
    rows = {name: [] for name in policies}
    for seed in seeds:
        requests = generate_episode(seed, requests_per_episode)
        for name, policy in policies.items():
            result = run_episode(AdmissionEnvironment(requests, capacity, environment_config), policy)
            result["seed"] = seed
            rows[name].append(result)
    return {
        "summaries": {name: _aggregate(values) for name, values in rows.items()},
        "paired_comparisons": {
            "dqn_vs_greedy": _paired_comparison(rows["greedy"], rows["dqn"]),
            "dqn_vs_value_density": _paired_comparison(
                rows["value_density"], rows["dqn"]
            ),
        },
        "per_episode": rows,
    }


def _save_plot(history: Sequence[dict], evaluation: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    training_rewards = np.asarray([row["reward"] for row in history], dtype=float)
    window = min(25, len(training_rewards))
    moving = np.convolve(training_rewards, np.ones(window) / window, mode="valid")
    names = list(evaluation["summaries"])
    policy_rewards = [evaluation["summaries"][name]["reward"]["mean"] for name in names]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].plot(
        np.arange(window - 1, len(training_rewards)), moving, color="#1f77b4"
    )
    axes[0].set(title=f"DQN training reward ({window}-episode mean)", xlabel="Episode", ylabel="Reward")
    bars = axes[1].bar(
        names, policy_rewards, color=("#1f77b4", "#777777", "#2ca02c")
    )
    axes[1].bar_label(bars, fmt="%.1f", padding=3)
    axes[1].set(title="Held-out admission policies", ylabel="Total reward")
    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run_objective2(
    output_file: Path,
    model_file: Path,
    episodes: int = 2_000,
    evaluation_episodes: int = 50,
    requests_per_episode: int = 24,
    seed: int = 42,
) -> dict:
    agent, history = train_agent(episodes, requests_per_episode, seed)
    evaluation = evaluate_agent(
        agent,
        range(seed + 10_000, seed + 10_000 + evaluation_episodes),
        requests_per_episode,
    )
    agent.save(model_file)
    plot_file = output_file.with_name("objective2_admission_control.png")
    _save_plot(history, evaluation, plot_file)
    result = {
        "objective": "Objective 2: Learning-Based Admission Control",
        "method": "NumPy DQN with replay memory and target network",
        "actions": [action.name.lower() for action in AdmissionAction],
        "state_features": [
            "cpu_load", "radio_load", "bandwidth_load", "active_fraction",
            "mean_remaining_lifetime",
            "request_cpu", "request_radio", "request_bandwidth", "revenue",
            "duration", "isolation_level", "risk_score", "defer_fraction",
            "horizon_fraction",
        ],
        "training": {
            "episodes": episodes,
            "requests_per_episode": requests_per_episode,
            "seed": seed,
            "final_epsilon": agent.epsilon,
            "last_25_mean_reward": float(
                np.mean([row["reward"] for row in history[-min(25, len(history)) :]])
            ),
        },
        "evaluation": evaluation,
        "config": {
            "environment": asdict(AdmissionConfig()),
            "dqn": asdict(DQNConfig()),
            "capacity": asdict(ResourceCapacity()),
        },
        "artifacts": {"model": str(model_file), "plot": str(plot_file)},
        "limitations": [
            "The environment is calibrated to 5Guard service classes but does not call the MILP at every RL step.",
            "Reported results are synthetic held-out trace results, not production-network validation.",
            "The security term is an isolation-exposure proxy rather than measured attack propagation.",
        ],
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for name, summary in evaluation["summaries"].items():
        print(
            f"{name:<14} reward="
            f"{summary['reward']['mean']:.2f} "
            f"admitted={summary['admitted']['mean']:.2f}"
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=2_000)
    parser.add_argument("--evaluation-episodes", type=int, default=50)
    parser.add_argument("--requests", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output-file", type=Path, default=Path("artifacts/objective2_admission_control.json")
    )
    parser.add_argument(
        "--model-file", type=Path, default=Path("artifacts/objective2_dqn.npz")
    )
    args = parser.parse_args()
    run_objective2(
        args.output_file,
        args.model_file,
        args.episodes,
        args.evaluation_episodes,
        args.requests,
        args.seed,
    )


if __name__ == "__main__":
    main()
