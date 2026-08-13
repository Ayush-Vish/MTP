"""Reviewer-oriented validation of SecGuard policy learning and trade-offs."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
from time import perf_counter

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from secguard.policy import decide_isolation
from secguard.policy_learning import (
    FIXED_THRESHOLDS,
    _evaluate_policy,
    _load_probability_pools,
    _mean,
    _summary,
    apply_thresholds,
    build_scenarios,
    threshold_candidates,
)
from secguard.security_experiment import _exposure, _load_fiveguard, _run_policy, _working_directory


LEARNED_THRESHOLDS = (0.30, 0.35, 0.90)
MINIMUM_EXPOSURE_REDUCTION = 0.60
SAMPLED_CANDIDATES = 81


def sampled_candidate_indices(
    candidates: list[tuple[float, float, float]],
    budget: int = SAMPLED_CANDIDATES,
) -> set[int]:
    """Reproduce the learner's sample and guarantee the exact policy budget."""
    if not 1 <= budget <= len(candidates):
        raise ValueError("budget must be between 1 and the number of candidates")
    rng = np.random.default_rng(42)
    sampled = set(rng.choice(len(candidates), size=budget - 1, replace=False).tolist())
    sampled.add(candidates.index(FIXED_THRESHOLDS))
    while len(sampled) < budget:
        remaining = sorted(set(range(len(candidates))) - sampled)
        sampled.add(int(rng.choice(remaining)))
    return sampled


def pareto_frontier(rows: list[dict]) -> list[dict]:
    """Return policies not dominated in profit (max) and exposure (min)."""
    frontier = []
    for candidate in rows:
        dominated = any(
            other["mean_profit"] >= candidate["mean_profit"]
            and other["mean_exposure"] <= candidate["mean_exposure"]
            and (
                other["mean_profit"] > candidate["mean_profit"]
                or other["mean_exposure"] < candidate["mean_exposure"]
            )
            for other in rows
        )
        if not dominated:
            frontier.append(candidate)
    return sorted(frontier, key=lambda row: row["mean_exposure"])


def paired_test(reference: list[dict], proposed: list[dict], key: str) -> dict:
    reference_values = np.asarray([row[key] for row in reference], dtype=float)
    proposed_values = np.asarray([row[key] for row in proposed], dtype=float)
    differences = proposed_values - reference_values
    nonzero = differences[differences != 0]
    if len(nonzero) == 0:
        statistic, p_value = 0.0, 1.0
    else:
        statistic, p_value = wilcoxon(
            proposed_values,
            reference_values,
            zero_method="wilcox",
            alternative="two-sided",
            method="auto",
        )
    sd = float(differences.std(ddof=1)) if len(differences) > 1 else 0.0
    return {
        "mean_difference": float(differences.mean()),
        "median_difference": float(np.median(differences)),
        "wilcoxon_statistic": float(statistic),
        "p_value": float(p_value),
        "paired_cohens_dz": float(differences.mean() / sd) if sd else 0.0,
        "positive": int((differences > 0).sum()),
        "negative": int((differences < 0).sum()),
        "ties": int((differences == 0).sum()),
    }


def _evaluate_no_quarantine(fiveguard, scenarios: list[list[dict]], iteration: int) -> list[dict]:
    rows = []
    for scenario in scenarios:
        decisions = apply_thresholds(scenario, LEARNED_THRESHOLDS)
        for item in decisions:
            if item["action"] == "QUARANTINE":
                item["action"] = "UPGRADE_L2"
                item["target_level"] = 2
                item["target_isolation"] = "L2"
                item["reason"] = "Ablation: quarantine disabled; force L2."
        with contextlib.redirect_stdout(io.StringIO()):
            allocation = _run_policy(
                fiveguard, decisions, adaptive=True, iteration=iteration
            )
        rows.append(
            {
                "profit": allocation["final_profit"],
                "admitted": allocation["admitted"],
                "quarantined": allocation["quarantined"],
                "exposure": _exposure(decisions, adaptive=True),
                "migrations": allocation.get("final_migrations", 0.0),
                "violation_cost": allocation.get("final_violation_cost", 0.0),
                "deployment_cost": allocation.get("final_deployment_cost", 0.0),
                "overhead_cost": allocation.get("final_overhead_cost", 0.0),
                "resource_efficiency": allocation.get("mean_resource_efficiency", 0.0),
                "allocation_seconds": allocation.get("allocation_seconds", 0.0),
            }
        )
    return rows


