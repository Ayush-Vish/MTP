"""Create trace-driven per-slice risks and dynamic isolation decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from secguard.policy import decide_isolation


LABEL = "label"


def _scenario(
    frame: pd.DataFrame,
    benign_count: int,
    attack_count: int,
    seed: int,
) -> pd.DataFrame:
    benign = frame[frame[LABEL] == 0].sample(benign_count, random_state=seed)
    attack = frame[frame[LABEL] == 1].sample(attack_count, random_state=seed)
    return pd.concat([benign, attack], ignore_index=True).sample(frac=1, random_state=seed)


def run_demo(data_file: Path, model_file: Path, output_file: Path) -> list[dict]:
    frame = pd.read_csv(data_file)
    bundle = joblib.load(model_file)
    model = bundle["model"]
    features = bundle["feature_names"]

    specifications = [
        ("slice-embb-01", "eMBB", 0, 64, 0),
        ("slice-mmtc-07", "mMTC", 0, 52, 12),
        ("slice-urllc-03", "uRLLC", 1, 32, 32),
        ("slice-mc-01", "MC", 2, 0, 64),
    ]
    results = []
    for seed, (slice_id, service, requested_level, benign_count, attack_count) in enumerate(specifications, 10):
        packets = _scenario(frame, benign_count, attack_count, seed)
        probabilities = model.predict_proba(packets[features])[:, 1]
        risk_score = float(probabilities.mean())
        decision = decide_isolation(slice_id, risk_score, requested_level).to_dict()
        decision.update(
            {
                "service": service,
                "packets": int(len(packets)),
                "simulated_attack_fraction": float(attack_count / len(packets)),
            }
        )
        results.append(decision)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    table = pd.DataFrame(results)[
        [
            "slice_id",
            "service",
            "requested_isolation",
            "risk_score",
            "action",
            "target_isolation",
        ]
    ]
    print(table.to_string(index=False, formatters={"risk_score": "{:.4f}".format}))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-file", type=Path, default=Path("data/raw/Test_Data.csv"))
    parser.add_argument("--model-file", type=Path, default=Path("artifacts/risk_model.joblib"))
    parser.add_argument("--output-file", type=Path, default=Path("artifacts/slice_decisions.json"))
    args = parser.parse_args()
    run_demo(args.data_file, args.model_file, args.output_file)


if __name__ == "__main__":
    main()

