"""Generate an evidence-linked replay report and paired seed-level intervals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from secguard.online_selector import save_figure


def paired_seed_intervals(decisions: list[dict], reference: str) -> dict:
    seeds = sorted({r["seed"] for r in decisions})
    groups = {}
    for policy in ("performance_selector", reference):
        groups[policy] = []
        for seed in seeds:
            rows = [r for r in decisions if r["seed"] == seed and r["policy"] == policy]
            groups[policy].append({
                "profit": max(rows, key=lambda r: r["step"])["profit"],
                "latency": float(np.mean([r["wall_seconds"] for r in rows])),
            })
    rng = np.random.default_rng(42)
    bootstrap_indices = rng.integers(0, len(seeds), size=(10_000, len(seeds)))
    result = {}
    for metric in ("profit", "latency"):
        differences = np.asarray([a[metric]-b[metric] for a, b in zip(groups["performance_selector"], groups[reference])])
        means = differences[bootstrap_indices].mean(axis=1)
        result[metric] = {
            "mean_paired_delta": float(differences.mean()),
            "bootstrap_ci95": np.quantile(means, [0.025, 0.975]).tolist(),
            "seeds": len(seeds),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("artifacts/objective3_online/results.json"))
    args = parser.parse_args()
    result = json.loads(args.results.read_text(encoding="utf-8"))
    summaries, comparisons, design = result["summaries"], result["comparisons"], result["design"]
    save_figure(summaries, args.results.parent / "comparison.png")
    seed_arguments = " ".join(
        f"--{label}-seeds " + " ".join(map(str, design[f"{label}_seeds"]))
        for label in ("train", "validation", "test")
    )
    command_arguments = f"--steps {design['steps']} --topology {design['topology']} --solver-seconds {design['solver_seconds']} {seed_arguments} --output-dir {args.results.parent.as_posix()}"
    intervals = {name: paired_seed_intervals(result["decisions"], name) for name in comparisons}
    (args.results.parent / "paired_intervals.json").write_text(json.dumps(intervals, indent=2), encoding="utf-8")
    proposed = summaries["performance_selector"]
    lines = [
        "# Objective 3: Performance-Based Selection and Causal Replay", "",
        "This experiment adds an actual solver replay to the earlier offline selector.",
        "Each policy receives the same requests and maintains its own evolving allocation state.",
        "Training labels come from four candidates evaluated on copies of one common state.", "",
        "## Evaluation design", "",
        f"- Topology: **{design['topology']}**; solver: SCIP; one solver thread.",
        f"- Requests per sequence: **{design['steps']}**.",
        f"- Training seed groups: `{design['train_seeds']}`.",
        f"- Validation seed groups: `{design['validation_seeds']}`; calibration and threshold tuning use separate validation groups when available.",
        f"- Test seed groups: `{design['test_seeds']}`; **{proposed['decisions']} online decisions per policy**.",
        f"- SCIP optimization limit: {design['solver_seconds']} seconds per call; full elapsed deadline is checked separately.",
        "- The RF + OPT comparator is retrained on the new training data and richer features. It represents the old decision rule, not the exact saved legacy model.",
        "- FGR-style reference: sequentially evaluate four cold-rebuilt candidates and apply the upstream OPT-priority rule.",
        "- Wall-clock timing includes features, prediction, copying, model reconstruction, allocation, and retries. CPU timing covers the current process.", "",
        "A development pilot used test seeds 300--303 and exposed a mismatch between incremental-profit gating and the total-profit oracle. After correcting that rule, gates were selected again using validation data and the reported final replay used fresh seeds 400--405. Pilot artifacts are retained locally outside the final report directory.", "",
        "## Implemented changes", "",
        "1. Actual request/graph-size features and placement-based load proxies, replacing fixed service profiles alone.",
        "2. Extra-Trees prediction of each candidate's log-runtime, incremental profit, and completion-success score.",
        "3. Sigmoid completion-score calibration where calibration data contain both outcome classes; validation-only selection of quality and feasibility gates.",
        "4. Ranking candidates by predicted time subject to predicted quality and feasibility; at most one retry if predicted remaining deadline permits.",
        "5. Consistent same-state candidate collection, followed by causal online evaluation on disjoint test seeds.",
        "6. Isolated temporary solver models, explicit error records, and a check that profit cannot exceed admitted revenue.", "",
        "The cold-rebuild adapter marks all requests as requiring constraints, initializes missing shared auxiliary variables, and preserves the local OPT correction that clamps negative numerical violation costs. It is applied in memory; upstream files are not overwritten. The SCIP compatibility layer is tracked in `src/secguard/solver_compat.py`.", "",
        "## Measured online results", "",
        "| Policy | Mean elapsed time (s) | p95 elapsed time (s) | Mean final profit | Admission within deadline | Mean solver calls | Solver errors |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("performance_selector", "rf_opt_fallback", "fgr_sequential", "always_opt", "always_iar"):
        s = summaries[name]
        lines.append(f"| {name} | {s['mean_wall_seconds']:.4f} | {s['p95_wall_seconds']:.4f} | {s['mean_final_profit']:.2f} | {s['admission_deadline_success_rate']:.2%} | {s['mean_solver_calls']:.3f} | {s['solver_errors']} |")
    lines += ["", "Final profit is measured at the end of each policy's own trajectory and then averaged across test seeds. It is not the older mean per-decision profit-quality score.", "", "## Comparison with the sequential FGR-style reference", ""]
    reference = comparisons["fgr_sequential"]
    lines += [
        f"- Mean elapsed-time reduction: **{reference['wall_time_reduction']:.2%}**.",
        f"- Process CPU-time reduction: **{reference['cpu_work_reduction']:.2%}**.",
        f"- Measured solver-call reduction, including retries: **{reference['solver_call_reduction']:.2%}**.",
        f"- Ratio of mean final profits: **{reference['profit_ratio']:.2%}**.",
        f"- Admission-within-deadline change: **{100*reference['success_rate_delta']:+.2f} percentage points**.", "",
        "## Comparison with the RF + OPT rule", "",
    ]
    reference = comparisons["rf_opt_fallback"]
    lines += [
        f"- Mean elapsed-time reduction: **{reference['wall_time_reduction']:.2%}** (negative means slower).",
        f"- Ratio of mean final profits: **{reference['profit_ratio']:.2%}**.",
        f"- Admission-within-deadline change: **{100*reference['success_rate_delta']:+.2f} percentage points**.", "",
        "![Measured causal replay results](comparison.png)", "",
        "Figure: online elapsed time, final trajectory profit, and admission within the total deadline. Every policy includes all arrivals, including failures.", "",
    ]
    if "common_state_audit" in result:
        lines += ["## Held-out common-state selection audit", "", "This diagnostic runs all candidates on common test states after the model is frozen. These additional diagnostic solves are excluded from online policy latency and call counts. Ranking is evaluated before retry.", "", "| Rule | Oracle-label accuracy | Mean bounded quality, all rows | Feasible, all rows | Eligible oracle rows / all rows |", "|---|---:|---:|---:|---:|"]
        for name, row in result["common_state_audit"].items():
            accuracy = f"{row['oracle_label_accuracy']:.2%}" if row['oracle_label_accuracy'] is not None else "unavailable"
            lines.append(f"| {name} | {accuracy} | {row['mean_quality_all_rows']:.2%} | {row['feasibility_all_rows']:.2%} | {row['oracle_eligible_rows']} / {row['all_rows']} |")
        lines += ["", "Rows where no candidate is feasible have no oracle algorithm label; they remain in quality and success denominators with zero score. These audit rows differ from the legacy 329-row test set, so new accuracy must not be described as a direct improvement from 66.57%.", "", "The common-state audit follows separate behavior trajectories and evaluates only the first ranked solver. Its feasibility/quality figures therefore differ from the actual online trajectories with bounded retry. They expose limitations on states beyond the selector's own trajectory.", ""]
    lines += ["## Uncertainty and limits", ""]
    for reference in ("fgr_sequential", "rf_opt_fallback"):
        summary = intervals[reference]
        for metric, units in (("latency", "seconds"), ("profit", "profit units")):
            row = summary[metric]
            low, high = row["bootstrap_ci95"]
            lines.append(f"- Proposed minus {reference}, {metric}: mean paired delta {row['mean_paired_delta']:.4f} {units}; seed-level bootstrap 95% interval [{low:.4f}, {high:.4f}].")
    lines += ["", "The intervals resample whole test seeds. With only a few short sequences, they are descriptive and do not establish broad generalization.", ""]
    lines += [f"- {limitation}" for limitation in result["limitations"]]
    lines += [
        "- This comparison does not establish superiority over the upstream parallel ensemble. Cold rebuilding corrects missing cached constraints but adds overhead to every policy, especially the four-candidate reference.",
        "- Legacy numbers (66.57% accuracy, 23.44% estimated solver-work reduction, 0.7523 s stored FGR time) use a different dataset, timing definition, and solver path. They are not directly comparable to this benchmark.",
        "- Broader BRAIN/topology, long-horizon, load, and repeated-run evaluation remains necessary.", "",
        "## Reproduction", "", "```powershell",
        f"python -m secguard.online_selector {command_arguments}",
        f"python -m secguard.online_selector {command_arguments} --audit-only",
        f"python scripts/report_objective3_online.py --results {args.results.as_posix()}",
        "```", "", "For custom seeds/topology/solver limits, pass the values in `results.json` explicitly; audit arguments must match the original experiment.", "",
        "Evidence: `results.json`, `training.json`, `validation.json`, `test_common_state.json`, and `paired_intervals.json` in this directory.",
    ]
    (args.results.parent / "README.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(f"Wrote report and paired intervals to {args.results.parent}")


if __name__ == "__main__":
    main()
