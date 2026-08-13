# Milestone 3A: Security-aware 5Guard allocation pilot

## Objective

Verify that SecGuard's dynamic isolation decisions change the output of a real
5Guard allocation run and quantify the initial security/profit trade-off.

## Environment

- 5Guard revision: `adadaccfcb6febfbf9e73eaf83541a9d20e7c5d0`.
- Algorithm: isolation-aware ranking (IAR).
- Topology: 5Guard synthetic topology.
- Optimizer: Gurobi 13.0.2 restricted non-production licence.
- Requests: eMBB, mMTC, uRLLC, and mission-critical.

## Compared policies

1. **Static 5Guard:** original requested L0/L0/L1/L2 levels.
2. **SecGuard:** risk-driven L0/L1/L2/quarantine decisions.

Both receive the same request sequence and ML risk scores.

## Exposure proxy

Until actual cross-slice attack propagation is simulated, the pilot uses:

```text
exposure = sum(attack risk * service impact * sharing factor)
```

Sharing factors are L0=1.0, L1=0.5, L2=0.0, and quarantine=0.0. This metric is
an explicit modeling assumption and will require sensitivity analysis.

## Results

| Metric | Static 5Guard | SecGuard | Change |
|---|---:|---:|---:|
| Exposure proxy | 0.6875 | 0.0938 | -86.36% |
| Raw profit | 2915.9950 | 2740.6860 | -6.01% |
| Admitted | 3 | 2 | -1 |
| Quarantined | 0 | 1 | +1 |
| Final migrations | 1 | 2 | +1 |
| Final violation cost | 0 | 0 | 0 |

The mission-critical attack was quarantined. Upgrading mMTC to L1 made that
request infeasible in this constrained sequence, while upgraded uRLLC at L2 was
admitted. The resulting profit cost is substantially smaller than the modeled
exposure reduction, but those quantities have different units and must not be
subtracted without a justified security-price coefficient.

## Improvement over Milestone 2

Milestone 2 proved interface compatibility only. M3A demonstrates that dynamic
isolation decisions alter actual 5Guard feasibility and economics and exposes
the central research trade-off to optimize.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[fiveguard]"
.\.venv\Scripts\python.exe scripts\fetch_5guard.py
.\.venv\Scripts\python.exe -m secguard.security_experiment
.\.venv\Scripts\python.exe -m pytest -q
```

Evidence:

- `artifacts/security_experiment.json`
- `artifacts/security_tradeoff.png`
- `tests/test_security_metrics.py`

## Limitations

- Only four requests and one deterministic sequence were evaluated.
- IAR was used instead of the complete 5Guard ensemble.
- The synthetic topology was used instead of BRAIN.
- Exposure is a proxy rather than measured attack propagation.
- The sharing factor for L1 is an assumption.
- Sequential smoke-test runtimes contain warm-up and ordering effects and are
  not treated as a performance comparison.

## Next improvement

Run repeated sequences and sweep the L1, L2, and quarantine thresholds. The
desired result is a Pareto frontier identifying policies that retain most of the
86.36% exposure reduction while recovering admission and profit.

