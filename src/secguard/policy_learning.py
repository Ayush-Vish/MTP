"""Learn profit-aware SecGuard thresholds from offline 5Guard feedback."""

from __future__ import annotations

import argparse
import contextlib
import io
import itertools
import json
from pathlib import Path
from typing import Iterable

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from secguard.policy import decide_isolation
from secguard.security_experiment import (
    _exposure,
    _load_fiveguard,
    _run_policy,
    _working_directory,
)


FIXED_THRESHOLDS = (0.15, 0.40, 0.75)
SERVICE_SPECS = (
    ("eMBB", 0, 0, 6),
    ("mMTC", 0, 6, 20),
    ("uRLLC", 1, 22, 44),
    ("MC", 2, 48, 64),
)
PACKETS_PER_SLICE = 64


def threshold_candidates() -> list[tuple[float, float, float]]:
    candidates = []
    for l1, l2, quarantine in itertools.product(
        (0.10, 0.15, 0.20, 0.25, 0.30, 0.35),
        (0.30, 0.35, 0.40, 0.45, 0.50, 0.55),
        (0.70, 0.75, 0.80, 0.85, 0.90),
    ):
        if l1 < l2 < quarantine:
            candidates.append((l1, l2, quarantine))
    return candidates


def _load_probability_pools(data_files: list[Path], model_file: Path) -> tuple[np.ndarray, np.ndarray]:
    frame = pd.concat([pd.read_csv(path) for path in data_files], ignore_index=True)
    bundle = joblib.load(model_file)
    probabilities = bundle["model"].predict_proba(frame[bundle["feature_names"]])[:, 1]
    labels = frame["label"].to_numpy(dtype=int)
    return probabilities[labels == 0], probabilities[labels == 1]


def build_scenarios(
    benign_probabilities: np.ndarray,
    attack_probabilities: np.ndarray,
    seeds: Iterable[int],
) -> list[list[dict]]:
    """Bootstrap detector outputs into repeatable slice-level risk scenarios."""
    scenarios = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        scenario = []
        for service, requested_level, minimum_attacks, maximum_attacks in SERVICE_SPECS:
            attack_count = int(rng.integers(minimum_attacks, maximum_attacks + 1))
            benign_count = PACKETS_PER_SLICE - attack_count
            packet_risks = np.concatenate(
                [
                    rng.choice(benign_probabilities, benign_count, replace=True),
                    rng.choice(attack_probabilities, attack_count, replace=True),
                ]
            )
            scenario.append(
                {
                    "slice_id": f"seed-{seed}-{service.lower()}",
                    "service": service,
                    "requested_level": requested_level,
                    "risk_score": float(packet_risks.mean()),
                    "attack_packets": attack_count,
                    "packets": PACKETS_PER_SLICE,
                }
            )
        rng.shuffle(scenario)
        scenarios.append(scenario)
    return scenarios


def apply_thresholds(
    scenario: list[dict], thresholds: tuple[float, float, float]
) -> list[dict]:
    l1, l2, quarantine = thresholds
    output = []
    for item in scenario:
        decision = decide_isolation(
            item["slice_id"],
            item["risk_score"],
            item["requested_level"],
            l1_threshold=l1,
            l2_threshold=l2,
            quarantine_threshold=quarantine,
        )
        row = dict(item)
        row.update(decision.to_dict())
        output.append(row)
    return output


def _evaluate_policy(
    fiveguard,
    scenarios: list[list[dict]],
    thresholds: tuple[float, float, float] | None,
    iteration: int,
) -> list[dict]:
    rows = []
    for scenario in scenarios:
        decisions = scenario if thresholds is None else apply_thresholds(scenario, thresholds)
        with contextlib.redirect_stdout(io.StringIO()):
            allocation = _run_policy(
                fiveguard,
                decisions,
                adaptive=thresholds is not None,
                iteration=iteration,
            )
        rows.append(
            {
                "profit": allocation["final_profit"],
                "admitted": allocation["admitted"],
                "quarantined": allocation["quarantined"],
                "exposure": _exposure(decisions, adaptive=thresholds is not None),
            }
        )
    return rows


def _mean(rows: list[dict], key: str) -> float:
    return float(np.mean([row[key] for row in rows]))


def _summary(rows: list[dict]) -> dict:
    result = {}
    for key in ("profit", "exposure", "admitted", "quarantined"):
        values = np.asarray([row[key] for row in rows], dtype=float)
        margin = 0.0 if len(values) < 2 else 1.96 * float(values.std(ddof=1)) / np.sqrt(len(values))
        result[key] = {
            "mean": float(values.mean()),
            "ci95_low": float(values.mean() - margin),
            "ci95_high": float(values.mean() + margin),
        }
    return result


