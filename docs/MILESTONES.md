# SecGuard milestone tracker

This file is the project-level source of truth. Each milestone records what was
built, what changed relative to its baseline, the evidence supporting the
result, known limitations, blockers, and the exact next step.

## Status summary

| Milestone | Status | Main outcome | Git commit |
|---|---|---|---|
| M0: Scope selection | Complete | Selected anomaly detection plus dynamic isolation | N/A |
| M1: Risk model and policy | Complete | Traffic-to-risk-to-isolation pipeline works | `65699ff` |
| M2: 5Guard input integration | Complete | Decisions become valid 5Guard requests | `fa3b25b` |
| M3A: Allocation pilot | Complete | 86.36% lower exposure for 6.01% lower profit | `11241c9` |
| M3B: Learned profit-aware policy | Complete | +164.92% profit over fixed SecGuard | `dee754d` |
| M4: Generalization and ablation | In progress | Validate on unseen scenarios and remove components | Pending |
| P1: Paper draft | Complete | IEEE-style preliminary paper and claim ledger | Pending |
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

Status: **Complete** on 2026-08-14.

Detailed report: [`milestones/02-fiveguard-adapter.md`](milestones/02-fiveguard-adapter.md)

### Baseline

SecGuard emits JSON decisions, while 5Guard expects Python slice-request objects
with a numeric `gamma` isolation field. There is currently no tested connection.

### Completion criteria

- Convert `KEEP` and upgrade actions into valid `gamma` values 0, 1, or 2.
- Preserve the original slice request and all non-security parameters.
- Represent quarantine without sending an invalid request to the optimizer.
- Prove through tests that SLA isolation can never be downgraded.
- Run an adapter demonstration with all four policy actions.

All completion criteria passed.

### Work completed

- Added a non-mutating adapter for the original 5Guard `sr` class.
- Updated only the optimizer copy's numeric `gamma` isolation value.
- Withheld quarantine decisions instead of creating an invalid `gamma`.
- Pinned upstream 5Guard revision `adadaccf` for repeatability.
- Added six adapter tests and a real-class compatibility demonstration.

### Measured improvement

- Before: 0/4 SecGuard actions could be submitted safely to 5Guard.
- After: 4/4 actions are handled; three yield valid `sr` inputs and quarantine
  is intercepted before optimization.
- Original input mutation: zero across all four demonstration requests.
- Non-security field preservation: 4/4 demonstration requests.
- Total test suite increased from 5 to 11 passing tests.

### Blocker recorded at completion

`gurobipy` and `gurobi_cl` are not installed in the current environment. Adapter
development and unit testing can proceed, but real 5Guard optimization and its
profit/resource metrics require Gurobi plus a valid licence.

This blocker was resolved in M3A by installing Gurobi 13.0.2. A restricted
non-production licence is available through 2027-11-29 and ran the small IAR
experiment successfully. Its model-size limit may still block the full BRAIN
topology.

## M3A: Security-aware allocation pilot

Status: **Complete** on 2026-08-14.

Detailed report: [`milestones/03-allocation-pilot.md`](milestones/03-allocation-pilot.md)

### Baseline

Original 5Guard uses the SLA-provided static isolation levels and has no attack
risk input. Before M3A, SecGuard's adapter had not been evaluated by an actual
5Guard optimization algorithm.

### Work completed

- Installed Gurobi 13.0.2 and verified the available restricted licence.
- Ran static 5Guard and SecGuard through IAR on the synthetic topology.
- Used the same four slice requests and risk scores for both policies.
- Defined a transparent isolation-exposure proxy.
- Recorded profit, admission, quarantine, migrations, costs, and efficiency.
- Added three metric tests and a presentation-ready trade-off plot.

### Measured improvement and cost

- Exposure proxy: 0.6875 to 0.0938, an **86.36% reduction**.
- Raw 5Guard profit: 2915.9950 to 2740.6860, a **6.01% reduction**.
- Admitted requests: 3 to 2; SecGuard additionally quarantined one request.
- Total project tests: 11 to 14 passing.

This establishes a security/profit trade-off; it does not establish statistical
superiority.

## M3B: Scaled security-aware allocation experiment

Status: **Complete** on 2026-08-14.

Detailed report: [`milestones/04-learned-policy.md`](milestones/04-learned-policy.md)

### Completion criteria

- Use repeated arrival sequences rather than one four-request sequence.
- Sweep isolation/quarantine thresholds and produce a Pareto frontier.
- Report mean and 95% confidence intervals over multiple seeds.
- Compare static 5Guard, complete isolation, rule-based isolation, and SecGuard.
- Determine whether the restricted licence supports the desired topology size.

The repeated-sequence, threshold-learning, confidence-interval, and
static/fixed/learned comparisons are complete. Complete-isolation and full BRAIN
experiments remain for M4 because the current restricted licence may impose a
model-size limit.

### Learned policy

A Random-Forest regression surrogate learned profit and exposure surfaces from
81 sampled threshold policies evaluated by Gurobi-backed 5Guard. Subject to at
least 60% predicted exposure reduction, it selected L1=0.30, L2=0.35, and
quarantine=0.90.

### Held-out improvements over fixed SecGuard

- Mean profit: 2776.79 to 7356.28, an **increase of 164.92%**.
- Mean admission: 2.27 to 2.90, an **increase of 27.94%**.
- Mean quarantines: 1.00 to 0.30, a **reduction of 70.00%**.
- Mean exposure: 0.2438 to 0.2542, a **4.27% increase** (security cost).
- Paired absolute profit gain: 4579.49, 95% CI [2206.50, 6952.49].

### Comparison with static 5Guard

- Learned SecGuard retained **90.44%** of static profit.
- It reduced the exposure proxy by **67.12%** versus static 5Guard.
- Exposure improved in 29 of 30 paired held-out scenarios, with one tie.

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

Status: **In progress**.

- Evaluate an unseen attack scenario or a second 5G dataset.
- Compare Random Forest with a simple logistic baseline.
- Remove SLA flooring, risk aggregation, and quarantine one at a time.
- Report confidence intervals over repeated slice-arrival simulations.

## P1: Paper draft

Status: **Complete** on 2026-08-14.

- Added `paper/main.tex` with abstract, related work, equations, design,
  evaluation, results, threats to validity, reproducibility, and conclusion.
- Added `paper/references.bib` with 13 standards, primary papers, software, and
  dataset references.
- Added `paper/CLAIMS.md` to prevent overstatement in the paper or presentation.
- Labeled the current evaluation as preliminary and enumerated the exact work
  needed before submission.
- TeX source has balanced braces, but a PDF was not built because no TeX
  distribution is installed in the current environment.