def benchmark_policy_latency(iterations: int = 100_000) -> dict:
    start = perf_counter()
    for index in range(iterations):
        decide_isolation(
            f"slice-{index}",
            (index % 1000) / 1000,
            index % 3,
            *LEARNED_THRESHOLDS,
        )
    elapsed = perf_counter() - start
    return {
        "decisions": iterations,
        "total_seconds": elapsed,
        "microseconds_per_decision": elapsed / iterations * 1e6,
        "decisions_per_second": iterations / elapsed,
    }


def benchmark_detector_latency(
    test_file: Path,
    model_file: Path,
    sample_rows: int = 1024,
    repeats: int = 20,
) -> dict:
    """Measure local batch inference without including CSV or model-load time."""
    bundle = joblib.load(model_file)
    frame = pd.read_csv(test_file, nrows=sample_rows)
    features = frame[bundle["feature_names"]]
    model = bundle["model"]
    model.predict_proba(features)
    durations = []
    for _ in range(repeats):
        start = perf_counter()
        model.predict_proba(features)
        durations.append(perf_counter() - start)
    median_seconds = float(np.median(durations))
    packets = len(features)
    return {
        "model_file_bytes": model_file.stat().st_size,
        "batch_rows": packets,
        "repeats": repeats,
        "median_batch_seconds": median_seconds,
        "microseconds_per_packet": median_seconds / packets * 1e6,
        "packets_per_second": packets / median_seconds,
        "scope": "Warm local batch predict_proba; excludes disk I/O and model loading.",
    }


