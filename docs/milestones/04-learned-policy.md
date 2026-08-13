# Milestone 3B: ML-based profit-aware isolation policy

## Objective

Recover the profit and admission lost by the initial fixed SecGuard thresholds
while preserving a substantial security improvement over static 5Guard.

## Method

The policy has three continuous decision parameters:

- L1 escalation threshold.
- L2 escalation threshold.
- Quarantine threshold.

Training sampled 81 of 165 valid policies. Each sampled policy was evaluated on
five training scenarios using the real 5Guard IAR allocator backed by Gurobi.
Two Random-Forest regressors learned threshold-to-profit and
threshold-to-exposure surfaces. The selected policy maximized predicted profit
subject to at least 60% predicted exposure reduction versus static 5Guard.

The selected thresholds were:

| Threshold | Fixed | ML learned |
|---|---:|---:|
| Upgrade to L1 | 0.15 | 0.30 |
| Upgrade to L2 | 0.40 | 0.35 |
| Quarantine | 0.75 | 0.90 |

The learned controller is less eager to impose L1 or quarantine, but promotes
moderately risky traffic to L2 earlier. This reduces costly unnecessary actions
while retaining strong isolation for significant risks.

## Data separation

- Policy-training risk scenarios bootstrap detector outputs from the two
  dataset-provided training files.
- Final policy evaluation bootstraps outputs only from the official held-out
  test file.
- Training seeds: 100-104.
- Held-out seeds: 1000-1029.
- The chosen thresholds never observe held-out allocation outcomes.

## Surrogate diagnostics

| Model | OOB R-squared |
|---|---:|
| Threshold-to-profit Random Forest | 0.99999 |
| Threshold-to-exposure Random Forest | 0.99288 |

These high scores apply only to the small three-dimensional candidate space.

## Held-out results: 30 scenarios

| Metric | Static 5Guard | Fixed SecGuard | Learned SecGuard |
|---|---:|---:|---:|
| Mean raw profit | 8133.84 | 2776.79 | 7356.28 |
| Mean exposure proxy | 0.7729 | 0.2438 | 0.2542 |
| Mean admitted slices | 3.00 | 2.27 | 2.90 |
| Mean quarantined slices | 0.00 | 1.00 | 0.30 |

### Improved metrics over fixed SecGuard

- Profit: **+164.92%**.
- Admission: **+27.94%**.
- Quarantine frequency: **-70.00%**.
- Exposure: **+4.27%** (worse than fixed but still much safer than static).
- Paired absolute profit gain: **4579.49**, 95% CI **[2206.50, 6952.49]**.
- Profit improved in 22/30 scenarios, tied in 4/30, and decreased in 4/30.

### Security retained versus static 5Guard

- Exposure reduction: **67.12%**.
- Exposure improved in **29/30** paired scenarios, with one tie.
- Learned SecGuard retained **90.44%** of static 5Guard's mean raw profit.

## Verification

```powershell
.\.venv\Scripts\python.exe -m secguard.policy_learning
.\.venv\Scripts\python.exe -m pytest -q
```

Expected tests: `17 passed`.

Evidence:

- `artifacts/learned_policy.json`
- `artifacts/learned_policy_comparison.png`
- `src/secguard/policy_learning.py`
- `tests/test_policy_learning.py`

## Defensible claim

On 30 held-out, trace-derived scenarios using 5Guard IAR's synthetic topology,
the learned threshold controller improved mean profit by 164.92% and admission
by 27.94% relative to fixed SecGuard, while maintaining a 67.12% reduction in
the modeled isolation-exposure proxy relative to static 5Guard.

## Limitations

- Scenarios are bootstrapped from one dataset rather than a second deployment.
- The evaluation uses four slices per scenario.
- IAR and the synthetic topology are used instead of the full ensemble/BRAIN.
- Exposure remains a model-based proxy, not observed attack propagation.
- The 95% intervals are normal-approximation intervals over 30 bootstrap
  scenarios, not independent real-world deployments.