def _paired_summary(
    reference: list[dict], proposed: list[dict], key: str, lower_is_better: bool = False
) -> dict:
    deltas = np.asarray(
        [new[key] - old[key] for old, new in zip(reference, proposed)], dtype=float
    )
    margin = 0.0 if len(deltas) < 2 else 1.96 * float(deltas.std(ddof=1)) / np.sqrt(len(deltas))
    return {
        "mean_delta": float(deltas.mean()),
        "ci95_low": float(deltas.mean() - margin),
        "ci95_high": float(deltas.mean() + margin),
        "improved_scenarios": int(((deltas < 0) if lower_is_better else (deltas > 0)).sum()),
        "equal_scenarios": int((deltas == 0).sum()),
        "total_scenarios": int(len(deltas)),
    }


def learn_thresholds(
    fiveguard,
    scenarios: list[list[dict]],
    minimum_exposure_reduction: float,
) -> tuple[tuple[float, float, float], list[dict], dict]:
    baseline = _evaluate_policy(fiveguard, scenarios, None, iteration=40)
    baseline_exposure = _mean(baseline, "exposure")
    candidates = threshold_candidates()
    rng = np.random.default_rng(42)
    sampled_indices = set(rng.choice(len(candidates), size=80, replace=False).tolist())
    sampled_indices.add(candidates.index(FIXED_THRESHOLDS))
    evaluations = []
    for index in sorted(sampled_indices):
        candidate = candidates[index]
        rows = _evaluate_policy(fiveguard, scenarios, candidate, iteration=100 + index)
        exposure = _mean(rows, "exposure")
        reduction = (baseline_exposure - exposure) / baseline_exposure
        evaluations.append(
            {
                "thresholds": candidate,
                "mean_profit": _mean(rows, "profit"),
                "mean_exposure": exposure,
                "exposure_reduction": reduction,
            }
        )

    x_train = np.asarray([row["thresholds"] for row in evaluations], dtype=float)
    profit_model = RandomForestRegressor(
        n_estimators=400,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
        oob_score=True,
    ).fit(x_train, [row["mean_profit"] for row in evaluations])
    exposure_model = RandomForestRegressor(
        n_estimators=400,
        min_samples_leaf=2,
        random_state=43,
        n_jobs=-1,
        oob_score=True,
    ).fit(x_train, [row["mean_exposure"] for row in evaluations])
    all_x = np.asarray(candidates, dtype=float)
    predicted_profit = profit_model.predict(all_x)
    predicted_exposure = exposure_model.predict(all_x)
    maximum_exposure = baseline_exposure * (1 - minimum_exposure_reduction)
    feasible_indices = np.flatnonzero(predicted_exposure <= maximum_exposure)
    if len(feasible_indices) == 0:
        raise RuntimeError("ML surrogate predicts no policy satisfying the security constraint")
    best_index = max(
        feasible_indices,
        key=lambda index: (predicted_profit[index], -predicted_exposure[index]),
    )
    selected = candidates[int(best_index)]
    metadata = {
        "model": "RandomForestRegressor",
        "sampled_candidates": len(evaluations),
        "total_candidates": len(candidates),
        "profit_oob_r2": float(profit_model.oob_score_),
        "exposure_oob_r2": float(exposure_model.oob_score_),
        "predicted_profit": float(predicted_profit[best_index]),
        "predicted_exposure": float(predicted_exposure[best_index]),
    }
    return selected, evaluations, metadata


