# Objective 1: Intelligent Security-to-Isolation Mapping

## Objective

Objective 1 maps packet-level threat evidence to slice-level risk and selects
the minimum safe isolation action without lowering the tenant's requested SLA.
The pipeline combines a Random-Forest detector, risk aggregation, dynamic
L0/L1/L2/quarantine decisions, and a non-mutating adapter for 5Guard.

## Prototype acceptance evidence

The learned threshold policy was evaluated on 30 held-out, trace-derived
scenarios. Relative to static 5Guard, it retained **90.44%** of mean profit and
reduced the modeled isolation-exposure proxy by **67.12%**. Relative to fixed
SecGuard, mean profit increased from 2776.79 to 7356.28 (**164.92%**) and the
paired Wilcoxon test reported p=0.0028.

The adapter validation confirms that no request is mutated and no selected
isolation level is lower than the original SLA floor.

## Reproduction

```powershell
python -m secguard.train
python -m secguard.security_experiment
python -m secguard.policy_learning
python -m secguard.research_validation
```

## Evidence

- Detector metrics: `artifacts/metrics.json`
- Adapter decisions: `artifacts/fiveguard_adapter.json`
- Statistical validation: `artifacts/research_validation.json`
- Pareto figure: `artifacts/pareto_frontier.png`
- Implementation: `src/secguard/policy.py`,
  `src/secguard/fiveguard_adapter.py`, and
  `src/secguard/research_validation.py`

## Claim boundary

Objective 1 is complete as a research prototype. The current security endpoint
is a modeled isolation-exposure proxy, not measured attack propagation, and the
detector result is within-source rather than cross-dataset generalization.
