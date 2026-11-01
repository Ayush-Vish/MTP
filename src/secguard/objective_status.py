"""Machine-checkable completion gate for the three SecGuard objectives.

This module deliberately distinguishes prototype completion from journal-level
external validation.  It reads the committed experiment artifacts, applies the
acceptance criteria documented in ``OBJECTIVE_STATUS.md``, and writes a compact
JSON report that can be checked before updating a report or manuscript.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable


Comparator = Callable[[float, float], bool]


def _criterion(
    name: str,
    value: float,
    threshold: float,
    operator: str,
    source: str,
) -> dict[str, Any]:
    comparators: dict[str, Comparator] = {
        ">=": lambda observed, target: observed >= target,
        "<=": lambda observed, target: observed <= target,
        ">": lambda observed, target: observed > target,
        "==": lambda observed, target: observed == target,
    }
    if operator not in comparators:
        raise ValueError(f"Unsupported comparison operator: {operator}")
    return {
        "name": name,
        "value": float(value),
        "operator": operator,
        "threshold": float(threshold),
        "passed": bool(comparators[operator](float(value), float(threshold))),
        "source": source,
    }


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"Required objective artifact not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def assess_objectives(project_root: Path) -> dict[str, Any]:
    """Assess prototype completion from the three committed result artifacts."""

    artifacts = project_root / "artifacts"
    objective1 = _read_json(artifacts / "research_validation.json")
    adapter = _read_json(artifacts / "fiveguard_adapter.json")
    objective2 = _read_json(artifacts / "objective2_admission_control.json")
    objective3 = _read_json(artifacts / "objective3_algorithm_selector.json")

    learned = objective1["test"]["learned"]
    static = objective1["test"]["static"]
    fixed = objective1["test"]["fixed"]
    exposure_reduction = 1.0 - (
        learned["exposure"]["mean"] / static["exposure"]["mean"]
    )
    profit_retention = learned["profit"]["mean"] / static["profit"]["mean"]
    profit_gain_vs_fixed = (
        learned["profit"]["mean"] / fixed["profit"]["mean"] - 1.0
    )
    sla_floor_violations = sum(
        1
        for row in adapter
        if row["target_gamma"] is not None
        and row["target_gamma"] < row["original_gamma"]
    )
    input_mutations = sum(not row["input_unchanged"] for row in adapter)
    objective1_criteria = [
        _criterion(
            "isolation-exposure reduction versus static 5Guard",
            exposure_reduction,
            0.60,
            ">=",
            "artifacts/research_validation.json",
        ),
        _criterion(
            "profit retained versus static 5Guard",
            profit_retention,
            0.85,
            ">=",
            "artifacts/research_validation.json",
        ),
        _criterion(
            "profit gain versus fixed SecGuard",
            profit_gain_vs_fixed,
            0.0,
            ">",
            "artifacts/research_validation.json",
        ),
        _criterion(
            "adapter SLA-floor violations",
            sla_floor_violations,
            0.0,
            "==",
            "artifacts/fiveguard_adapter.json",
        ),
        _criterion(
            "mutated input requests",
            input_mutations,
            0.0,
            "==",
            "artifacts/fiveguard_adapter.json",
        ),
    ]

    summaries = objective2["evaluation"]["summaries"]
    comparisons = objective2["evaluation"]["paired_comparisons"]
    dqn_reward = summaries["dqn"]["reward"]["mean"]
    greedy_reward = summaries["greedy"]["reward"]["mean"]
    objective2_criteria = [
        _criterion(
            "DQN reward gain versus greedy",
            dqn_reward / greedy_reward - 1.0,
            0.20,
            ">=",
            "artifacts/objective2_admission_control.json",
        ),
        _criterion(
            "paired DQN wins versus greedy",
            comparisons["dqn_vs_greedy"]["wins"],
            40.0,
            ">=",
            "artifacts/objective2_admission_control.json",
        ),
        _criterion(
            "mean infeasible DQN admissions",
            summaries["dqn"]["infeasible"]["mean"],
            0.0,
            "==",
            "artifacts/objective2_admission_control.json",
        ),
    ]

    computation = objective3["evaluation"]["computation"]["balanced"]
    selector = objective3["evaluation"]["policies"]["selector"]
    objective3_criteria = [
        _criterion(
            "solver-call reduction versus run-all",
            computation["solver_call_reduction"],
            0.75,
            ">=",
            "artifacts/objective3_algorithm_selector.json",
        ),
        _criterion(
            "estimated solver-work reduction versus run-all",
            computation["solver_work_reduction"],
            0.10,
            ">=",
            "artifacts/objective3_algorithm_selector.json",
        ),
        _criterion(
            "mean profit quality retained",
            selector["mean_quality_retention"],
            0.90,
            ">=",
            "artifacts/objective3_algorithm_selector.json",
        ),
        _criterion(
            "deadline-feasible selection rate",
            selector["deadline_success_rate"],
            0.90,
            ">=",
            "artifacts/objective3_algorithm_selector.json",
        ),
    ]

    objectives = []
    for number, title, criteria, scope in (
        (
            1,
            "Intelligent security-to-isolation mapping",
            objective1_criteria,
            "within-source, trace-derived synthetic evaluation",
        ),
        (
            2,
            "Learning-based admission control",
            objective2_criteria,
            "capacity-safe synthetic admission environment",
        ),
        (
            3,
            "Intelligent algorithm selection",
            objective3_criteria,
            "offline synthetic 5Guard traces; computation criterion",
        ),
    ):
        objectives.append(
            {
                "objective": number,
                "title": title,
                "prototype_complete": all(row["passed"] for row in criteria),
                "scope": scope,
                "criteria": criteria,
            }
        )

    prototype_complete = all(row["prototype_complete"] for row in objectives)
    return {
        "status": (
            "all_objectives_prototype_complete"
            if prototype_complete
            else "objective_acceptance_failed"
        ),
        "prototype_complete": prototype_complete,
        "journal_validation_complete": False,
        "objectives": objectives,
        "journal_validation_gaps": [
            "external or cross-dataset threat-detection validation",
            "direct causal integration of admission and selection with 5Guard",
            "multi-seed BRAIN-topology evaluation for all proposed components",
            "measured attack propagation or containment rather than an exposure proxy",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/objective_status.json"),
    )
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    root = args.project_root.resolve()
    report = assess_objectives(root)
    if not args.no_write:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for objective in report["objectives"]:
        marker = "PASS" if objective["prototype_complete"] else "FAIL"
        print(f"Objective {objective['objective']}: {marker} - {objective['title']}")
        for criterion in objective["criteria"]:
            result = "PASS" if criterion["passed"] else "FAIL"
            print(
                f"  [{result}] {criterion['name']}: {criterion['value']:.6g} "
                f"{criterion['operator']} {criterion['threshold']:.6g}"
            )
    print(f"Prototype completion: {report['prototype_complete']}")
    print(f"Journal validation completion: {report['journal_validation_complete']}")
    raise SystemExit(0 if report["prototype_complete"] else 1)


if __name__ == "__main__":
    main()
