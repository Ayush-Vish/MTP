# Milestone 1 results

Run date: 2026-08-14

## Held-out packet classification

The model was trained on the dataset-provided training subsets and evaluated on
the separate dataset-provided test file.

| Metric | Result |
|---|---:|
| Training rows | 30,288 |
| Held-out test rows | 3,787 |
| Features | 44 |
| Attack prevalence (test) | 21.12% |
| Accuracy | 100.00% |
| Precision (attack) | 100.00% |
| Recall (attack) | 100.00% |
| F1 (attack) | 100.00% |
| PR-AUC | 100.00% |
| False-positive rate | 0.00% |

Confusion matrix: TN=2,987, FP=0, FN=0, TP=800.

## Trace-driven slice decisions

Each example contains 64 held-out packets. Packet risks are averaged to obtain
the slice risk used by the isolation policy.

| Slice | SLA | Risk | Decision |
|---|---:|---:|---|
| slice-embb-01 | L0 | 0.0000 | KEEP L0 |
| slice-mmtc-07 | L0 | 0.1875 | UPGRADE L1 |
| slice-urllc-03 | L1 | 0.5000 | UPGRADE L2 |
| slice-mc-01 | L2 | 1.0000 | QUARANTINE |

## Interpretation and limitation

The perfect held-out score shows that the initial integration works on the
curated Open5GS/UERANSIM dataset. It must not be presented as proof that the
model generalizes to unseen networks or zero-day attacks. The next scientific
validation should train on this dataset and test on a different 5G dataset or
an unseen attack scenario. The dynamic decisions are not yet connected to
5Guard's resource allocator, so no containment, profit, migration, or resource
efficiency claim is made in this milestone.

