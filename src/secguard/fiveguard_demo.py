"""Apply saved SecGuard decisions to the real 5Guard ``sr`` input class."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType

from secguard.fiveguard_adapter import adapt_slice_request
from secguard.policy import IsolationDecision


def _load_5guard_data(path: Path) -> ModuleType:
    if not path.exists():
        raise FileNotFoundError(
            f"5Guard data model not found at {path}. Run scripts/fetch_5guard.py."
        )
    spec = importlib.util.spec_from_file_location("fiveguard_data", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load 5Guard data model from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_demo(decisions_file: Path, data_model: Path, output_file: Path) -> list[dict]:
    fiveguard = _load_5guard_data(data_model)
    decisions = json.loads(decisions_file.read_text(encoding="utf-8"))
    output = []

    for item in decisions:
        requested_level = int(item["requested_level"])
        request = fiveguard.sr(
            V_S=[],
            V_R=[],
            E=[],
            gamma=requested_level,
            kappa=0,
            R=100.0,
            rho_B=1.0,
            rho_D=1.0,
            rho_C=1.0,
            rho_K=1.0,
            beta=1.0,
            timeout=5.0,
        )
        decision = IsolationDecision(
            slice_id=item["slice_id"],
            requested_level=requested_level,
            risk_score=float(item["risk_score"]),
            action=item["action"],
            target_level=item["target_level"],
            reason=item["reason"],
        )
        original_revenue = request.R
        result = adapt_slice_request(request, decision)
        row = result.to_dict()
        row["input_unchanged"] = request.gamma == requested_level
        row["non_security_fields_preserved"] = (
            result.quarantined or result.optimizer_request.R == original_revenue
        )
        output.append(row)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print("slice_id          before  action        after  optimizer")
    for row in output:
        after = row["target_isolation"] or "-"
        print(
            f"{row['slice_id']:<17} {row['original_isolation']:<7} "
            f"{row['action']:<13} {after:<6} {str(row['sent_to_optimizer']):<5}"
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--decisions-file",
        type=Path,
        default=Path("artifacts/slice_decisions.json"),
    )
    parser.add_argument(
        "--data-model",
        type=Path,
        default=Path("external/5guard/data.py"),
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("artifacts/fiveguard_adapter.json"),
    )
    args = parser.parse_args()
    run_demo(args.decisions_file, args.data_model, args.output_file)


if __name__ == "__main__":
    main()