def _plot_pareto(
    evaluations: list[dict],
    frontier: list[dict],
    selected: dict[str, tuple[float, float, float]],
    path: Path,
) -> None:
    # IEEE double-column dimensions and a colorblind-safe categorical palette.
    fig, axis = plt.subplots(figsize=(6.9, 4.1))
    axis.scatter(
        [row["mean_exposure"] for row in evaluations],
        [row["mean_profit"] for row in evaluations],
        s=20,
        alpha=0.35,
        color="#BBBBBB",
        label="Candidate policies",
    )
    axis.plot(
        [row["mean_exposure"] for row in frontier],
        [row["mean_profit"] for row in frontier],
        "o-",
        color="#CC3311",
        label="Training Pareto frontier",
    )
    lookup = {tuple(row["thresholds"]): row for row in evaluations}
    markers = {"Fixed": "s", "Learned": "*", "Oracle": "D", "Random": "^"}
    colors = {
        "Fixed": "#0077BB",
        "Learned": "#009988",
        "Oracle": "#EE3377",
        "Random": "#EE7733",
    }
    for name, thresholds in selected.items():
        row = lookup[thresholds]
        axis.scatter(
            row["mean_exposure"],
            row["mean_profit"],
            marker=markers[name],
            color=colors[name],
            s=130,
            edgecolor="black",
            linewidth=0.6,
            label=name,
            zorder=5,
        )
    axis.set_xlabel("Mean modeled isolation-exposure score (unitless; lower is safer)")
    axis.set_ylabel("Mean 5Guard profit (synthetic units; higher is better)")
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(fontsize=8, ncol=2, frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def _plot_metrics(results: dict[str, dict], path: Path) -> None:
    names = ["Static", "Fixed", "Learned", "Train oracle", "Random", "No quarantine"]
    keys = ["static", "fixed", "learned", "oracle", "random", "no_quarantine"]
    colors = ["#BBBBBB", "#0077BB", "#009988", "#EE3377", "#EE7733", "#33BBEE"]
    metrics = (
        ("profit", "Mean profit", "Synthetic profit units"),
        ("exposure", "Mean modeled exposure", "Exposure score (unitless)"),
        ("admitted", "Mean admission", "Admitted slices (count)"),
        ("migrations", "Mean migrations", "Migrations (count)"),
        ("overhead_cost", "Mean overhead cost", "Synthetic cost units"),
        ("resource_efficiency", "Mean resource efficiency", "Profit/cost ratio (unitless)"),
    )
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for axis, (metric, title, ylabel) in zip(axes.flat, metrics):
        values = [results[key][metric]["mean"] for key in keys]
        bars = axis.bar(names, values, color=colors)
        axis.bar_label(bars, labels=[f"{value:.2f}" for value in values], padding=3, fontsize=8)
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.tick_params(axis="x", rotation=24, labelsize=8)
        axis.spines[["top", "right"]].set_visible(False)
    fig.suptitle("SecGuard reviewer-oriented metric suite")
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def run_validation(
    data_dir: Path,
    model_file: Path,
    external_dir: Path,
    output_file: Path,
    train_seeds: range,
    test_seeds: range,
) -> dict:
    train_benign, train_attack = _load_probability_pools(
        [data_dir / "Train_subset_1.csv", data_dir / "Train_subset_2.csv"], model_file
    )
    test_benign, test_attack = _load_probability_pools(
        [data_dir / "Test_Data.csv"], model_file
    )
    training_scenarios = build_scenarios(train_benign, train_attack, train_seeds)
    test_scenarios = build_scenarios(test_benign, test_attack, test_seeds)
    fiveguard = _load_fiveguard(external_dir)
    candidates = threshold_candidates()

    with _working_directory(external_dir.resolve()):
        static_training = _evaluate_policy(fiveguard, training_scenarios, None, iteration=700)
        baseline_exposure = _mean(static_training, "exposure")
        evaluations = []
        for index, candidate in enumerate(candidates):
            rows = _evaluate_policy(
                fiveguard, training_scenarios, candidate, iteration=800 + index
            )
            exposure = _mean(rows, "exposure")
            evaluations.append(
                {
                    "thresholds": candidate,
                    "mean_profit": _mean(rows, "profit"),
                    "mean_exposure": exposure,
                    "exposure_reduction": (baseline_exposure - exposure) / baseline_exposure,
                }
            )

        feasible = [
            row for row in evaluations
            if row["exposure_reduction"] >= MINIMUM_EXPOSURE_REDUCTION
        ]
        oracle_row = max(feasible, key=lambda row: (row["mean_profit"], -row["mean_exposure"]))
        sampled_indices = sampled_candidate_indices(candidates)
        sampled_feasible = [
            evaluations[index] for index in sampled_indices
            if evaluations[index]["exposure_reduction"] >= MINIMUM_EXPOSURE_REDUCTION
        ]
        random_row = max(
            sampled_feasible, key=lambda row: (row["mean_profit"], -row["mean_exposure"])
        )
        frontier = pareto_frontier(evaluations)

        policies = {
            "static": None,
            "fixed": FIXED_THRESHOLDS,
            "learned": LEARNED_THRESHOLDS,
            "oracle": tuple(oracle_row["thresholds"]),
            "random": tuple(random_row["thresholds"]),
        }
        raw_test = {
            name: _evaluate_policy(
                fiveguard, test_scenarios, thresholds, iteration=1100 + offset
            )
            for offset, (name, thresholds) in enumerate(policies.items())
        }
        raw_test["no_quarantine"] = _evaluate_no_quarantine(
            fiveguard, test_scenarios, iteration=1110
        )

    summaries = {name: _summary(rows) for name, rows in raw_test.items()}
    validation = {
        "design": {
            "training_scenarios": len(training_scenarios),
            "test_scenarios": len(test_scenarios),
            "total_candidate_policies": len(candidates),
            "ml_evaluated_policies": len(sampled_indices),
            "gurobi_evaluation_reduction": 1 - len(sampled_indices) / len(candidates),
            "minimum_exposure_reduction": MINIMUM_EXPOSURE_REDUCTION,
        },
        "selected_thresholds": {
            "fixed": FIXED_THRESHOLDS,
            "learned": LEARNED_THRESHOLDS,
            "training_oracle": oracle_row["thresholds"],
            "equal_budget_random": random_row["thresholds"],
        },
        "training": {
            "pareto_policies": len(frontier),
            "candidate_evaluations": evaluations,
            "pareto_frontier": frontier,
            "oracle": oracle_row,
            "equal_budget_random": random_row,
            "learned": next(row for row in evaluations if tuple(row["thresholds"]) == LEARNED_THRESHOLDS),
        },
        "test": summaries,
        "per_scenario_test": raw_test,
        "statistical_tests": {
            "learned_vs_fixed_profit": paired_test(
                raw_test["fixed"], raw_test["learned"], "profit"
            ),
            "learned_vs_static_exposure": paired_test(
                raw_test["static"], raw_test["learned"], "exposure"
            ),
            "learned_vs_oracle_profit": paired_test(
                raw_test["oracle"], raw_test["learned"], "profit"
            ),
            "learned_vs_no_quarantine_profit": paired_test(
                raw_test["no_quarantine"], raw_test["learned"], "profit"
            ),
        },
        "sample_efficiency": {
            "gurobi_policies_avoided": len(candidates) - len(sampled_indices),
            "gurobi_scenario_allocations_avoided": (
                len(candidates) - len(sampled_indices)
            ) * len(training_scenarios),
            "evaluation_reduction": 1 - len(sampled_indices) / len(candidates),
            "heldout_profit_regret_vs_training_oracle": (
                summaries["oracle"]["profit"]["mean"]
                - summaries["learned"]["profit"]["mean"]
            ) / abs(summaries["oracle"]["profit"]["mean"]),
            "heldout_profit_gain_vs_equal_budget_random": (
                summaries["learned"]["profit"]["mean"]
                - summaries["random"]["profit"]["mean"]
            ) / abs(summaries["random"]["profit"]["mean"]),
        },
        "online_policy_latency": benchmark_policy_latency(),
        "detector_latency": benchmark_detector_latency(
            data_dir / "Test_Data.csv", model_file
        ),
        "limitations": [
            "The exhaustive oracle is selected on training scenarios, not future-aware test outcomes.",
            "All allocation policies still use IAR and the synthetic 5Guard topology.",
            "Exposure is an isolation-level proxy, not measured attack propagation.",
            "Scenario risks come from one intrusion dataset despite train/test file separation.",
        ],
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    pareto_file = output_file.with_name("pareto_frontier.png")
    metrics_file = output_file.with_name("extended_metrics.png")
    selected_for_plot = {
        "Fixed": FIXED_THRESHOLDS,
        "Learned": LEARNED_THRESHOLDS,
        "Oracle": tuple(oracle_row["thresholds"]),
        "Random": tuple(random_row["thresholds"]),
    }
    _plot_pareto(evaluations, frontier, selected_for_plot, pareto_file)
    _plot_metrics(summaries, metrics_file)
    validation["artifacts"] = {
        "pareto_frontier": str(pareto_file),
        "extended_metrics": str(metrics_file),
    }
    output_file.write_text(json.dumps(validation, indent=2), encoding="utf-8")

    print("policy          profit    exposure  admitted  migrations  overhead")
    for name in ("static", "fixed", "learned", "oracle", "random", "no_quarantine"):
        row = summaries[name]
        print(
            f"{name:<15} {row['profit']['mean']:<9.2f} {row['exposure']['mean']:<9.4f} "
            f"{row['admitted']['mean']:<9.2f} {row['migrations']['mean']:<11.2f} "
            f"{row['overhead_cost']['mean']:.2f}"
        )
    print(
        "Gurobi policy evaluations avoided:",
        validation["sample_efficiency"]["gurobi_policies_avoided"],
    )
    return validation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--model-file", type=Path, default=Path("artifacts/risk_model.joblib"))
    parser.add_argument("--external-dir", type=Path, default=Path("external/5guard"))
    parser.add_argument(
        "--output-file", type=Path, default=Path("artifacts/research_validation.json")
    )
    parser.add_argument("--train-scenarios", type=int, default=5)
    parser.add_argument("--test-scenarios", type=int, default=30)
    args = parser.parse_args()
    run_validation(
        args.data_dir,
        args.model_file,
        args.external_dir,
        args.output_file,
        train_seeds=range(100, 100 + args.train_scenarios),
        test_seeds=range(1000, 1000 + args.test_scenarios),
    )


if __name__ == "__main__":
    main()
