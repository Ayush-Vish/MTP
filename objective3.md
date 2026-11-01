# Objective 3: Intelligent Algorithm Selection

## Objective

Objective 3 replaces 5Guard's run-all ensemble with a lightweight meta-selector.
For each admitted slice, the selector predicts one algorithm from `OPT`, `IAR`,
`DTR`, and `RNR` using request complexity and the previous network state. The
goal is to reduce allocation latency without materially sacrificing profit or
deadline feasibility.

## Implementation

The current research prototype uses a 400-tree Random Forest trained on measured
per-step outcomes from the existing 5Guard reproduction. Its 22 input features
contain only information available before the current allocation:

- service type, isolation, CPU, radio, bandwidth, revenue, and deadline;
- time within the simulation and the recent service-arrival mix; and
- previous profit, migration, latency, violation, overhead, resource-efficiency,
  and rejection state.

The training label is the fastest deadline-feasible algorithm whose observed
profit is within 5% of the best feasible candidate. The default balanced profile
falls back to `OPT` below 45% confidence. A separate safe profile uses a 60%
threshold when profit retention is more important than computation reduction.

Training uses complete simulation groups: iterations 0--6 train the selector,
while iterations 7--9 remain held out. Rows from the same simulation are never
randomly split between training and evaluation.

## Architecture

![Objective 3 architecture](artifacts/objective3_architecture.png)

## Reproduction

```powershell
python -m secguard.algorithm_selector
```

This command reads the existing synthetic 5Guard traces from
`external/5guard/saved_data/synthetic/`, trains the selector, evaluates all
baselines, and regenerates the model, JSON evidence, figure, and diagram.

## Held-out results

The evaluation contains 329 deadline-feasible decision points from held-out
simulation iterations 7--9.

| Policy | Mean solver time (s) | Mean profit retained | Feasibility/deadline rate |
|---|---:|---:|---:|
| Balanced selector (45%) | **1.2245** | 94.63% | 95.14% |
| Safe selector (60%) | 1.3615 | 95.35% | 95.44% |
| Always OPT | 1.3760 | **96.05%** | **96.05%** |
| Always IAR | **0.0087** | 33.44% | 51.98% |
| Always RNR / training majority | 0.1104 | 78.67% | 79.64% |
| Quality-constrained oracle | 0.8209 | 99.82% | 100.00% |

Measured FGR/5Guard latency was 0.7523 seconds per decision. For context, the
independent candidate trajectories give a counterfactual parallel wait of
1.3760 seconds and a counterfactual sequential sum of 1.5994 seconds. These are
not causal measurements of the FGR trajectory. The balanced selector therefore:

- executed **one solver instead of four**, a **75.00% reduction in solver calls**;
- reduced estimated solver work by **23.44%** versus the independent run-all sum;
- was 11.01% faster than always selecting OPT on the independent trajectories;
- retained **94.63%** of the best observed profit on average;
- placed **89.67%** of selections within the 5% profit-loss budget;
- achieved **95.14%** deadline-feasible selections;
- was still **62.77% slower** than measured FGR response latency; and
- recorded 1.34 ms of inference timing per held-out row, including both the
  balanced and safe prediction batches (not single-request online timing).

The safe 60% profile reduces estimated solver work by 14.88% while retaining
95.35% profit quality. The balanced and safe profiles now establish computation
improvements, but neither meets the original 90% response-latency aspiration or
yet justifies replacing measured FGR execution.

![Objective 3 held-out results](artifacts/objective3_algorithm_selector.png)

![Objective 3 computation trade-off](artifacts/objective3_computation_tradeoff.png)

## Evidence and verification

- Implementation: `src/secguard/algorithm_selector.py`
- Unit tests: `tests/test_algorithm_selector.py`
- Metrics: `artifacts/objective3_algorithm_selector.json`
- Trained model: `artifacts/objective3_selector.joblib`
- Result figure: `artifacts/objective3_algorithm_selector.png`
- Computation figure: `artifacts/objective3_computation_tradeoff.png`
- Architecture diagram: `artifacts/objective3_architecture.png`
- Complete project test suite: **38 tests passed**

## Limitations and next work

- Counterfactual candidate outcomes come from independent algorithm trajectories,
  not a single causal replay trajectory.
- Training and testing use one topology and one seeded traffic generator.
- The confidence fallback protects quality but substantially limits latency gain.
- BRAIN-topology evaluation, direct online integration, probability calibration,
  and broader workload validation remain necessary before claiming generalization.
