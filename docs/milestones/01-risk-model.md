# Milestone 1: ML risk model and dynamic isolation policy

## Objective

Convert 5G packet/GTP telemetry into an attack probability, aggregate those
probabilities into a slice-level risk, and produce an SLA-safe isolation action.

## Data

- Source: public Open5GS/UERANSIM 5G Intrusion Detection Dataset.
- Training records: 30,288.
- Held-out test records: 3,787.
- Features: 44 numeric IP, TCP, UDP, frame, and GTP fields.
- Test attack prevalence: 21.12%.
- Exact held-out rows found in training: zero.

## Implementation

- Model: Random Forest, 300 trees, maximum depth 18, minimum leaf size 2.
- Imbalance handling: balanced subsample class weights.
- Reproducibility seed: 42.
- Packet decision threshold: 0.5.
- Slice risk: arithmetic mean of packet attack probabilities.
- Isolation thresholds: L1 at 0.15, L2 at 0.40, quarantine at 0.75.

The thresholds are initial engineering values and must later be tuned against
the security/resource trade-off, not merely classifier accuracy.

## Results

| Metric | Value |
|---|---:|
| Accuracy | 1.0000 |
| Attack precision | 1.0000 |
| Attack recall | 1.0000 |
| Attack F1 | 1.0000 |
| ROC-AUC | 1.0000 |
| PR-AUC | 1.0000 |
| False-positive rate | 0.0000 |

Confusion matrix: TN=2,987, FP=0, FN=0, TP=800.

## Demonstrated policy output

| Slice | Requested SLA | Risk | Output |
|---|---:|---:|---|
| eMBB | L0 | 0.0000 | Keep L0 |
| mMTC | L0 | 0.1875 | Upgrade to L1 |
| uRLLC | L1 | 0.5000 | Upgrade to L2 |
| Mission-critical | L2 | 1.0000 | Quarantine |

## Verification

```powershell
.\.venv\Scripts\python.exe scripts\fetch_dataset.py
.\.venv\Scripts\python.exe -m secguard.train
.\.venv\Scripts\python.exe -m secguard.demo
.\.venv\Scripts\python.exe -m pytest -q
```

Expected test output: `5 passed`.

## Evidence

- `artifacts/metrics.json`
- `artifacts/confusion_matrix.png`
- `artifacts/feature_importance.csv`
- `artifacts/slice_decisions.json`

## Research interpretation

This milestone establishes feasibility, not external validity. A perfect result
on one curated source suggests that the scenarios are readily separable. It also
makes cross-dataset or leave-one-attack-out evaluation particularly important.

