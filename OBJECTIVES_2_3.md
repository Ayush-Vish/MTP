# SecGuard Objectives 2 and 3

This README documents the two decision-intelligence layers added after SecGuard's
threat-to-isolation mapping: learning-based admission control (Objective 2) and
intelligent 5Guard algorithm selection (Objective 3).

## End-to-end workflow

```mermaid
flowchart LR
    A[Slice telemetry] --> B[Objective 1<br/>risk and isolation]
    B --> C[Objective 2<br/>DQN admission control]
    C -->|Reject| D[Decline request]
    C -->|Defer| E[Bounded queue]
    E --> C
    C -->|Admit| F[Objective 3<br/>algorithm selector]
    F --> G[OPT]
    F --> H[IAR]
    F --> I[DTR]
    F --> J[RNR]
    G --> K[5Guard allocation]
    H --> K
    I --> K
    J --> K
    K --> L[Updated network state]
    L --> C
    L --> F
```

## Status at a glance

| Objective | Model | Main held-out result | Status |
|---|---|---|---|
| Objective 2: admission | NumPy DQN | 64.9% more reward than greedy | Synthetic prototype complete |
| Objective 3: solver selection | Random Forest | 75% fewer solver calls and 23.44% less estimated solver work | Offline computational improvement; response target not met |

## Objective 2: learning-based admission control

Objective 2 observes current capacity, request demands, revenue, duration,
isolation, and risk before choosing `ADMIT`, `REJECT`, or bounded `DEFER`.
Capacity-aware action masking prevents the DQN from overcommitting resources.

### Objective 2 results

| Metric | DQN | Greedy | Value density |
|---|---:|---:|---:|
| Mean total reward | **987.47** | 598.71 | 986.75 |
| Security-adjusted profit | **1020.62** | 626.46 | 1018.05 |
| Admitted requests | 18.92 | 12.92 | **20.26** |
| Infeasible admissions | **0.00** | **0.00** | **0.00** |

DQN beats greedy in all 50 held-out episodes. Its small mean advantage over the
value-density heuristic is not statistically established because the paired 95%
confidence interval crosses zero.

![Objective 2 training and evaluation](artifacts/objective2_admission_control.png)

Detailed note: [`objective2.md`](objective2.md)

## Objective 3: intelligent algorithm selection

Objective 3 uses request features and the previous 5Guard state to choose one
solver rather than executing all four ensemble candidates. A low-confidence
prediction falls back to OPT.

![Objective 3 architecture](artifacts/objective3_architecture.png)

### Objective 3 results

| Metric | Result |
|---|---:|
| Held-out decisions | 329 |
| Solver-call reduction vs run-all | **75.00%** |
| Estimated solver-work reduction | **23.44%** |
| Mean profit quality retained | **94.63%** |
| Within-5%-of-best rate | **89.67%** |
| Deadline-feasible selection rate | **95.14%** |
| Response latency vs measured FGR | **+62.77% (slower)** |
| Mean selector inference | **Sub-millisecond** |

The balanced selector improves computation by running one solver rather than
four. A safe 60% confidence profile is also retained: it preserves 95.35% profit
quality while reducing estimated solver work by 14.88%. Response latency still
does not meet the proposed target, so causal online evaluation remains required.

![Objective 3 comparison](artifacts/objective3_algorithm_selector.png)

![Objective 3 computational improvement](artifacts/objective3_computation_tradeoff.png)

Detailed note: [`objective3.md`](objective3.md)

## Reproduce both objectives

```powershell
# Objective 2
python -m secguard.admission_control --episodes 2000 `
  --evaluation-episodes 50 --requests 24 --seed 42

# Objective 3
python -m secguard.algorithm_selector

# Verification
python -m pytest tests -q
```

## Generated artifacts

| Artifact | Purpose |
|---|---|
| `artifacts/objective2_admission_control.json` | Objective 2 numerical evidence |
| `artifacts/objective2_dqn.npz` | Trained admission DQN |
| `artifacts/objective2_admission_control.png` | DQN training and baseline figure |
| `artifacts/objective3_algorithm_selector.json` | Objective 3 numerical evidence |
| `artifacts/objective3_selector.joblib` | Trained meta-selector |
| `artifacts/objective3_algorithm_selector.png` | Latency, quality, and confusion figure |
| `artifacts/objective3_computation_tradeoff.png` | Solver-work, invocation, and quality trade-off |
| `artifacts/objective3_architecture.png` | Objective 3 architecture diagram |

## Research boundaries

Both objectives are reproducible synthetic/offline prototypes. Publication-level
claims require direct 5Guard causal replay, BRAIN or additional topologies,
unseen traffic distributions, and online timing under realistic deployment load.