def _plot(result: dict, path: Path) -> None:
    policies = ["Static 5Guard", "Fixed SecGuard", "Learned SecGuard"]
    keys = ["static", "fixed", "learned"]
    colors = ["#777777", "#1f77b4", "#2ca02c"]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for axis, metric, title, ylabel in (
        (axes[0], "profit", "Mean raw profit", "Higher is better"),
        (axes[1], "exposure", "Mean isolation exposure", "Lower is safer"),
    ):
        values = [result["test"][key][metric]["mean"] for key in keys]
        errors = [
            result["test"][key][metric]["ci95_high"] - value
            for key, value in zip(keys, values)
        ]
        bars = axis.bar(policies, values, yerr=errors, capsize=4, color=colors)
        axis.bar_label(bars, labels=[f"{value:.2f}" for value in values], padding=5)
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.tick_params(axis="x", rotation=12)
        axis.spines[["top", "right"]].set_visible(False)
    admission = [result["test"][key]["admitted"]["mean"] for key in keys]
    bars = axes[2].bar(policies, admission, color=colors)
    axes[2].bar_label(bars, labels=[f"{value:.2f}" for value in admission], padding=5)
    axes[2].set_title("Mean admitted slices")
    axes[2].set_ylabel("Higher is better")
    axes[2].tick_params(axis="x", rotation=12)
    axes[2].spines[["top", "right"]].set_visible(False)
    fig.suptitle("Offline-learned SecGuard policy on held-out scenarios")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run_learning(
    data_dir: Path,
    model_file: Path,
    external_dir: Path,
    output_file: Path,
    train_seeds: range,
    test_seeds: range,
    minimum_exposure_reduction: float,
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

    with _working_directory(external_dir.resolve()):
        learned_thresholds, candidates, surrogate = learn_thresholds(
            fiveguard, training_scenarios, minimum_exposure_reduction
        )
        static_rows = _evaluate_policy(fiveguard, test_scenarios, None, iteration=500)
        fixed_rows = _evaluate_policy(
            fiveguard, test_scenarios, FIXED_THRESHOLDS, iteration=501
        )
        learned_rows = _evaluate_policy(
            fiveguard, test_scenarios, learned_thresholds, iteration=502
        )

    static = _summary(static_rows)
    fixed = _summary(fixed_rows)
    learned = _summary(learned_rows)
    learned_profit_gain = (
        learned["profit"]["mean"] - fixed["profit"]["mean"]
    ) / abs(fixed["profit"]["mean"])
    learned_exposure_reduction = (
        static["exposure"]["mean"] - learned["exposure"]["mean"]
    ) / static["exposure"]["mean"]
    result = {
        "method": "offline_constrained_threshold_policy_learning",
        "fixed_thresholds": {
            "l1": FIXED_THRESHOLDS[0],
            "l2": FIXED_THRESHOLDS[1],
            "quarantine": FIXED_THRESHOLDS[2],
        },
        "learned_thresholds": {
            "l1": learned_thresholds[0],
            "l2": learned_thresholds[1],
            "quarantine": learned_thresholds[2],
        },
        "training": {
            "scenarios": len(training_scenarios),
            "evaluated_candidates": len(candidates),
            "minimum_exposure_reduction": minimum_exposure_reduction,
            "surrogate": surrogate,
        },
        "testing": {"scenarios": len(test_scenarios), "seeds": list(test_seeds)},
        "test": {"static": static, "fixed": fixed, "learned": learned},
        "improvement": {
            "profit_over_fixed_secguard": learned_profit_gain,
            "exposure_reduction_vs_static": learned_exposure_reduction,
            "profit_change_vs_static": (
                learned["profit"]["mean"] - static["profit"]["mean"]
            )
            / abs(static["profit"]["mean"]),
            "admission_over_fixed_secguard": (
                learned["admitted"]["mean"] - fixed["admitted"]["mean"]
            )
            / fixed["admitted"]["mean"],
            "exposure_change_vs_fixed_secguard": (
                learned["exposure"]["mean"] - fixed["exposure"]["mean"]
            )
            / fixed["exposure"]["mean"],
            "quarantine_reduction_vs_fixed_secguard": (
                fixed["quarantined"]["mean"] - learned["quarantined"]["mean"]
            )
            / fixed["quarantined"]["mean"],
            "paired_profit_vs_fixed": _paired_summary(
                fixed_rows, learned_rows, "profit"
            ),
            "paired_exposure_vs_static": _paired_summary(
                static_rows, learned_rows, "exposure", lower_is_better=True
            ),
        },
        "limitations": [
            "Risk scenarios bootstrap one held-out dataset and are not cross-dataset validation.",
            "Thresholds are learned on synthetic-topology IAR feedback, not the full 5Guard ensemble.",
            "Exposure uses an isolation-level proxy rather than measured attack propagation.",
        ],
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    plot_file = output_file.with_name("learned_policy_comparison.png")
    result["artifacts"] = {"comparison_plot": str(plot_file)}
    _plot(result, plot_file)
    output_file.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("learned thresholds:", learned_thresholds)
    print("policy             mean profit  mean exposure  mean admitted")
    for name, summary in (("static_5guard", static), ("fixed_secguard", fixed), ("learned_secguard", learned)):
        print(
            f"{name:<18} {summary['profit']['mean']:<12.3f} "
            f"{summary['exposure']['mean']:<14.4f} {summary['admitted']['mean']:.2f}"
        )
    print(f"profit gain over fixed SecGuard: {learned_profit_gain:.2%}")
    print(f"exposure reduction vs static: {learned_exposure_reduction:.2%}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--model-file", type=Path, default=Path("artifacts/risk_model.joblib"))
    parser.add_argument("--external-dir", type=Path, default=Path("external/5guard"))
    parser.add_argument(
        "--output-file", type=Path, default=Path("artifacts/learned_policy.json")
    )
    parser.add_argument("--train-scenarios", type=int, default=5)
    parser.add_argument("--test-scenarios", type=int, default=30)
    parser.add_argument("--minimum-exposure-reduction", type=float, default=0.60)
    args = parser.parse_args()
    run_learning(
        args.data_dir,
        args.model_file,
        args.external_dir,
        args.output_file,
        train_seeds=range(100, 100 + args.train_scenarios),
        test_seeds=range(1000, 1000 + args.test_scenarios),
        minimum_exposure_reduction=args.minimum_exposure_reduction,
    )


if __name__ == "__main__":
    main()
