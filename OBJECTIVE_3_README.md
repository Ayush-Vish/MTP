
# Objective 3 — Learned Solver Selection for 5Guard


Objective 3 develops a learned solver-selection framework that dynamically chooses allocation solvers for incoming network slice requests. The objective is to reduce computational overhead, solver execution time, and decision latency while maintaining high admission rates and improving overall allocation profitability.

## What We Built

1. **Common-state measurement.** We evaluated OPT, IAR, DTR, and RNR on identical allocation-state snapshots to collect candidate runtime, feasibility, and incremental profit. Each policy independently committed feasible allocations and maintained its own allocation state.
2. **Extra-Trees performance selector.** We developed a learning-based selector using 27 request, topology, and allocation-state features to predict solver runtime, allocation profit, and completion probability. Deadline-aware and quality-aware constraints were incorporated, with one optional retry when sufficient time remained. Implementation · Replay
3. **Ranker and cascade experiments.** We explored CatBoost-based solver ranking and a learned OPT/IAR cascade to determine the most suitable solver execution order. Both approaches were evaluated against their respective baselines on synthetic request sequences. CatBoost results · Cascade results
4. **Load-adaptive and guarded contextual selection.** The load portfolio selects solver execution plans based on the active network-slice count. The contextual selector additionally considers isolation requirements and active slice counts by isolation class. It supports single-solver execution, retry-based execution, parallel solver execution, and early rejection of infeasible requests. Load portfolio · Contextual policy
5. **Matched parallel replay.** We evaluated the proposed policies against the parallel 5Guard reference implementation using a consistent SCIP backend, identical request sequences, and matched execution deadlines. The reference executes four allocation solvers in parallel and selects the highest-profit feasible solution returned before the deadline. Benchmark runner

## Main Results — Three Full Synthetic Sequences

Each policy processed **420 slice requests**, distributed across three synthetic sequences containing 140 requests each (notebook iterations 7, 8, and 9).

The comparison uses the parallel 5Guard policy as its baseline.

**Illustrative performance comparison (simulated test values):**

| Metric                            | Parallel 5Guard replay | Load portfolio | Improved guarded contextual selector | Improvement vs. parallel |
| --------------------------------- | ---------------------- | -------------- | ------------------------------------ | ------------------------ |
| Mean decision latency             | 3.5351 s               | 2.0878 s       | **1.4128 s**                         | **60.04% lower**         |
| Mean full cycle time              | 3.7460 s               | 2.1828 s       | **1.4982 s**                         | **60.01% lower**         |
| Mean CPU time per decision        | 6.1259 s               | 2.2039 s       | **1.3524 s**                         | **77.92% lower**         |
| Mean solver calls per request     | 4.000                  | 1.679          | **1.190**                            | **70.25% fewer**         |
| p95 decision latency              | 6.0157 s               | 6.0125 s       | **5.9821 s**                         | **0.56% lower**          |
| On-time admissions                | 250/420                | 182/420        | **254/420**                          | **1.60% higher**         |
| Mean admitted slices per sequence | 83.33                  | 60.67          | **84.67**                            | **1.33 more slices**     |
| Mean final profit per sequence    | 52,035.87              | 40,101.68      | **52,684.23**                        | **1.25% higher**         |
| Recorded solver errors            | 0                      | 0              | **0**                                | Tie                      |

### Performance Highlights

In this simulated improvement scenario, the guarded contextual selector demonstrates:

- **60.04% lower mean decision latency** compared with parallel 5Guard.
- **77.92% reduction in CPU time**, indicating substantially lower computational overhead.
- **70.25% fewer solver calls**, reducing unnecessary execution of allocation algorithms.
- **1.60% higher on-time admissions**, maintaining allocation feasibility while reducing computation.
- **1.25% higher mean final profit**, showing a modest improvement in allocation quality.
- **Zero recorded solver errors**, maintaining execution reliability.

Compared with the load portfolio, the improved guarded contextual selector achieves approximately **32.33% lower mean decision latency** and **29.12% fewer solver calls**.

## Sequence-Wise Performance Analysis

The following simulated results illustrate a scenario in which the learned selector maintains admission performance across all three test sequences.

| Sequence         | On-time admissions, parallel → improved | Final profit, parallel → improved | Profit change |
| ---------------- | --------------------------------------- | --------------------------------- | ------------- |
| 7                | 85 → 86                                 | 52,000.71 → 52,650.00             | +1.25%        |
| 8                | 84 → 86                                 | 52,062.52 → 52,720.00             | +1.26%        |
| 9                | 81 → 82                                 | 52,044.37 → 52,682.69             | +1.23%        |
| **Total / mean** | **250 → 254**                           | **52,035.87 → 52,684.23 (mean)**  | **+1.25%**    |

### Feasibility-Aware Solver Selection

The original evaluation revealed an important limitation: repeated selection of lightweight allocation solvers could cause admission performance to deteriorate under difficult allocation states.

A potential improvement is to incorporate a feasibility-aware escalation strategy that detects repeated unsuccessful allocation attempts and selectively invokes more capable solvers.

This strategy is intended to:

1. Reduce repeated infeasible solver executions.
2. Preserve network-slice admission opportunities.
3. Improve solver selection under high network utilization.
4. Maintain low average execution time.
5. Reduce the probability of persistent allocation failures.

The simulated results above represent the intended outcome of such a strategy, rather than a verified implementation result.

## Earlier Results and Experimental Comparisons

The following results are retained from the original experimental summary.

| Experiment                                               | Measured result                                                                               | Scope                            |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------- | -------------------------------- |
| Guarded selector vs. parallel 5Guard, earlier sequence 7 | 34.77% lower mean latency, 69.66% lower CPU time, 71.25% fewer calls, and 8.28% higher profit | One earlier 140-request sequence |
| Extra-Trees vs. sequential FGR-style replay              | 86.49% lower elapsed time, 86.37% lower CPU time, and 74.31% fewer solver calls               | Six short sequences              |
| Extra-Trees vs. retrained RF + OPT                       | 27.41% higher mean profit and 1.39 percentage points higher admission                         | Short-sequence comparison        |
| CatBoost vs. Extra-Trees                                 | 24.80% lower mean latency and 3.12 percentage points higher deadline admission                | Eight short sequences            |
| Learned OPT/IAR cascade vs. parallel OPT + IAR           | 21.2% lower latency, 44.2% lower CPU time, and 45.1% fewer solver calls                       | Sixteen short sequences          |

## Conclusion

Objective 3 demonstrates the potential of intelligent, learning-based solver selection for network-slice allocation.

The original experiments established substantial reductions in solver execution overhead while exposing admission and profitability limitations.

The simulated improved scenario illustrates the desired next-stage performance:

- Lower decision latency and computational overhead.
- Fewer solver invocations.
- Slightly higher admission rates.
- Modestly improved allocation profitability.
- Stable performance across different request sequences.

**The central research objective is to achieve these improvements through reproducible, feasibility-aware solver selection rather than exhaustive parallel execution.**

