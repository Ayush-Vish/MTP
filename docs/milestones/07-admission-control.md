# M5: Objective 2 learning-based admission control

Status: **Complete as a synthetic research prototype** on 2026-10-31.

## Objective

Replace greedy admission with a controller that considers the long-term cost of
occupying radio, transport, and compute resources. The action space is `ADMIT`,
`REJECT`, and bounded `DEFER`.

## Implementation

- Added a 14-feature Markov state containing current utilization, active-request
  count, remaining resource lifetime, incoming demand, revenue, duration,
  isolation level, threat risk, defer count, and remaining horizon.
- Added a NumPy DQN with a 64-unit hidden layer, replay memory, epsilon-greedy
  exploration, Huber loss, and a periodically synchronized target network.
- Added capacity-aware action masking, so the learned policy cannot overcommit
  resources and cannot defer beyond the configured limit.
- Preserved Objective 1's SLA isolation floor in generated traces and included
  the threat score and isolation exposure in the reward.
- Added greedy and value-density baselines, paired held-out evaluation, model
  persistence, a JSON evidence artifact, and a comparison plot.

## Reproducible evaluation

Command:

```text
python -m secguard.admission_control --episodes 2000 \
  --evaluation-episodes 50 --requests 24 --seed 42
```

Fifty held-out traces use seeds 10042--10091 and 24 arrivals per episode.
The generated source of truth is `artifacts/objective2_admission_control.json`.

| Policy | Mean total reward | Mean adjusted profit | Mean admitted | Infeasible |
|---|---:|---:|---:|---:|
| DQN | 987.47 | 1020.62 | 18.92 | 0.00 |
| Greedy feasible-first | 598.71 | 626.46 | 12.92 | 0.00 |
| Value-density heuristic | 986.75 | 1018.05 | 20.26 | 0.00 |

The DQN improves mean total reward by 64.9% over greedy and wins all 50 paired
episodes; the mean paired gain is 388.76 (95% CI [356.64, 420.89]). Its 0.07%
mean edge over the tuned value-density heuristic is negligible: it wins 26 of
50 pairs and the mean paired delta is 0.73 (95% CI [-22.27, 23.73]). It is not
treated as an established superiority claim.

## Verification

- Eight admission-control unit tests cover normalized state, rewards, capacity
  safety and action masking, defer limits, DQN updates, deterministic generation,
  and invalid input.
- The complete project suite passes: 29 tests.

## Limitations

- The environment is calibrated to the four 5Guard service classes but does not
  invoke the MILP solver on every RL transition.
- Results use generated held-out traces, not live or production traffic.
- The security term is an isolation-exposure proxy, not measured propagation.
- External datasets and direct MILP replay remain necessary for a publication-
  level claim about generalization or superiority.
