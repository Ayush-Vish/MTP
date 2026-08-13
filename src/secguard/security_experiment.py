"""Run a small static-versus-SecGuard experiment with 5Guard IAR."""

from __future__ import annotations

import argparse
import contextlib
import copy
import importlib
import io
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterator

import numpy as np
import matplotlib.pyplot as plt

from secguard.fiveguard_adapter import adapt_slice_request
from secguard.policy import IsolationDecision
from secguard.security_metrics import (
    ExposureObservation,
    exposure_reduction,
    isolation_exposure,
)


SERVICE_INDEX = {"eMBB": 0, "uRLLC": 1, "mMTC": 2, "MC": 3}
SERVICE_IMPACT = {"eMBB": 1.0, "mMTC": 1.0, "uRLLC": 2.0, "MC": 3.0}


@contextlib.contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _load_fiveguard(external_dir: Path) -> Any:
    absolute = external_dir.resolve()
    if not (absolute / "libraries.py").exists():
        raise FileNotFoundError("5Guard not found. Run scripts/fetch_5guard.py first.")
    sys.path.insert(0, str(absolute))
    try:
        with _working_directory(absolute), contextlib.redirect_stdout(io.StringIO()):
            return importlib.import_module("libraries")
    finally:
        sys.path.remove(str(absolute))


def _number(value: Any) -> float:
    return float(np.asarray(value, dtype=float).sum())


def _prepare_backup(fiveguard: Any, iteration: int) -> None:
    Path("saved_model").mkdir(parents=True, exist_ok=True)
    model = fiveguard.gp.Model(f"secguard_{iteration}")
    model.Params.OutputFlag = 0
    model.write(f"saved_model/model_backup_iar_{iteration}.mps")


def _decision_from_json(item: dict) -> IsolationDecision:
    return IsolationDecision(
        slice_id=item["slice_id"],
        requested_level=int(item["requested_level"]),
        risk_score=float(item["risk_score"]),
        action=item["action"],
        target_level=item["target_level"],
        reason=item["reason"],
    )


def _run_policy(
    fiveguard: Any,
    specifications: list[dict],
    adaptive: bool,
    iteration: int,
) -> dict:
    topology = fiveguard.init_setup_synth()
    request_types = fiveguard.create_sr_resources()
    _prepare_backup(fiveguard, iteration)

    active_requests: list[Any] = []
    x_state: list = []
    y_state: list = []
    previous_profit = 0.0
    allocation_seconds = 0.0
    admitted = 0
    quarantined = 0
    last_result = None
    steps = []

    for time_step, item in enumerate(specifications):
        request = copy.deepcopy(request_types[SERVICE_INDEX[item["service"]]])
        decision = _decision_from_json(item)
        target_gamma = request.gamma

        if adaptive:
            adapted = adapt_slice_request(request, decision)
            if adapted.quarantined:
                quarantined += 1
                steps.append(
                    {
                        "slice_id": item["slice_id"],
                        "status": "quarantined",
                        "gamma": None,
                    }
                )
                continue
            request = adapted.optimizer_request
            target_gamma = request.gamma

        with contextlib.redirect_stdout(io.StringIO()):
            result, candidate_x, candidate_y = fiveguard.iar_iter(
                previous_profit,
                iteration,
                time_step,
                request,
                active_requests,
                *topology,
                0,
                x_state,
                y_state,
            )

        feasible = int(result[8]) == 1
        allocation_seconds += float(result[7])
        if feasible:
            admitted += 1
            previous_profit = float(result[0])
            active_requests = result[10]
            x_state = candidate_x
            y_state = candidate_y
            last_result = result
        steps.append(
            {
                "slice_id": item["slice_id"],
                "status": "admitted" if feasible else "rejected",
                "gamma": int(target_gamma),
                "profit": float(previous_profit),
                "allocation_seconds": float(result[7]),
            }
        )

    summary = {
        "policy": "secguard" if adaptive else "static_5guard",
        "requests": len(specifications),
        "admitted": admitted,
        "quarantined": quarantined,
        "final_profit": float(previous_profit),
        "allocation_seconds": allocation_seconds,
        "steps": steps,
    }
    if last_result is not None:
        summary.update(
            {
                "final_violation_cost": _number(last_result[1]),
                "final_migrations": _number(last_result[2]),
                "final_deployment_cost": _number(last_result[3]),
                "final_overhead_cost": _number(last_result[4]),
                "mean_resource_efficiency": float(np.asarray(last_result[5]).mean()),
            }
        )
    return summary


