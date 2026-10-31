# Objective 2: Learning-Based Admission Control

Combined Objective 2/3 README: [`OBJECTIVES_2_3.md`](OBJECTIVES_2_3.md)

## Objective

Objective 2 replaces greedy slice admission with a learning-based controller
that considers the long-term effect of each decision on network resources and
profit. For every incoming slice, the controller selects one of three actions:

- `ADMIT`: allocate the request when sufficient capacity is available.
- `REJECT`: decline a request that is unlikely to improve long-term reward.
- `DEFER`: postpone the decision until occupied resources may become available.

## Implementation

SecGuard implements Objective 2 as a Deep Q-Network (DQN) written with NumPy.
The implementation includes:

- experience replay and a periodically synchronized target network;
- epsilon-greedy exploration and Huber-loss training;
- capacity-aware action masking that prevents resource overcommitment;
- a bounded defer action to prevent requests from remaining queued forever;
- model saving and deterministic, seed-controlled experiments; and
- comparisons with greedy and value-density admission policies.

The 14-feature state represents CPU, radio, and bandwidth utilization; active
request count; mean remaining resource lifetime; incoming resource demands;
revenue; duration; isolation level; threat risk; defer count; and remaining
episode horizon. The isolation level always respects the tenant's requested SLA
floor inherited from Objective 1.

## Evaluation setup

- Training episodes: **2,000**
- Held-out evaluation episodes: **50**
- Requests per episode: **24**
- Random seed: **42**
- Held-out seeds: **10042--10091**

Reproduction command:

```powershell
python -m secguard.admission_control --episodes 2000 `
  --evaluation-episodes 50 --requests 24 --seed 42
```

## Results

| Metric | DQN | Greedy | Value density |
|---|---:|---:|---:|
| Mean total reward | **987.47** | 598.71 | 986.75 |
| Mean security-adjusted profit | **1020.62** | 626.46 | 1018.05 |
| Mean admitted requests | 18.92 | 12.92 | **20.26** |
| Mean rejected requests | 5.08 | 11.08 | **3.74** |
| Mean infeasible admissions | **0.00** | **0.00** | **0.00** |

Relative to greedy admission, DQN achieved:

- **64.9% higher mean total reward**;
- **62.9% higher security-adjusted profit**;
- **46.4% more admitted requests**; and
- **54.2% fewer rejected requests**.

In the paired comparison, DQN beat greedy in all 50 held-out episodes. Its mean
paired reward gain was 388.76 with a 95% confidence interval of
[356.64, 420.89].

DQN's mean reward was only 0.07% higher than the value-density heuristic. DQN
won 26 of the 50 paired episodes, and its paired difference had a 95% confidence
interval of [-22.27, 23.73]. Therefore, the experiment establishes a clear
improvement over greedy admission but does **not** establish superiority over
the strong value-density baseline.

## Verification and artifacts

- Complete test suite: **29 tests passed**.
- Implementation: `src/secguard/admission_control.py`
- Tests: `tests/test_admission_control.py`
- Numerical evidence: `artifacts/objective2_admission_control.json`
- Trained model: `artifacts/objective2_dqn.npz`
- Evaluation plot: `artifacts/objective2_admission_control.png`

## Limitations

- The environment is calibrated to the four 5Guard service classes but does not
  run the 5Guard MILP solver for every RL transition.
- The held-out traces are synthetic rather than production-network traces.
- The security penalty is based on an isolation-exposure proxy, not directly
  measured attack propagation.
- Direct MILP replay and external-dataset evaluation are required before making
  publication-level generalization or superiority claims.
