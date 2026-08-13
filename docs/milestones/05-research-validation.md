# Milestone M4A: Reviewer-oriented research validation

Status: **Complete** on 2026-08-14  
Implementation commit: `4b2d75d`

## Goal

Strengthen the learned-policy experiment with controls and metrics that can
survive a professor or reviewer asking whether the gain is statistically
reliable, close to an oracle, better than a simple search, dependent on
quarantine, or too expensive to run.

## What was added

- Exhaustive evaluation of all 165 ordered threshold tuples on five training
  scenarios.
- An exhaustive training oracle and an exactly equal-budget 81-policy random
  search control.
- Thirty paired held-out trace-derived scenarios for six policies: Static,
  Fixed, Learned, Oracle, Random-81, and No-quarantine.
- Two-sided paired Wilcoxon tests, paired Cohen's dz effects, signs, and ties.
- A no-quarantine component ablation.
- Migration, QoS-violation, deployment, overhead, resource-efficiency, and
  allocation-time measurements.
- Local warm-batch detector and threshold-policy latency benchmarks.
- A complete JSON evidence package with all candidate and per-scenario results.

## Main measured outcomes

| Comparison | Outcome |
|---|---:|
| Learned vs. Fixed mean profit | +164.92% (+4,579.49 units) |
| Learned vs. Fixed paired test | p=0.0028, dz=0.69; 22+/4-/4 ties |
| Learned vs. Static modeled exposure | -67.12% |
| Learned vs. Static paired test | p=2.56e-6, dz=-3.43; 29-/0+/1 tie |
| Learned retention of Static profit | 90.44% |
| Learned regret vs. training oracle | 2.41%, p=0.2843 |
| Exact allocator work avoided by learner | 84 policies / 420 scenario allocations |
| Warm detector benchmark | 47.66 microseconds/packet; 20,981 packets/s |
| Threshold-policy benchmark | 1.21 microseconds/decision |

## Adverse and null controls

- Random-81 found the exact exhaustive training oracle. The current plateaued
  165-policy space therefore does **not** support a claim that the surrogate is
  more sample-efficient than random search.
- Replacing quarantine with L2 raised mean raw profit by 19.25%. Only three
  scenarios changed and the paired result was not significant (p=0.1088).
- Modeled exposure was unchanged in that ablation because the proxy gives both
  L2 and quarantine zero sharing. Quarantine's security benefit is unvalidated.

## Evidence and reproduction

- Evidence: `artifacts/research_validation.json`
- Main figure: `artifacts/pareto_frontier.png`
- Extended metrics: `artifacts/extended_metrics.png`
- Implementation: `src/secguard/research_validation.py`
- Tests: `tests/test_research_validation.py`

```powershell
.\.venv\Scripts\python.exe -m secguard.research_validation
.\.venv\Scripts\python.exe -m pytest -q
```

At completion, all 21 tests passed. The full validation run completed locally
without a technical blocker using the available restricted Gurobi licence.

## Limitations and next evidence

The test records come from the same public data source as training, scenarios
are simulated, and modeled exposure is not attack containment. M4B must add a
second dataset or unseen attack family, a simple classifier baseline, a larger
policy/topology study, and a propagation outcome that distinguishes L2 from
quarantine.
