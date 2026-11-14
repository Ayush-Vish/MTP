"""Performance-based 5Guard selection with isolated, causal solver replay.

Candidates are cold-rebuilt from copies of a common request/allocation state.
This is a controlled FGR-style sequential reference, not the upstream cached
FGR implementation or a concurrent production ensemble. No legacy artifacts
are overwritten. Train/validation/test seeds are disjoint.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
from dataclasses import dataclass, field
import importlib
import inspect
import json
import os
from pathlib import Path
import random
import re
import shutil
import tempfile
import time
from typing import Any

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor, RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from secguard.algorithm_selector import ALGORITHMS, choose_oracle, quality_retention


@dataclass
class ReplayState:
    requests: list = field(default_factory=list)
    x: list = field(default_factory=list)
    y: list = field(default_factory=list)
    profit: float = 0.0
    previous_seconds: float = 0.0


def cold_solver(module: Any, algorithm: str):
    """Adapt upstream incremental construction for an empty model.

    Existing request variables are created before upstream computes R_miss,
    hiding the fact that their constraints are missing after a cold rebuild.
    Mark every request as missing and create shared auxiliary variables based
    on model contents. Fail closed if the expected pinned source has changed.
    """
    source = inspect.getsource(getattr(module, f"{algorithm}_iter"))
    original = 'R_miss = [idx_r for idx_r, r in enumerate(reqs) if m.getVarByName(f"c_{idx_r}_{0}_{0}") is None]'
    if source.count(original) != 1:
        raise ValueError(f"Unsupported {algorithm} source: missing incremental constraint marker")
    source = source.replace(original, "R_miss = list(range(len(reqs)))")
    if algorithm == "opt":
        # Preserve the existing local SCIP numerical-reporting correction when
        # replay is run against a fresh upstream checkout as well.
        for index in (1, 2, 3):
            pattern = rf"g_B_{index}_opt = sum\(r\.rho_B \* h_B_h_{index}\[idx_r\]\[idx_e\][\s\S]*?\n\s*\)"
            def clamp(match):
                block = match.group(0).replace("= sum(", "= max(0.0, sum(", 1)
                block = block.replace(f"h_B_h_{index}[idx_r][idx_e]", f"max(0.0, h_B_h_{index}[idx_r][idx_e])", 1)
                return block + ")"
            source = re.sub(pattern, clamp, source)
        source = source.replace(
            "g_vio_opt = g_D_opt + g_C_opt + g_K_opt + g_B_1_opt + g_B_2_opt + g_B_3_opt",
            "g_vio_opt = max(0.0, g_D_opt) + max(0.0, g_C_opt) + max(0.0, g_K_opt) + g_B_1_opt + g_B_2_opt + g_B_3_opt",
        )
    if algorithm in ("dtr", "rnr"):
        original = "if len(R_t) == 0:"
        if source.count(original) != 1:
            raise ValueError(f"Unsupported {algorithm} auxiliary-variable initialization")
        source = source.replace(original, 'if m.getVarByName("a_x2_0_0") is None:')
    namespace = dict(vars(module))
    exec(compile(source, f"<secguard_cold_{algorithm}>", "exec"), namespace)
    return namespace[f"{algorithm}_iter"]


def state_features(request: Any, state: ReplayState, topology: tuple) -> dict[str, float]:
    """Use actual requests, placements, and capacities; never current outcomes."""
    servers, radios, paths, _, links, _ = topology
    cpu = np.zeros(len(servers))
    radio = np.zeros(len(radios))
    # X/Y encode mappings; demand occupancy excludes orchestration overhead.
    for i, active in enumerate(state.requests):
        for j, vnf in enumerate(active.V_S):
            if i < len(state.x) and j < len(state.x[i]):
                cpu += np.asarray(state.x[i][j], dtype=float) * vnf.C_REQ
        for j, unit in enumerate(active.V_R):
            if i < len(state.y) and j < len(state.y[i]):
                assignments = np.asarray(state.y[i][j], dtype=float)
                radio += assignments.sum(axis=tuple(range(1, assignments.ndim))) * unit.K_REQ
    cpu_capacity = np.asarray([p.C_MAX for p in servers], dtype=float)
    radio_capacity = np.asarray([sum(q.Pi_MAX) for q in radios], dtype=float)
    cpu_remaining = np.maximum(cpu_capacity - cpu, 0)
    radio_remaining = np.maximum(radio_capacity - radio, 0)
    request_cpu = sum(v.C_REQ for v in request.V_S)
    request_radio = sum(w.K_REQ for w in request.V_R)
    request_bandwidth = sum(e.B_REQ for e in request.E)
    total_bandwidth = sum(sum(link.B_MAX) for link in links)
    return {
        "active_slices": len(state.requests),
        "previous_profit": state.profit,
        "previous_seconds": state.previous_seconds,
        "isolation": request.gamma,
        "sub_isolation": request.kappa,
        "revenue": request.R,
        "deadline": request.timeout,
        "vnfs": len(request.V_S),
        "vnf_instances": sum(v.Xi_REQ for v in request.V_S),
        "radio_units": len(request.V_R),
        "virtual_links": len(request.E),
        "cpu_demand": request_cpu,
        "radio_demand": request_radio,
        "bandwidth_demand_log": float(np.log1p(request_bandwidth)),
        "min_path_delay": min((e.D_REQ for e in request.E), default=0),
        "migration_penalty": request.beta,
        "physical_servers": len(servers),
        "physical_radios": len(radios),
        "physical_paths": len(paths),
        "cpu_load_proxy": float(cpu.sum() / max(cpu_capacity.sum(), 1)),
        "radio_load_proxy": float(radio.sum() / max(radio_capacity.sum(), 1)),
        "cpu_remaining": float(cpu_remaining.sum()),
        "radio_remaining": float(radio_remaining.sum()),
        "cpu_fragmentation": float(cpu_remaining.std() / max(cpu_remaining.mean(), 1)),
        "eligible_servers_proxy": int(np.sum(cpu_remaining >= request_cpu)),
        "eligible_radios_proxy": int(np.sum(radio_remaining >= request_radio)),
        "active_bandwidth_demand_fraction": sum(e.B_REQ for r in state.requests for e in r.E) / max(total_bandwidth, 1),
    }


def fgr_choice(outcomes: dict[str, dict]) -> str:
    """Mirror upstream priority: non-timeout OPT, else best non-timeout profit."""
    if not outcomes["opt"]["timeout"] and not outcomes["opt"].get("error"):
        return "opt"
    available = [a for a in ALGORITHMS if not outcomes[a]["timeout"] and not outcomes[a].get("error")]
    return max(available, key=lambda a: round(outcomes[a]["profit"], 4)) if available else "opt"


class FiveGuardReplay:
    def __init__(self, external_dir: Path, work_dir: Path, solver_seconds: float = 2.0):
        import sys
        from secguard import solver_compat
        self.external_dir = external_dir.resolve()
        sys.path.insert(0, str(self.external_dir))
        os.environ["FIVEGUARD_SOLVER"] = "scip"
        # Also support upstream libraries.py, which imports gurobipy directly.
        # The adapter is tracked in SecGuard, not an ignored external file.
        sys.modules["gurobipy_scip"] = solver_compat
        sys.modules["gurobipy"] = solver_compat
        self.work_dir = work_dir
        (work_dir / "saved_model").mkdir(parents=True, exist_ok=True)
        (work_dir / "dataset").mkdir(exist_ok=True)
        shutil.copy2(self.external_dir / "dataset/brain.xml", work_dir / "dataset/brain.xml")
        self.lib = importlib.import_module("libraries")
        # Runtime-only adaptation: set identical limits for every solver call.
        original_read = self.lib.gp.read
        def read_with_limit(path):
            model = original_read(path)
            model.setParam("TimeLimit", solver_seconds)
            return model
        self.lib.gp.read = read_with_limit
        self.functions = {}
        for a in ALGORITHMS:
            module = importlib.import_module(f"algorithms.{a}")
            module.THREADS = 1
            self.functions[a] = cold_solver(module, a)
        self.template = work_dir / "empty.mps"
        self.lib.gp.Model("replay_empty").write(str(self.template))

    def topology(self, name: str) -> tuple:
        with contextlib.chdir(self.work_dir):
            return self.lib.init_setup_brain() if name == "brain" else self.lib.init_setup_synth()

    def requests(self, seed: int, count: int, load: float = 1.0) -> list:
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
            profiles = self.lib.create_sr_resources()
        rng = np.random.default_rng(seed)
        # Vary class mix and actual resource demands across complete sequences.
        mixture = rng.dirichlet(np.asarray([7.0, 1.5, 1.0, 0.5]))
        sequence = []
        for _ in range(count):
            request = copy.deepcopy(profiles[int(rng.choice(4, p=mixture))])
            factor = load * rng.uniform(0.85, 1.15)
            for v in request.V_S:
                v.C_REQ *= factor
            for edge in request.E:
                edge.B_REQ *= factor
            request.R *= float(rng.uniform(0.9, 1.1))
            sequence.append(request)
        return sequence

    def candidate(self, algorithm: str, state: ReplayState, request: Any, topology: tuple, seed: int, step: int) -> tuple[dict, ReplayState]:
        wall_start, cpu_start = time.perf_counter(), time.process_time()
        with contextlib.chdir(self.work_dir):
            path = self.work_dir / f"saved_model/model_backup_{algorithm}_0.mps"
            shutil.copyfile(self.template, path)
            # Preserve identity links between VNFs and virtual edges while
            # preventing any mutation leaking between candidate branches.
            r, active, x, y, physical = copy.deepcopy((request, state.requests, state.x, state.y, topology))
            np.random.seed(seed * 1009 + step)
            random.seed(seed * 1009 + step)
            error = None
            try:
                args = (state.profit, 0, step, r, active, *physical, 0, x, y)
                if algorithm == "dtr":
                    result, x, y = self.functions[algorithm](0.6, *args)
                else:
                    result, x, y = self.functions[algorithm](*args)
                if bool(result[8]):
                    revenue_bound = sum(item.R for item in result[10])
                    if not np.isfinite(float(result[0])) or float(result[0]) > revenue_bound + 1e-5 * max(revenue_bound, 1):
                        raise ValueError("Solver profit exceeds total admitted revenue")
                    if len(result[10]) != len(state.requests) + 1:
                        raise ValueError("Feasible result did not retain the existing request set")
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                result = [state.profit, None, None, None, None, None, None, 0.0, 0, 1, state.requests]
        elapsed = time.perf_counter() - wall_start
        cpu = time.process_time() - cpu_start
        accepted = bool(result[8]) and not bool(result[9]) and elapsed <= request.timeout and error is None
        next_state = (
            ReplayState(result[10], x, y, float(result[0]), elapsed)
            if accepted else copy.deepcopy(state)
        )
        next_state.previous_seconds = elapsed
        row = {
            "profit": float(result[0]) if accepted else state.profit,
            "incremental_profit": float(result[0]) - state.profit if accepted else 0.0,
            "wall_seconds": elapsed, "cpu_seconds": cpu,
            "reported_seconds": float(result[7]),
            "feasible": accepted, "timeout": bool(result[9]) or elapsed > request.timeout,
            "error": error,
        }
        return row, next_state


class PerformanceSelector:
    """Jointly predict log-runtime, incremental profit, and completion success."""
    def fit(self, rows: list[dict]) -> "PerformanceSelector":
        self.feature_names = list(rows[0]["features"])
        x = np.asarray([[r["features"][k] for k in self.feature_names] for r in rows])
        targets = []
        for r in rows:
            targets.append([
                item for a in ALGORITHMS for item in (
                    np.log1p(r["outcomes"][a]["wall_seconds"]),
                    r["outcomes"][a]["incremental_profit"],
                    float(r["outcomes"][a]["feasible"]),
                )
            ])
        self.model = ExtraTreesRegressor(n_estimators=128, min_samples_leaf=2, random_state=42, n_jobs=1)
        self.model.fit(x, targets)
        self.quality_floor = 0.95
        self.feasibility_floor = 0.75
        self.calibrators = {}
        return self

    def calibrate(self, rows: list[dict]) -> dict:
        """Fit sigmoid completion-score calibration on held-out validation rows."""
        raw = [self.predictions(row["features"]) for row in rows]
        status = {}
        for a in ALGORITHMS:
            target = [int(row["outcomes"][a]["feasible"]) for row in rows]
            if len(set(target)) < 2:
                status[a] = "unavailable: calibration rows have only one outcome class"
                continue
            calibration = LogisticRegression(random_state=42)
            calibration.fit([[prediction[a]["success"]] for prediction in raw], target)
            self.calibrators[a] = calibration
            status[a] = "sigmoid fitted on calibration seed groups"
        return status

    def predictions(self, features: dict) -> dict[str, dict]:
        vector = np.asarray([[features[k] for k in self.feature_names]])
        values = self.model.predict(vector)[0].reshape(4, 3)
        result = {
            a: {"seconds": max(float(np.expm1(v[0])), 1e-6), "gain": float(v[1]), "success": float(np.clip(v[2], 0, 1))}
            for a, v in zip(ALGORITHMS, values)
        }
        for a, calibration in self.calibrators.items():
            result[a]["success"] = float(calibration.predict_proba([[result[a]["success"]]])[0, 1])
        return result

    def rank(self, features: dict) -> list[str]:
        predictions = self.predictions(features)
        feasible = [a for a in ALGORITHMS if predictions[a]["success"] >= self.feasibility_floor and predictions[a]["seconds"] <= features["deadline"]]
        if not feasible:
            return sorted(ALGORITHMS, key=lambda a: (-predictions[a]["success"], predictions[a]["seconds"]))
        # Match the oracle's total-profit loss budget. Applying the percentage
        # to incremental gain alone over-penalizes tiny marginal differences.
        best_profit = features.get("previous_profit", 0.0) + max(predictions[a]["gain"] for a in feasible)
        qualified = [a for a in feasible if best_profit - (features.get("previous_profit", 0.0) + predictions[a]["gain"]) <= (1-self.quality_floor)*max(abs(best_profit), 1)]
        first = sorted(qualified, key=lambda a: predictions[a]["seconds"])
        return first + sorted((a for a in ALGORITHMS if a not in first), key=lambda a: (-predictions[a]["success"], predictions[a]["seconds"]))


def oracle_label(outcomes: dict[str, dict]) -> str:
    feasible = {a: outcomes[a]["feasible"] for a in ALGORITHMS}
    if not any(feasible.values()):
        return "none"
    return choose_oracle(
        {a: outcomes[a]["profit"] for a in ALGORITHMS},
        {a: outcomes[a]["wall_seconds"] for a in ALGORITHMS}, feasible, 0.95,
    )[0]


def collect_rows(runner: FiveGuardReplay, seeds: list[int], steps: int, topology_name: str) -> list[dict]:
    rows = []
    for seed in seeds:
        topology = runner.topology(topology_name)
        state = ReplayState()
        sequence = runner.requests(seed, steps)
        rng = np.random.default_rng(seed)
        for step, request in enumerate(sequence):
            features = state_features(request, state, topology)
            outcomes, states = {}, {}
            with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
                for a in rng.permutation(ALGORITHMS):
                    outcomes[a], states[a] = runner.candidate(a, state, request, topology, seed, step)
            label = oracle_label(outcomes)
            rows.append({"seed": seed, "step": step, "topology": topology_name, "features": features, "outcomes": outcomes, "oracle": label})
            # Different behavior policies expose training to varied causal states.
            choices = [a for a in ALGORITHMS if outcomes[a]["feasible"]]
            behavior = fgr_choice(outcomes) if seed % 2 == 0 else str(rng.choice(choices)) if choices else "opt"
            state = states[behavior]
        errors = sum(bool(r["outcomes"][a]["error"]) for r in rows if r["seed"] == seed for a in ALGORITHMS)
        print(f"Collected {topology_name} seed {seed}: {steps} common-state rows; errors={errors}", flush=True)
    return rows


def tune_selector(model: PerformanceSelector, validation_rows: list[dict]) -> list[dict]:
    profiles = []
    predictions = [model.predictions(r["features"]) for r in validation_rows]
    # Cache tree inference; grid selection uses validation outcomes only.
    original = model.predictions
    for quality in (0.90, 0.95, 0.98, 1.0):
        for feasibility in (0.5, 0.75, 0.9):
            model.quality_floor, model.feasibility_floor = quality, feasibility
            selected = []
            for row, prediction in zip(validation_rows, predictions):
                model.predictions = lambda _features, values=prediction: values
                selected.append(model.rank(row["features"])[0])
            model.predictions = original
            qualities, seconds, success = [], [], []
            for row, a in zip(validation_rows, selected):
                feasible_profits = [r["profit"] for r in row["outcomes"].values() if r["feasible"]]
                best = max(feasible_profits, default=0.0)
                item = row["outcomes"][a]
                qualities.append(quality_retention(item["profit"], best, item["feasible"]))
                seconds.append(item["wall_seconds"])
                success.append(item["feasible"])
            profiles.append({"quality_floor": quality, "feasibility_floor": feasibility, "mean_quality": float(np.mean(qualities)), "success_rate": float(np.mean(success)), "mean_seconds": float(np.mean(seconds))})
    qualified = [p for p in profiles if p["mean_quality"] >= 0.95 and p["success_rate"] >= 0.95]
    best = min(qualified, key=lambda p: p["mean_seconds"]) if qualified else max(profiles, key=lambda p: (p["mean_quality"], -p["mean_seconds"]))
    model.quality_floor, model.feasibility_floor = best["quality_floor"], best["feasibility_floor"]
    return profiles


def evaluate_online(runner: FiveGuardReplay, model: PerformanceSelector, classifier: Any, seeds: list[int], steps: int, topology_name: str) -> list[dict]:
    rows = []
    policies = ("performance_selector", "rf_opt_fallback", "fgr_sequential", "always_iar", "always_opt")
    for seed in seeds:
        sequence = runner.requests(seed, steps)
        # Rotate execution order across seeds to reduce warm-up/order bias.
        for policy in np.random.default_rng(seed).permutation(policies):
            state, topology = ReplayState(), runner.topology(topology_name)
            for step, request in enumerate(sequence):
                start_wall, start_cpu = time.perf_counter(), time.process_time()
                features = state_features(request, state, topology)
                inference_start = time.perf_counter()
                if policy == "performance_selector":
                    ranking = model.rank(features)
                elif policy == "rf_opt_fallback":
                    probabilities = classifier.predict_proba([[features[k] for k in model.feature_names]])[0]
                    predicted = str(classifier.classes_[int(np.argmax(probabilities))])
                    ranking = [predicted if max(probabilities) >= 0.45 else "opt"]
                elif policy == "fgr_sequential":
                    ranking = list(ALGORITHMS)
                else:
                    ranking = [policy.replace("always_", "")]
                inference = time.perf_counter() - inference_start
                outcomes, states = {}, {}
                with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
                    if policy == "fgr_sequential":
                        for a in ranking:
                            outcomes[a], states[a] = runner.candidate(a, state, request, topology, seed, step)
                        selected = fgr_choice(outcomes)
                    else:
                        selected = ranking[0]
                        outcomes[selected], states[selected] = runner.candidate(selected, state, request, topology, seed, step)
                        # At most one retry, only with enough predicted remaining budget.
                        if policy == "performance_selector" and not outcomes[selected]["feasible"]:
                            prediction = model.predictions(features)
                            remaining = request.timeout - (time.perf_counter() - start_wall)
                            for candidate in ranking[1:]:
                                if prediction[candidate]["seconds"] * 1.2 < remaining:
                                    outcomes[candidate], states[candidate] = runner.candidate(candidate, state, request, topology, seed, step)
                                    if outcomes[candidate]["feasible"]:
                                        selected = candidate
                                    break
                elapsed = time.perf_counter() - start_wall
                cpu = time.process_time() - start_cpu
                accepted = outcomes[selected]["feasible"] and elapsed <= request.timeout
                if accepted:
                    state = states[selected]
                state.previous_seconds = elapsed
                rows.append({"seed": seed, "step": step, "policy": str(policy), "topology": topology_name, "selected": selected, "accepted": bool(accepted), "profit": state.profit, "wall_seconds": elapsed, "cpu_seconds": cpu, "inference_seconds": inference, "solver_calls": len(outcomes), "deadline": request.timeout, "outcomes": outcomes})
            print(f"Replayed {topology_name} seed {seed} {policy}: profit={state.profit:.2f}", flush=True)
    return rows


def summarize(rows: list[dict]) -> dict:
    result = {}
    for policy in sorted({r["policy"] for r in rows}):
        selected = [r for r in rows if r["policy"] == policy]
        seeds = sorted({r["seed"] for r in selected})
        final_profits = [max((r for r in selected if r["seed"] == s), key=lambda r: r["step"])["profit"] for s in seeds]
        result[policy] = {
            "decisions": len(selected), "mean_wall_seconds": float(np.mean([r["wall_seconds"] for r in selected])),
            "p95_wall_seconds": float(np.quantile([r["wall_seconds"] for r in selected], 0.95)),
            "mean_cpu_seconds": float(np.mean([r["cpu_seconds"] for r in selected])),
            "mean_solver_calls": float(np.mean([r["solver_calls"] for r in selected])),
            "admission_deadline_success_rate": float(np.mean([r["accepted"] for r in selected])),
            "mean_final_profit": float(np.mean(final_profits)),
            "per_seed_final_profit": dict(zip(map(str, seeds), final_profits)),
            "solver_errors": sum(bool(o["error"]) for r in selected for o in r["outcomes"].values()),
        }
    return result


def common_state_audit(rows: list[dict], model: PerformanceSelector, classifier: Any) -> dict:
    """Score both learned selectors against exactly the same held-out branches."""
    report = {}
    for name in ("performance_selector", "rf_opt_fallback", "fgr_style"):
        exact, qualities, successes, times = [], [], [], []
        for row in rows:
            if name == "performance_selector":
                choice = model.rank(row["features"])[0]
            elif name == "rf_opt_fallback":
                probabilities = classifier.predict_proba([[row["features"][k] for k in model.feature_names]])[0]
                choice = str(classifier.classes_[int(np.argmax(probabilities))]) if max(probabilities) >= 0.45 else "opt"
            else:
                choice = fgr_choice(row["outcomes"])
            item = row["outcomes"][choice]
            if row["oracle"] != "none":
                exact.append(choice == row["oracle"])
            profits = [o["profit"] for o in row["outcomes"].values() if o["feasible"]]
            qualities.append(quality_retention(item["profit"], max(profits, default=0), item["feasible"]))
            successes.append(item["feasible"])
            times.append(item["wall_seconds"])
        report[name] = {
            "oracle_label_accuracy": float(np.mean(exact)) if exact else None,
            "oracle_eligible_rows": len(exact),
            "all_rows": len(rows),
            "mean_quality_all_rows": float(np.mean(qualities)),
            "feasibility_all_rows": float(np.mean(successes)),
            "selected_solver_seconds": float(np.mean(times)),
        }
    return report


def save_figure(summaries: dict, path: Path) -> None:
    names = list(summaries)
    labels = {"performance_selector": "Performance\nselector", "rf_opt_fallback": "RF + OPT\nfallback", "fgr_sequential": "Sequential\nFGR-style", "always_iar": "Always IAR", "always_opt": "Always OPT"}
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8))
    for ax, metric, title in zip(axes, ("mean_wall_seconds", "mean_final_profit", "admission_deadline_success_rate"), ("Measured end-to-end seconds", "Mean final trajectory profit", "Admission within total deadline")):
        scale = 100 if metric == "admission_deadline_success_rate" else 1
        values = [scale*summaries[n][metric] for n in names]
        bars = ax.bar([labels[n] for n in names], values, color=["#278250" if n == "performance_selector" else "#657b96" for n in names])
        ax.bar_label(bars, fmt="%.2f%%" if scale==100 else "%.3f", fontsize=8, padding=3)
        ax.tick_params(axis="x", labelsize=8, rotation=15)
        ax.set_title(title)
        ax.set_ylim(0, max(values) * 1.2 + 1e-6)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Objective 3: causal cold-rebuild replay (SCIP, sequential reference)")
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fiveguard-dir", type=Path, default=Path("external/5guard"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/objective3_online"))
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument("--train-seeds", type=int, nargs="+", default=list(range(100, 106)))
    parser.add_argument("--validation-seeds", type=int, nargs="+", default=[200, 201])
    parser.add_argument("--test-seeds", type=int, nargs="+", default=[300, 301, 302, 303])
    parser.add_argument("--topology", choices=["synthetic", "brain"], default="synthetic")
    parser.add_argument("--solver-seconds", type=float, default=2.0)
    parser.add_argument("--audit-only", action="store_true", help="Load the completed model and audit held-out common-state branches")
    parser.add_argument("--reuse-data-dir", type=Path, help="Reuse only training and validation data from a matching experiment")
    args = parser.parse_args()
    splits = [set(args.train_seeds), set(args.validation_seeds), set(args.test_seeds)]
    if any(splits[i] & splits[j] for i in range(3) for j in range(i)):
        parser.error("train, validation, and test seeds must be disjoint")
    if args.steps < 1 or args.solver_seconds <= 0:
        parser.error("steps and solver-seconds must be positive")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="secguard_replay_") as temporary:
        runner = FiveGuardReplay(args.fiveguard_dir, Path(temporary), args.solver_seconds)
        if args.audit_only:
            result_path = output / "results.json"
            existing = json.loads(result_path.read_text(encoding="utf-8"))
            design = existing["design"]
            if args.steps != design["steps"] or args.topology != design["topology"] or args.test_seeds != design["test_seeds"]:
                parser.error("audit arguments must match the completed experiment")
            bundle = joblib.load(output / "selector.joblib")
            if "selector" in bundle:
                model, classifier = bundle["selector"], bundle["classifier"]
            else:
                model = PerformanceSelector()
                model.__dict__.update(bundle["selector_state"])
                classifier = bundle["classifier"]
            audit_rows = collect_rows(runner, design["test_seeds"], design["steps"], design["topology"])
            (output / "test_common_state.json").write_text(json.dumps(audit_rows, indent=2), encoding="utf-8")
            existing["common_state_audit"] = common_state_audit(audit_rows, model, classifier)
            existing["common_state_audit_design"] = "Separate held-out common-state branches; no retry; diagnostic solver calls excluded from online policy timing; model unchanged"
            result_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            joblib.dump({"selector_state": {k:v for k,v in vars(model).items() if k != "predictions"}, "classifier": classifier}, output / "selector.joblib")
            print(json.dumps(existing["common_state_audit"], indent=2))
            return
        if args.reuse_data_dir:
            training = json.loads((args.reuse_data_dir / "training.json").read_text(encoding="utf-8"))
            validation = json.loads((args.reuse_data_dir / "validation.json").read_text(encoding="utf-8"))
            for data, seeds in ((training, args.train_seeds), (validation, args.validation_seeds)):
                if {r["seed"] for r in data} != set(seeds) or any(r["topology"] != args.topology for r in data) or any(sum(r["seed"]==seed for r in data)!=args.steps for seed in seeds):
                    parser.error("reused training/validation data do not match requested design")
        else:
            training = collect_rows(runner, args.train_seeds, args.steps, args.topology)
            validation = collect_rows(runner, args.validation_seeds, args.steps, args.topology)
        (output / "training.json").write_text(json.dumps(training, indent=2), encoding="utf-8")
        (output / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
        model = PerformanceSelector().fit(training)
        calibration_seeds = set(args.validation_seeds[:max(1, len(args.validation_seeds)//2)])
        calibration_rows = [r for r in validation if r["seed"] in calibration_seeds]
        tuning_rows = [r for r in validation if r["seed"] not in calibration_seeds]
        if not tuning_rows:
            # Small smoke runs skip calibration to retain an independent tuning set.
            calibration_status = {a: "skipped: only one validation seed" for a in ALGORITHMS}
            tuning_rows = validation
        else:
            calibration_status = model.calibrate(calibration_rows)
        profiles = tune_selector(model, tuning_rows)
        valid_training = [r for r in training if r["oracle"] != "none"]
        classifier = RandomForestClassifier(n_estimators=128, max_depth=14, min_samples_leaf=2, random_state=42, n_jobs=1)
        classifier.fit([[r["features"][k] for k in model.feature_names] for r in valid_training], [r["oracle"] for r in valid_training])
        rows = evaluate_online(runner, model, classifier, args.test_seeds, args.steps, args.topology)
    summaries = summarize(rows)
    proposed = summaries["performance_selector"]
    comparisons = {}
    for name in ("rf_opt_fallback", "fgr_sequential", "always_opt", "always_iar"):
        reference = summaries[name]
        comparisons[name] = {
            "wall_time_reduction": 1 - proposed["mean_wall_seconds"] / reference["mean_wall_seconds"],
            "cpu_work_reduction": 1 - proposed["mean_cpu_seconds"] / max(reference["mean_cpu_seconds"], 1e-9),
            "solver_call_reduction": 1 - proposed["mean_solver_calls"] / reference["mean_solver_calls"],
            "profit_ratio": proposed["mean_final_profit"] / max(reference["mean_final_profit"], 1e-9),
            "success_rate_delta": proposed["admission_deadline_success_rate"] - reference["admission_deadline_success_rate"],
        }
    result = {
        "design": {"topology": args.topology, "steps": args.steps, "train_seeds": args.train_seeds, "validation_seeds": args.validation_seeds, "test_seeds": args.test_seeds, "solver_seconds": args.solver_seconds, "reference": "FGR priority rule with sequential cold-rebuilt candidate execution; all feature, inference, copy and solve time included", "features": model.feature_names},
        "selected_validation_config": {"quality_floor": model.quality_floor, "feasibility_floor": model.feasibility_floor},
        "calibration": {"seed_groups": sorted(calibration_seeds) if len(args.validation_seeds)>1 else [], "status": calibration_status},
        "validation_profiles": profiles, "summaries": summaries, "comparisons": comparisons,
        "decisions": rows,
        "limitations": ["Short synthetic request sequences do not establish production or BRAIN generalization.", "Cold rebuilding removes cache contamination but differs from the original incremental 5Guard solver; the adapter rebuilds all request constraints and missing auxiliary variables.", "CPU timing is process CPU time; external child-process costs are not relevant to this sequential in-process backend.", "Fallback budget is checked before retry; upstream model construction is not preemptible, and overruns count as failures.", "Demand occupancy features approximate load and exclude isolation/orchestration overhead; exact residual transport bandwidth is unavailable from X/Y.", "Sigmoid calibration is fitted only when both outcome classes exist in separate calibration seed groups; small calibration samples do not guarantee reliability."]
    }
    (output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    joblib.dump({"selector_state": {k:v for k,v in vars(model).items() if k != "predictions"}, "classifier": classifier}, output / "selector.joblib")
    save_figure(summaries, output / "comparison.png")
    print(json.dumps({"summaries": summaries, "comparisons": comparisons}, indent=2))


if __name__ == "__main__":
    main()
