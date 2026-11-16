"""Render report figures from recorded results; no training or solver calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def plot_metrics(result: dict, output: Path) -> None:
    names = ("rf_opt_fallback", "performance_selector", "fgr_sequential")
    labels = ("Previous rule\nRF + OPT", "Current\nperformance selector", "Baseline\nsequential FGR-style")
    colors = ("#527ca5", "#26834a", "#858585")
    summaries = result["summaries"]
    fig, axes = plt.subplots(4, 2, figsize=(12, 15))
    panels = (
        ("mean_wall_seconds", "Mean elapsed time — lower is better", "Seconds per decision", 1, "%.4f"),
        ("mean_final_profit", "Mean final profit — higher is better", "Modeled profit units", 1, "%.2f"),
        ("admission_deadline_success_rate", "Admission within deadline — higher is better", "Percent of 72 online arrivals", 100, "%.2f%%"),
        ("p95_wall_seconds", "p95 elapsed time — lower is better", "Seconds per decision", 1, "%.4f"),
        ("mean_cpu_seconds", "Mean process CPU time — lower is better", "CPU seconds per decision", 1, "%.4f"),
        ("mean_solver_calls", "Actual solver calls — lower is better", "Mean calls per decision, including retries", 1, "%.3f"),
        ("solver_errors", "Recorded solver errors", "Error count; zero for all three policies", 1, "%.0f"),
    )
    for ax, (metric, title, ylabel, scale, fmt) in zip(axes.flat, panels):
        values = [summaries[name][metric]*scale for name in names]
        bars = ax.bar(labels, values, color=colors, width=0.6)
        ax.bar_label(bars, fmt=fmt, padding=4, fontsize=10)
        ax.set(title=title, ylabel=ylabel, ylim=(0, max(values)*1.20 if max(values)>0 else 1))
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, alpha=0.15)
    ax = axes[3, 1]
    audit = result["common_state_audit"]
    values = [100*audit[name]["oracle_label_accuracy"] for name in names[:2]]
    bars = ax.bar(labels[:2], values, color=colors[:2], width=0.5)
    ax.bar_label(bars, fmt="%.2f%%", padding=4, fontsize=10)
    ax.set(title="First-choice oracle-label accuracy", ylabel="Percent of 71 eligible audit states", ylim=(0, 100))
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, alpha=0.15)
    ax.text(0.5, 0.10, "FGR-style oracle-label agreement: 2.82% (table).\nFGR prioritizes OPT; it is not an oracle-label classifier.", transform=ax.transAxes, ha="center", fontsize=9, bbox={"facecolor":"white", "alpha":0.92, "edgecolor":"none", "pad":4})
    fig.suptitle("Objective 3: measured previous-rule, current-selector, and baseline comparison", fontsize=14)
    fig.text(0.5, 0.015, "Online metrics: six synthetic sequences, 72 decisions per policy. Accuracy: separate common-state audit.\nSequential cold-rebuilt reference; native parallel 5Guard and BRAIN are not evaluated here.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.045, 1, 0.97), h_pad=2.5, w_pad=2)
    fig.savefig(output / "approach_comparison.png", dpi=200, bbox_inches="tight")
    fig.savefig(output / "approach_comparison.svg", bbox_inches="tight")
    plt.close(fig)


def plot_architecture(output: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 8.5))
    ax.set(xlim=(0, 14), ylim=(0, 9))
    ax.axis("off")

    def box(x, y, width, height, label, edge="#456780", face="#eef4f8", size=11):
        ax.add_patch(FancyBboxPatch((x, y), width, height, boxstyle="round,pad=0.07", linewidth=1.6, edgecolor=edge, facecolor=face))
        ax.text(x+width/2, y+height/2, label, ha="center", va="center", fontsize=size)

    def arrow(start, end, color="#53616b"):
        ax.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle":"->", "lw":1.7, "color":color})

    ax.text(7, 8.7, "Objective 3: implemented algorithm-selection workflows", ha="center", fontsize=17, weight="bold")
    box(0.55, 7.55, 12.9, 0.65, "Identical incoming requests; each policy has its own evolving allocation state", size=12)
    centers = (2.2, 7, 11.8)
    headers = ("Previous rule: RF + OPT", "Current: performance selector", "Baseline: sequential FGR-style")
    for center, header in zip(centers, headers):
        arrow((center, 7.55), (center, 7.38))
        ax.text(center, 7.12, header, ha="center", fontsize=12, weight="bold")
        arrow((center, 6.98), (center, 6.84))
    lanes = (
        ("27 pre-decision features\nRandom Forest classifier", "Predict one algorithm label\nConfidence < 0.45: choose OPT", "Execute one chosen solver\n1.000 mean calls per decision"),
        ("27 pre-decision features\n128-tree Extra-Trees regressor", "Predict time, profit gain, and\ncompletion score for each candidate\nApply quality and deadline gates", "Execute ranked solver; at most\none budget-aware retry\n1.028 mean calls per decision"),
        ("Execute OPT, IAR, DTR, RNR\nfrom the same pre-decision state", "Apply FGR allocation priority:\nprefer non-timeout OPT, otherwise\nbest non-timeout profit", "Four sequential solver calls\n4.000 calls per decision"),
    )
    for index, (center, lane) in enumerate(zip(centers, lanes)):
        edge = "#26834a" if index == 1 else "#456780"
        face = "#eaf5ed" if index == 1 else "#eef4f8"
        for y, height, label in zip((5.75, 3.95, 2.15), (1.05, 1.2, 1.2), lane):
            box(center-1.95, y, 3.9, height, label, edge, face)
        arrow((center, 5.75), (center, 5.15))
        arrow((center, 3.95), (center, 3.35))
        arrow((center, 2.15), (center, 1.55))
    box(0.55, 0.6, 12.9, 0.8, "Accept only feasible allocations within the total measured deadline; update that policy's next state.\nRecord elapsed time, process CPU time, profit, admissions, actual solver calls, and errors.", size=11)
    ax.text(7, 0.12, "Training collection evaluates all four candidates; inference usually executes one. Reference uses sequential cold rebuilding.", ha="center", fontsize=10)
    fig.tight_layout()
    fig.savefig(output / "selection_workflow.png", dpi=200, bbox_inches="tight")
    fig.savefig(output / "selection_workflow.svg", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=root / "artifacts/objective3_online/results.json")
    args = parser.parse_args()
    result = json.loads(args.results.read_text(encoding="utf-8"))
    plot_metrics(result, args.results.parent)
    plot_architecture(args.results.parent)
    print(f"Rendered comparison and workflow figures from {args.results}")


if __name__ == "__main__":
    main()
