# SecGuard milestone tracker

This file is the project-level source of truth. Each milestone records what was
built, what changed relative to its baseline, the evidence supporting the
result, known limitations, blockers, and the exact next step.

## Status summary

| Milestone | Status | Main outcome | Git commit |
|---|---|---|---|
| M0: Scope selection | Complete | Selected anomaly detection plus dynamic isolation | N/A |
| M1: Risk model and policy | Complete | Traffic-to-risk-to-isolation pipeline works | `65699ff` |
| M2: 5Guard input integration | In progress | Convert decisions into 5Guard slice updates | Pending |
| M3: Security-aware allocation experiment | Planned | Measure security/resource/profit trade-offs | Pending |
| M4: Generalization and ablation | Planned | Validate on unseen scenarios and remove components | Pending |

## M0: Scope selection

### Decision

The project selected **ML anomaly detection plus dynamic isolation plus
security-aware 5Guard allocation**. Full deep-RL allocation was deferred because
it adds substantial training risk before a trustworthy security baseline exists.

### Expected novelty

5Guard receives an isolation level as input. SecGuard derives a risk signal from
5G telemetry, selects a safe isolation response, and will feed that response into
5Guard while accounting for security exposure and allocation cost.

## M1: ML risk model and SLA-safe isolation policy

Status: **Complete** on 2026-08-14.

Detailed report: [`milestones/01-risk-model.md`](milestones/01-risk-model.md)

### Baseline

- No traffic-based security signal existed in the local project.
- Isolation levels could not change in response to observed attacks.
- No reproducible ML evaluation or security-action demonstration existed.

### Work completed

- Trained a 300-tree Random Forest using 44 packet/GTP features.
- Preserved the dataset-provided train/test split.
- Converted packet attack probabilities into a mean per-slice risk score.
- Added `KEEP`, `UPGRADE_L1`, `UPGRADE_L2`, and `QUARANTINE` actions.
- Guaranteed that the policy never weakens the SLA-requested isolation level.
- Added reproducible dataset download, training, artifacts, and policy tests.

### Measured improvement

- Added a previously absent anomaly-detection capability.
- Held-out test result: F1=1.0000, PR-AUC=1.0000, FPR=0.0000 on 3,787 rows.
- Trace-driven demo: all three constructed risky slices were escalated; the
  benign slice was not escalated.
- Test suite: 5/5 policy tests passed.

These are dataset-specific baseline results, not a generalization claim.

### Limitations

- The held-out samples come from the same curated data source as training.
- Demo slices are constructed by mixing held-out records; the dataset does not
  provide native 5Guard slice identifiers.
- No 5Guard resource mapping is changed yet.
- No containment, profit, migration, or resource-efficiency improvement has yet
  been measured.

## M2: SecGuard-to-5Guard input integration

Status: **In progress**.

### Baseline

SecGuard emits JSON decisions, while 5Guard expects Python slice-request objects
with a numeric `gamma` isolation field. There is currently no tested connection.

### Completion criteria

- Convert `KEEP` and upgrade actions into valid `gamma` values 0, 1, or 2.
- Preserve the original slice request and all non-security parameters.
- Represent quarantine without sending an invalid request to the optimizer.
- Prove through tests that SLA isolation can never be downgraded.
- Run an adapter demonstration with all four policy actions.

### Current blocker

`gurobipy` and `gurobi_cl` are not installed in the current environment. Adapter
development and unit testing can proceed, but real 5Guard optimization and its
profit/resource metrics require Gurobi plus a valid licence.

## M3: Security-aware allocation experiment

Status: **Planned**.

### Metrics

- Cross-slice exposure score and exposure reduction.
- Attack containment rate and containment latency.
- False isolation-escalation rate.
- 5Guard net profit and security-adjusted profit.
- Admission rate by service and isolation level.
- Migration cost, QoS violation cost, and resource efficiency.
- Allocation deadline satisfaction and p95 decision time.

### Required comparisons

- Original static-isolation 5Guard.
- Complete isolation for all slices.
- Rule-based dynamic isolation.
- ML-risk-driven dynamic isolation (SecGuard).

## M4: Generalization and ablation

Status: **Planned**.

- Evaluate an unseen attack scenario or a second 5G dataset.
- Compare Random Forest with a simple logistic baseline.
- Remove SLA flooring, risk aggregation, and quarantine one at a time.
- Report confidence intervals over repeated slice-arrival simulations.

