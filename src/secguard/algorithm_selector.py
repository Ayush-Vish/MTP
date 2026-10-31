"""Objective 3: learned 5Guard algorithm selection.

The selector learns from per-step counterfactual outcomes produced by the four
5Guard ensemble members (OPT, IAR, DTR, and RNR).  Its label is the fastest
feasible algorithm whose profit is within a configurable tolerance of the best
observed profit.  Features are restricted to information available before the
current allocation: request properties, time, recent arrivals, and the previous
5Guard network state.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import pickle
import sys
import time
from typing import Mapping, Sequence

import joblib
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix


ALGORITHMS = ("opt", "iar", "dtr", "rnr")
SERVICES = ("eMBB", "uRLLC", "mMTC", "MC")

# service, isolation, CPU, radio, bandwidth, revenue, deadline
SERVICE_PROFILES = (
    ("eMBB", 0, 18.0, 1.0, 10_000.0, 48.0, 6.0),
    ("uRLLC", 1, 50.0, 1.0, 10.0, 70.0, 4.0),
    ("mMTC", 0, 4.0, 10.0, 0.1, 30.0, 10.0),
    ("MC", 2, 80.0, 1.0, 10_000.0, 105.0, 2.0),
)


@dataclass(frozen=True)
class SelectorConfig:
    quality_floor: float = 0.95
    confidence_threshold: float = 0.60
    fallback_algorithm: str = "opt"
    train_iterations: int = 7
    random_state: int = 42
    n_estimators: int = 400

    def __post_init__(self) -> None:
        if not 0.0 < self.quality_floor <= 1.0:
            raise ValueError("quality_floor must be in (0, 1]")
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be in [0, 1]")
        if self.fallback_algorithm not in ALGORITHMS:
            raise ValueError("fallback_algorithm must be a candidate algorithm")
        if self.train_iterations < 1:
            raise ValueError("train_iterations must be positive")


def request_schedule(iterations: int, steps: int, seed: int = 42) -> np.ndarray:
    """Recreate the seeded service schedule used by the 5Guard reproduction."""

    if iterations < 1 or steps < 1:
        raise ValueError("iterations and steps must be positive")
    rng = np.random.RandomState(seed)
    return rng.choice(4, size=(iterations, steps), p=(0.70, 0.15, 0.10, 0.05))


def choose_oracle(
    profits: Mapping[str, float],
    latencies: Mapping[str, float],
    feasible: Mapping[str, bool],
    quality_floor: float,
) -> tuple[str, float]:
    """Choose the fastest feasible algorithm within the profit-loss budget."""

    valid = [algorithm for algorithm in ALGORITHMS if feasible.get(algorithm, False)]
    if not valid:
        raise ValueError("at least one feasible algorithm is required")
    best_profit = max(float(profits[algorithm]) for algorithm in valid)
    tolerance = (1.0 - quality_floor) * max(abs(best_profit), 1.0)
    qualified = [
        algorithm
        for algorithm in valid
        if best_profit - float(profits[algorithm]) <= tolerance + 1e-12
    ]
    selected = min(qualified, key=lambda algorithm: float(latencies[algorithm]))
    return selected, best_profit


def quality_retention(profit: float, best_profit: float, feasible: bool = True) -> float:
    """Return bounded relative quality, with infeasible outcomes scored as zero."""

    if not feasible:
        return 0.0
    loss = max(best_profit - profit, 0.0)
    return float(np.clip(1.0 - loss / max(abs(best_profit), 1.0), 0.0, 1.0))


def _load_pickle(path: Path, fiveguard_dir: Path) -> dict:
    # Pickles contain instances of external/5guard/data.py classes in R_t.
    # Prepending that directory lets the standard unpickler resolve the class.
    absolute = str(fiveguard_dir.resolve())
    previous_data_module = sys.modules.get("data")
    if previous_data_module is not None and not hasattr(previous_data_module, "sr"):
        del sys.modules["data"]
    sys.path.insert(0, absolute)
    try:
        with path.open("rb") as handle:
            return pickle.load(handle)
    finally:
        sys.path.remove(absolute)
        if previous_data_module is not None and not hasattr(previous_data_module, "sr"):
            sys.modules["data"] = previous_data_module


def load_traces(data_dir: Path, fiveguard_dir: Path) -> dict[str, dict]:
    """Load the four ensemble members and measured 5Guard (FGR) trace."""

    required = (*ALGORITHMS, "fgr")
    missing = [name for name in required if not (data_dir / f"{name}.pkl").exists()]
    if missing:
        raise FileNotFoundError(
            f"missing 5Guard traces for {', '.join(missing)}; run the reproduction first"
        )
    return {
        name: _load_pickle(data_dir / f"{name}.pkl", fiveguard_dir)
        for name in required
    }


def _previous(array: np.ndarray, iteration: int, step: int) -> np.ndarray | float:
    if step == 0:
        return np.zeros(array.shape[2:], dtype=float) if array.ndim > 2 else 0.0
    return array[iteration, step - 1]


def build_dataset(
    traces: Mapping[str, dict], quality_floor: float = 0.95
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create leakage-safe features and counterfactual outcome records."""

    sample = traces[ALGORITHMS[0]]["profit"]
    iterations, steps = sample.shape
    schedule = request_schedule(iterations, steps)
    fgr = traces["fgr"]
    feature_rows: list[dict] = []
    outcome_rows: list[dict] = []

    for iteration in range(iterations):
        for step in range(steps):
            service_index = int(schedule[iteration, step])
            service, isolation, cpu, radio, bandwidth, revenue, deadline = (
                SERVICE_PROFILES[service_index]
            )
            profits = {
                algorithm: float(traces[algorithm]["profit"][iteration, step])
                for algorithm in ALGORITHMS
            }
            latencies = {
                algorithm: max(float(traces[algorithm]["time"][iteration, step]), 0.0)
                for algorithm in ALGORITHMS
            }
            feasible = {
                algorithm: bool(
                    traces[algorithm]["feasib"][iteration, step] > 0
                    and traces[algorithm]["timeou"][iteration, step] <= 0
                    and latencies[algorithm] <= deadline
                )
                for algorithm in ALGORITHMS
            }
            if not any(feasible.values()):
                continue
            oracle, best_profit = choose_oracle(
                profits, latencies, feasible, quality_floor
            )

            recent = schedule[iteration, max(0, step - 10) : step]
            feature = {
                "time_fraction": step / max(steps - 1, 1),
                "request_isolation": isolation / 2.0,
                "request_cpu": cpu / 100.0,
                "request_radio": radio / 100.0,
                "request_bandwidth_log": np.log1p(bandwidth) / np.log1p(10_000.0),
                "request_revenue": revenue / 120.0,
                "request_deadline": deadline / 10.0,
                "previous_profit": float(_previous(fgr["profit"], iteration, step)),
                "previous_migrations": float(_previous(fgr["migrat"], iteration, step)),
                "previous_latency": float(_previous(fgr["time"], iteration, step)),
                "previous_violation": float(
                    np.asarray(_previous(fgr["violat"], iteration, step)).flat[0]
                ),
                "previous_overhead": float(
                    np.asarray(_previous(fgr["overhe"], iteration, step)).flat[0]
                ),
                "previous_resource_efficiency": float(
                    np.asarray(_previous(fgr["reseff"], iteration, step)).flat[0]
                ),
                "previous_rejections": float(
                    np.asarray(_previous(fgr["reject"], iteration, step)).sum()
                ),
            }
            for index, name in enumerate(SERVICES):
                feature[f"service_{name}"] = float(service_index == index)
                feature[f"recent_{name}"] = float((recent == index).sum()) / 10.0
            feature_rows.append(feature)

            outcome = {
                "iteration": iteration,
                "step": step,
                "service": service,
                "deadline": deadline,
                "oracle": oracle,
                "best_profit": best_profit,
                # FGR records the maximum runtime of its candidates on the FGR
                # trajectory. Candidate traces below follow independent states,
                # so their max/sum are explicitly labeled counterfactual.
                "measured_fgr_latency": float(fgr["time"][iteration, step]),
                "counterfactual_parallel_wait": max(latencies.values()),
                "counterfactual_sequential_sum": sum(latencies.values()),
            }
            for algorithm in ALGORITHMS:
                outcome[f"{algorithm}_profit"] = profits[algorithm]
                outcome[f"{algorithm}_latency"] = latencies[algorithm]
                outcome[f"{algorithm}_feasible"] = feasible[algorithm]
            outcome_rows.append(outcome)

    return pd.DataFrame(feature_rows), pd.DataFrame(outcome_rows)


