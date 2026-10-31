# Changelog

All notable research-prototype changes are recorded here. Experimental results
and limitations are documented separately in `docs/MILESTONES.md`.

## Unreleased

- Add cross-dataset and full-ensemble validation before paper submission.
- Compile and proofread the paper with the final author metadata.
- Implement Objective 2 as a reproducible DQN admission controller with replay
  memory, a target network, admit/reject/defer actions, held-out baselines, and
  security-aware resource state.

## 0.7.0 - 2026-08-14

- Rewrite the SecGuard manuscript through the ARS-Codex academic-paper workflow.
- Add paired statistics, oracle/random controls, quarantine ablation, operational
  metrics, and adverse findings to the IEEE draft.
- Add verified bibliography metadata, bilingual abstracts, a claim ledger, and
  a deterministic evidence-drift checker.
- Upgrade the Pareto plot to a traced, accessible 300-DPI IEEE figure.

## 0.6.0 - 2026-08-14

- Exhaustively evaluate all 165 valid policy thresholds and record the oracle.
- Compare against an equal-budget random search on 30 paired test scenarios.
- Add Wilcoxon tests, paired effect sizes, no-quarantine ablation, latency, and
  extended allocation metrics.
- Persist all candidate and per-scenario results for independent checking.

## 0.5.0 - 2026-08-14

- Add an IEEE-style SecGuard paper draft based on the 5Guard extension.
- Add a 13-entry bibliography and a reproducibility guide.
- Add a claim ledger separating supported, qualified, and unsupported claims.
- Document the experiments required for publication-level evidence.

## 0.4.0 - 2026-08-14

- Add Random-Forest surrogate learning for profit-aware isolation thresholds.
- Separate detector-training probability pools from held-out test pools.
- Evaluate learned, fixed, and static policies over 30 held-out scenarios.
- Add paired confidence intervals and a three-metric comparison plot.

## 0.3.0 - 2026-08-14

- Add a static-versus-adaptive allocation experiment using 5Guard IAR.
- Add an explicit isolation-exposure proxy and unit tests.
- Add Gurobi, NetworkX, and Tabulate as optional 5Guard dependencies.
- Add a presentation-ready security/profit trade-off plot.

## 0.2.0 - 2026-08-14

- Add an SLA-safe adapter for the original 5Guard `sr.gamma` input.
- Withhold quarantined slices before they enter the optimizer.
- Pin and fetch the upstream 5Guard revision used for compatibility tests.
- Add a four-action adapter demonstration and six adapter tests.

## 0.1.0 - 2026-08-14

- Add a Random Forest attack-risk model for 5G packet and GTP telemetry.
- Add an SLA-safe L0/L1/L2/quarantine policy.
- Add a trace-driven four-slice demonstration.
- Add held-out metrics, feature importance, and confusion-matrix artifacts.
- Add five unit tests for isolation-policy behavior.
