"""Plot DQN versus greedy from saved results without rerunning training."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path,
        default=root / "artifacts/objective2_admission_control.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=root / "artifacts/objective2_dqn_vs_greedy.png",
    )
    args = parser.parse_args()
    evidence = json.loads(args.input.read_text(encoding="utf-8"))
    summaries = evidence["evaluation"]["summaries"]
    policies = ("greedy", "dqn")
    metrics = (
        ("reward", "Total reward", "Reward units per episode"),
        ("security_adjusted_profit", "Security-adjusted profit", "Modeled profit units per episode"),
        ("admitted", "Admitted requests", "Requests per episode"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.8))
    for axis, (metric, title, ylabel) in zip(axes, metrics):
        rows = [summaries[name][metric] for name in policies]
        means = [row["mean"] for row in rows]
        errors = [
            [row["mean"] - row["ci95_low"] for row in rows],
            [row["ci95_high"] - row["mean"] for row in rows],
        ]
        bars = axis.bar(
            ["Greedy", "DQN"], means, yerr=errors, capsize=5,
            color=["#777777", "#1671ad"], width=0.6,
        )
        for bar, row in zip(bars, rows):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                row["ci95_high"] + max(means) * 0.025,
                f"{row['mean']:.2f}", ha="center", fontsize=11,
            )
        gain = (means[1] / means[0] - 1) * 100
        axis.set_title(f"{title}\nDQN improvement: {gain:.2f}%")
        axis.set_ylabel(ylabel)
        axis.set_ylim(0, max(row["ci95_high"] for row in rows) * 1.16)
        axis.spines[["top", "right"]].set_visible(False)
        axis.set_axisbelow(True)
        axis.yaxis.grid(True, alpha=0.18)
    episodes = summaries["dqn"]["episodes"]
    fig.suptitle("Objective 2: DQN versus greedy admission", fontsize=15)
    fig.text(
        0.5, 0.025,
        f"{episodes} paired held-out synthetic episodes | Bars: means; error bars: approximate 95% CIs\n"
        "Both policies recorded zero infeasible admissions. Full baseline evidence is retained in the source JSON.",
        ha="center", fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.12, 1, 0.93))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