def split_by_iteration(
    features: pd.DataFrame, outcomes: pd.DataFrame, train_iterations: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split complete simulation runs to prevent temporal/group leakage."""

    train_mask = outcomes["iteration"] < train_iterations
    if not train_mask.any() or train_mask.all():
        raise ValueError("train_iterations must leave both training and test runs")
    return (
        features.loc[train_mask].reset_index(drop=True),
        features.loc[~train_mask].reset_index(drop=True),
        outcomes.loc[train_mask].reset_index(drop=True),
        outcomes.loc[~train_mask].reset_index(drop=True),
    )


def train_selector(
    features: pd.DataFrame, labels: Sequence[str], config: SelectorConfig
) -> RandomForestClassifier:
    model = RandomForestClassifier(
        n_estimators=config.n_estimators,
        max_depth=14,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        random_state=config.random_state,
        n_jobs=-1,
    )
    model.fit(features, labels)
    return model


def predict_with_fallback(
    model: RandomForestClassifier,
    features: pd.DataFrame,
    confidence_threshold: float,
    fallback_algorithm: str = "opt",
) -> tuple[np.ndarray, np.ndarray]:
    """Use the safe fallback whenever classifier confidence is insufficient."""

    probabilities = model.predict_proba(features)
    class_indices = np.argmax(probabilities, axis=1)
    predictions = model.classes_[class_indices].astype(object)
    confidence = probabilities[np.arange(len(features)), class_indices]
    predictions[confidence < confidence_threshold] = fallback_algorithm
    return np.asarray(predictions, dtype=str), confidence


def evaluate_choices(
    choices: Sequence[str], outcomes: pd.DataFrame, inference_seconds: float = 0.0
) -> dict:
    """Evaluate chosen algorithms using their held-out measured outcomes."""

    rows = []
    per_request_inference = inference_seconds / max(len(outcomes), 1)
    for choice, (_, row) in zip(choices, outcomes.iterrows()):
        if choice not in ALGORITHMS:
            raise ValueError(f"unknown algorithm choice: {choice}")
        feasible = bool(row[f"{choice}_feasible"])
        profit = float(row[f"{choice}_profit"])
        latency = float(row[f"{choice}_latency"]) + per_request_inference
        rows.append(
            {
                "algorithm": choice,
                "profit": profit,
                "latency": latency,
                "feasible": feasible,
                "deadline_met": feasible and latency <= float(row["deadline"]),
                "quality_retention": quality_retention(
                    profit, float(row["best_profit"]), feasible
                ),
                "within_5_percent": feasible
                and quality_retention(profit, float(row["best_profit"]), feasible)
                >= 0.95,
            }
        )
    latency = np.asarray([row["latency"] for row in rows], dtype=float)
    quality = np.asarray([row["quality_retention"] for row in rows], dtype=float)
    return {
        "requests": len(rows),
        "mean_latency_seconds": float(latency.mean()),
        "p95_latency_seconds": float(np.quantile(latency, 0.95)),
        "mean_profit": float(np.mean([row["profit"] for row in rows])),
        "mean_quality_retention": float(quality.mean()),
        "within_5_percent_rate": float(
            np.mean([row["within_5_percent"] for row in rows])
        ),
        "feasibility_rate": float(np.mean([row["feasible"] for row in rows])),
        "deadline_success_rate": float(
            np.mean([row["deadline_met"] for row in rows])
        ),
        "selection_counts": dict(Counter(row["algorithm"] for row in rows)),
        "per_request": rows,
    }


def _save_results_figure(result: dict, path: Path) -> None:
    policies = ("selector", "always_opt", "always_iar", "majority")
    labels = ("Selector", "Always OPT", "Always IAR", "Majority")
    colors = ("#1f77b4", "#e4ac3e", "#416fbd", "#777777")
    summaries = result["evaluation"]["policies"]
    latency_labels = (
        "Selector",
        "Measured 5Guard",
        "CF parallel wait",
        "CF sequential sum",
    )
    latencies = (
        summaries["selector"]["mean_latency_seconds"],
        result["evaluation"]["measured_fgr_mean_latency_seconds"],
        result["evaluation"]["counterfactual_parallel_wait_seconds"],
        result["evaluation"]["counterfactual_sequential_sum_seconds"],
    )
    qualities = [100 * summaries[name]["mean_quality_retention"] for name in policies]
    counts = result["evaluation"]["selector_confusion_matrix"]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    bars = axes[0].bar(latency_labels, latencies, color=colors)
    axes[0].bar_label(bars, fmt="%.3f", padding=3, fontsize=8)
    axes[0].set(title="Mean allocation latency", ylabel="Seconds")
    axes[0].tick_params(axis="x", rotation=25)
    bars = axes[1].bar(labels, qualities, color=colors)
    axes[1].bar_label(bars, fmt="%.1f%%", padding=3, fontsize=8)
    axes[1].set(title="Profit quality retained", ylabel="Percent", ylim=(0, 105))
    axes[1].tick_params(axis="x", rotation=25)
    image = axes[2].imshow(counts, cmap="Blues")
    axes[2].set(
        title="Selector vs. oracle",
        xlabel="Predicted algorithm",
        ylabel="Oracle algorithm",
        xticks=range(len(ALGORITHMS)),
        yticks=range(len(ALGORITHMS)),
        xticklabels=[name.upper() for name in ALGORITHMS],
        yticklabels=[name.upper() for name in ALGORITHMS],
    )
    for row in range(len(ALGORITHMS)):
        for column in range(len(ALGORITHMS)):
            axes[2].text(column, row, counts[row][column], ha="center", va="center")
    fig.colorbar(image, ax=axes[2], fraction=0.046, pad=0.04)
    for axis in axes[:2]:
        axis.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Objective 3: learned 5Guard algorithm selection")
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _save_architecture_diagram(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(12, 3.2))
    axis.set_xlim(0, 12)
    axis.set_ylim(0, 3.2)
    axis.axis("off")
    boxes = (
        (0.2, "Slice request\n+ SecGuard risk"),
        (3.0, "Network state\n+ request features"),
        (5.8, "Random-Forest\nmeta-selector"),
        (8.6, "One chosen solver\nOPT / IAR / DTR / RNR"),
    )
    for x, label in boxes:
        patch = FancyBboxPatch(
            (x, 1.0), 2.2, 1.15, boxstyle="round,pad=0.08",
            facecolor="#eaf2f8", edgecolor="#1f4e79", linewidth=1.8,
        )
        axis.add_patch(patch)
        axis.text(x + 1.1, 1.575, label, ha="center", va="center", fontsize=10)
    for start in (2.4, 5.2, 8.0):
        axis.annotate(
            "", xy=(start + 0.55, 1.575), xytext=(start + 0.05, 1.575),
            arrowprops={"arrowstyle": "->", "lw": 2, "color": "#333333"},
        )
    axis.annotate(
        "allocation result feeds the next network state",
        xy=(4.1, 0.92), xytext=(9.7, 0.35), ha="center", fontsize=9,
        arrowprops={"arrowstyle": "->", "lw": 1.5, "color": "#777777",
                    "connectionstyle": "arc3,rad=-0.25"},
    )
    axis.text(
        6, 2.75,
        "Objective 3 replaces run-all ensemble execution with one predicted solver",
        ha="center", va="center", fontsize=13, weight="bold",
    )
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def run_objective3(
    data_dir: Path,
    fiveguard_dir: Path,
    output_file: Path,
    model_file: Path,
    config: SelectorConfig = SelectorConfig(),
) -> dict:
    traces = load_traces(data_dir, fiveguard_dir)
    features, outcomes = build_dataset(traces, config.quality_floor)
    x_train, x_test, y_train_rows, y_test_rows = split_by_iteration(
        features, outcomes, config.train_iterations
    )
    model = train_selector(x_train, y_train_rows["oracle"], config)
    start = time.perf_counter()
    predictions, confidence = predict_with_fallback(
        model,
        x_test,
        config.confidence_threshold,
        config.fallback_algorithm,
    )
    inference_seconds = time.perf_counter() - start
    majority = Counter(y_train_rows["oracle"]).most_common(1)[0][0]

    policies = {
        # Solver latency and model inference are reported separately so timing
        # noise in the classifier does not alter the allocation comparison.
        "selector": evaluate_choices(predictions, y_test_rows),
        "always_opt": evaluate_choices(["opt"] * len(y_test_rows), y_test_rows),
        "always_iar": evaluate_choices(["iar"] * len(y_test_rows), y_test_rows),
        "majority": evaluate_choices([majority] * len(y_test_rows), y_test_rows),
        "oracle": evaluate_choices(y_test_rows["oracle"], y_test_rows),
    }
    selector_latency = policies["selector"]["mean_latency_seconds"]
    measured_fgr = float(y_test_rows["measured_fgr_latency"].mean())
    parallel_wait = float(y_test_rows["counterfactual_parallel_wait"].mean())
    sequential_sum = float(y_test_rows["counterfactual_sequential_sum"].mean())
    latency_change = (
        (selector_latency - measured_fgr) / measured_fgr
        if measured_fgr > 0
        else 0.0
    )
    confusion = confusion_matrix(
        y_test_rows["oracle"], predictions, labels=list(ALGORITHMS)
    )
    importances = sorted(
        zip(x_train.columns, model.feature_importances_),
        key=lambda item: item[1],
        reverse=True,
    )
    result = {
        "objective": "Objective 3: Intelligent Algorithm Selection",
        "method": "Random-Forest meta-classifier",
        "candidate_algorithms": list(ALGORITHMS),
        "label_rule": (
            "fastest deadline-feasible algorithm within 5% of the best observed profit"
        ),
        "data": {
            "source": str(data_dir),
            "total_rows": len(features),
            "training_rows": len(x_train),
            "held_out_rows": len(x_test),
            "training_iterations": sorted(y_train_rows["iteration"].unique().tolist()),
            "held_out_iterations": sorted(y_test_rows["iteration"].unique().tolist()),
            "features": list(features.columns),
        },
        "evaluation": {
            "oracle_label_accuracy": float(
                accuracy_score(y_test_rows["oracle"], predictions)
            ),
            "mean_prediction_confidence": float(confidence.mean()),
            "fallback_rate": float(
                np.mean(confidence < config.confidence_threshold)
            ),
            "mean_inference_milliseconds": 1000 * inference_seconds / len(x_test),
            "measured_fgr_mean_latency_seconds": measured_fgr,
            "counterfactual_parallel_wait_seconds": parallel_wait,
            "counterfactual_sequential_sum_seconds": sequential_sum,
            "selector_latency_change_vs_measured_fgr": latency_change,
            "selector_confusion_matrix": confusion.tolist(),
            "policies": policies,
        },
        "feature_importance": [
            {"feature": name, "importance": float(value)}
            for name, value in importances
        ],
        "config": {
            "quality_floor": config.quality_floor,
            "confidence_threshold": config.confidence_threshold,
            "fallback_algorithm": config.fallback_algorithm,
            "train_iterations": config.train_iterations,
            "random_state": config.random_state,
            "n_estimators": config.n_estimators,
        },
        "limitations": [
            "Offline counterfactual evaluation uses independent algorithm trajectories, not one causal replay trajectory.",
            "Training and held-out runs share the synthetic topology and seeded traffic generator.",
            "The measured FGR implementation executes candidates sequentially; the parallel lower bound is also reported.",
            "BRAIN-topology and live-system generalization remain untested.",
        ],
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    model_file.parent.mkdir(parents=True, exist_ok=True)
    figure_file = output_file.with_name("objective3_algorithm_selector.png")
    diagram_file = output_file.with_name("objective3_architecture.png")
    result["artifacts"] = {
        "model": str(model_file),
        "figure": str(figure_file),
        "architecture_diagram": str(diagram_file),
    }
    joblib.dump(
        {
            "model": model,
            "feature_names": list(features.columns),
            "confidence_threshold": config.confidence_threshold,
            "fallback_algorithm": config.fallback_algorithm,
        },
        model_file,
        compress=3,
    )
    _save_results_figure(result, figure_file)
    _save_architecture_diagram(diagram_file)
    output_file.write_text(json.dumps(result, indent=2), encoding="utf-8")

    selector = policies["selector"]
    print(f"held-out requests: {len(x_test)}")
    print(f"oracle-label accuracy: {result['evaluation']['oracle_label_accuracy']:.2%}")
    print(f"selector mean latency: {selector['mean_latency_seconds']:.6f}s")
    print(f"selector mean quality retention: {selector['mean_quality_retention']:.2%}")
    print(f"latency change vs measured FGR: {latency_change:+.2%}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("external/5guard/saved_data/synthetic"),
    )
    parser.add_argument("--fiveguard-dir", type=Path, default=Path("external/5guard"))
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("artifacts/objective3_algorithm_selector.json"),
    )
    parser.add_argument(
        "--model-file",
        type=Path,
        default=Path("artifacts/objective3_selector.joblib"),
    )
    parser.add_argument("--quality-floor", type=float, default=0.95)
    parser.add_argument("--confidence-threshold", type=float, default=0.60)
    parser.add_argument("--train-iterations", type=int, default=7)
    args = parser.parse_args()
    run_objective3(
        args.data_dir,
        args.fiveguard_dir,
        args.output_file,
        args.model_file,
        SelectorConfig(
            quality_floor=args.quality_floor,
            confidence_threshold=args.confidence_threshold,
            train_iterations=args.train_iterations,
        ),
    )


if __name__ == "__main__":
    main()
