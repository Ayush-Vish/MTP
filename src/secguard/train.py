"""Train and evaluate the first SecGuard attack-risk model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


TRAIN_FILES = ("Train_subset_1.csv", "Train_subset_2.csv")
TEST_FILE = "Test_Data.csv"
LABEL = "label"
RANDOM_STATE = 42


def load_data(data_dir: Path) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    missing = [name for name in (*TRAIN_FILES, TEST_FILE) if not (data_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing dataset files: {', '.join(missing)}. Run scripts/fetch_dataset.py first."
        )

    train = pd.concat(
        [pd.read_csv(data_dir / name) for name in TRAIN_FILES], ignore_index=True
    )
    test = pd.read_csv(data_dir / TEST_FILE)
    if LABEL not in train or LABEL not in test:
        raise ValueError(f"Expected a '{LABEL}' column in every dataset file")

    feature_names = [column for column in train.columns if column != LABEL]
    if feature_names != [column for column in test.columns if column != LABEL]:
        raise ValueError("Training and test feature columns do not match")
    return train[feature_names], train[LABEL].astype(int), test[feature_names], test[LABEL].astype(int)


def train_and_evaluate(data_dir: Path, artifacts_dir: Path) -> dict:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    x_train, y_train, x_test, y_test = load_data(data_dir)

    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=18,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )
    model.fit(x_train, y_train)
    attack_probability = model.predict_proba(x_test)[:, 1]
    prediction = (attack_probability >= 0.5).astype(int)

    cm = confusion_matrix(y_test, prediction)
    tn, fp, fn, tp = cm.ravel()
    metrics = {
        "dataset": {
            "train_rows": int(len(x_train)),
            "test_rows": int(len(x_test)),
            "features": int(x_train.shape[1]),
            "train_attack_rate": float(y_train.mean()),
            "test_attack_rate": float(y_test.mean()),
        },
        "model": "RandomForestClassifier",
        "threshold": 0.5,
        "accuracy": float(accuracy_score(y_test, prediction)),
        "precision": float(precision_score(y_test, prediction, zero_division=0)),
        "recall": float(recall_score(y_test, prediction, zero_division=0)),
        "f1": float(f1_score(y_test, prediction, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, attack_probability)),
        "pr_auc": float(average_precision_score(y_test, attack_probability)),
        "false_positive_rate": float(fp / (fp + tn)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "classification_report": classification_report(
            y_test, prediction, target_names=["normal", "attack"], output_dict=True
        ),
    }

    joblib.dump(
        {"model": model, "feature_names": list(x_train.columns), "threshold": 0.5},
        artifacts_dir / "risk_model.joblib",
    )
    (artifacts_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )

    importance = (
        pd.DataFrame({"feature": x_train.columns, "importance": model.feature_importances_})
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )
    importance.to_csv(artifacts_dir / "feature_importance.csv", index=False)

    display = ConfusionMatrixDisplay(cm, display_labels=["Normal", "Attack"])
    display.plot(cmap="Blues", values_format="d")
    plt.title("SecGuard held-out test confusion matrix")
    plt.tight_layout()
    plt.savefig(artifacts_dir / "confusion_matrix.png", dpi=180)
    plt.close()

    print(json.dumps({key: value for key, value in metrics.items() if key != "classification_report"}, indent=2))
    print("\nTop 10 features:")
    print(importance.head(10).to_string(index=False))
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    train_and_evaluate(args.data_dir, args.artifacts_dir)


if __name__ == "__main__":
    main()