def _exposure(specifications: list[dict], adaptive: bool) -> float:
    observations = []
    for item in specifications:
        level = int(item["requested_level"])
        if adaptive:
            level = item["target_level"]
        observations.append(
            ExposureObservation(
                slice_id=item["slice_id"],
                risk_score=float(item["risk_score"]),
                impact=SERVICE_IMPACT[item["service"]],
                isolation_level=level,
            )
        )
    return isolation_exposure(observations)


def _save_tradeoff_plot(result: dict, path: Path) -> None:
    labels = ["Static 5Guard", "SecGuard"]
    colors = ["#777777", "#1f77b4"]
    exposure = [
        result["exposure_metric"]["baseline"],
        result["exposure_metric"]["secguard"],
    ]
    profit = [result["baseline"]["final_profit"], result["secguard"]["final_profit"]]
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    for axis, values, title, ylabel, fmt in (
        (axes[0], exposure, "Isolation exposure proxy", "Lower is safer", "{:.3f}"),
        (axes[1], profit, "Raw 5Guard profit", "Profit", "{:.1f}"),
    ):
        bars = axis.bar(labels, values, color=colors)
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.bar_label(bars, labels=[fmt.format(value) for value in values], padding=3)
        axis.spines[["top", "right"]].set_visible(False)
    fig.suptitle("SecGuard pilot: security gain versus allocation cost")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run_experiment(
    decisions_file: Path,
    external_dir: Path,
    output_file: Path,
) -> dict:
    specifications = json.loads(decisions_file.read_text(encoding="utf-8"))
    fiveguard = _load_fiveguard(external_dir)
    with _working_directory(external_dir.resolve()):
        with contextlib.redirect_stdout(io.StringIO()):
            baseline = _run_policy(fiveguard, specifications, adaptive=False, iteration=20)
            proposed = _run_policy(fiveguard, specifications, adaptive=True, iteration=21)

    baseline_exposure = _exposure(specifications, adaptive=False)
    proposed_exposure = _exposure(specifications, adaptive=True)
    result = {
        "experiment": "synthetic_topology_iar_four_requests",
        "exposure_metric": {
            "name": "isolation_exposure_proxy",
            "formula": "sum(risk * service_impact * sharing_factor)",
            "sharing_factor": {"L0": 1.0, "L1": 0.5, "L2": 0.0, "quarantine": 0.0},
            "baseline": baseline_exposure,
            "secguard": proposed_exposure,
            "reduction": exposure_reduction(baseline_exposure, proposed_exposure),
        },
        "baseline": baseline,
        "secguard": proposed,
        "delta": {
            "profit": proposed["final_profit"] - baseline["final_profit"],
            "admitted": proposed["admitted"] - baseline["admitted"],
            "allocation_seconds": proposed["allocation_seconds"] - baseline["allocation_seconds"],
        },
        "limitations": [
            "Four-request feasibility experiment; not statistically representative.",
            "Exposure is an isolation-level proxy, not measured attack propagation.",
            "Uses IAR on the synthetic topology, not the full 5Guard ensemble or BRAIN topology.",
            "Sequential smoke-test runtimes include order and warm-up effects and are not compared as a performance claim.",
        ],
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    plot_file = output_file.with_name("security_tradeoff.png")
    result["artifacts"] = {"tradeoff_plot": str(plot_file)}
    _save_tradeoff_plot(result, plot_file)
    output_file.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("policy        admitted  quarantined  profit       exposure")
    print(
        f"static_5guard {baseline['admitted']:<9} {baseline['quarantined']:<12} "
        f"{baseline['final_profit']:<12.4f} {baseline_exposure:.4f}"
    )
    print(
        f"secguard      {proposed['admitted']:<9} {proposed['quarantined']:<12} "
        f"{proposed['final_profit']:<12.4f} {proposed_exposure:.4f}"
    )
    print(f"exposure reduction: {result['exposure_metric']['reduction']:.2%}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--decisions-file", type=Path, default=Path("artifacts/slice_decisions.json")
    )
    parser.add_argument(
        "--external-dir", type=Path, default=Path("external/5guard")
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("artifacts/security_experiment.json"),
    )
    args = parser.parse_args()
    run_experiment(args.decisions_file, args.external_dir, args.output_file)


if __name__ == "__main__":
    main()
