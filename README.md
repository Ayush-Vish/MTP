# SecGuard & 5Guard Reproduction Guide

SecGuard is a research framework extending the **5Guard** base paper (*"5Guard: Isolation-Aware End-to-End Slicing of 5G Networks"*, IEEE TMC 2026) with an ML-derived security risk detector and an SLA-safe dynamic isolation policy.

For the admission-control and intelligent solver-selection extensions, see
[`OBJECTIVES_2_3.md`](OBJECTIVES_2_3.md).

This repository allows you to:
1. **Reproduce the 5Guard Base Paper** across all 7 algorithms (`OPT`, `IAR`, `DTR`, `RNR`, `NIS`, `CIS`, `FGR`) on both Synthetic and Berlin BRAIN topologies with publication-quality SVG plots.
2. **Run the SecGuard Pipeline** (Random Forest packet-level threat detection $\to$ risk aggregation $\to$ SLA-floor isolation adaptation $\to$ surrogate policy learning $\to$ DQN admission control $\to$ statistical validation).

---

## 1. Requirements for Your Strong Machine

* **OS**: Linux (Ubuntu 22.04 / 24.04 or Debian recommended) or Windows 10/11 / macOS.
* **Python**: Python 3.10, 3.11, or 3.12 (`python3 --version`).
* **CPU**: Multi-core processor (8, 16, 32, or 64 cores). Iterations are parallelized across available cores.
* **Memory**: 8 GB RAM or more.
* **Solvers**:
  * **SCIP (Default & Recommended)**: Fully open-source via `pyscipopt`. **No license required, no model-size limit**. It handles large models past 140 time steps without crashing.
  * **Gurobi (Optional)**: Supported if you have a full academic or commercial Gurobi license (`gurobi.lic`).

---

## 2. Environment Setup

### On Linux / macOS (Bash)

```bash
# 1. Navigate to the project directory
cd secguard

# 2. Create and activate a clean virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -e ".[fiveguard]"

# 4. Fetch the upstream 5Guard code and 5G Intrusion dataset
python scripts/fetch_5guard.py
python scripts/fetch_dataset.py
```

### On Windows (PowerShell)

```powershell
# 1. Navigate to the project directory
cd secguard

# 2. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Upgrade pip and install dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e ".[fiveguard]"

# 4. Fetch upstream code and dataset
python scripts/fetch_5guard.py
python scripts/fetch_dataset.py
```

---

## 3. Running the 5Guard Base Paper Reproduction

The reproduction driver ([`scripts/reproduce_5guard.py`](scripts/reproduce_5guard.py)) converts the base paper's simulation notebook into a parallel, command-line benchmark.

### Step 3.1: Quick Smoke Test (5 seconds)
Verify that all 7 algorithms, the SCIP solver, and the plotting pipeline work properly:

```bash
python scripts/reproduce_5guard.py --iters 2 --interval 10 --workers 2
```

### Step 3.2: Full Paper Reproduction (Synthetic Topology)
Runs all 7 algorithms across 10 Monte Carlo iterations and 140 simulation time steps ($9,800$ total optimization steps):

```bash
# Uses 10 parallel workers (one worker per Monte Carlo iteration)
python scripts/reproduce_5guard.py --iters 10 --interval 140 --workers 10
```
> **Performance note:** On a 10+ core machine, parallel execution completes the entire 7-algorithm benchmark in **~8 to 12 minutes** (compared to ~2 hours sequentially).

### Step 3.3: Real-World Berlin BRAIN Topology
To run on the SNDlib Berlin optical core network (`dataset/brain.xml`):

```bash
python scripts/reproduce_5guard.py --brain --iters 10 --interval 140 --workers 10
```

### Step 3.4: Running Specific Algorithms
You can run a subset of algorithms (e.g. only 5Guard and IAR):

```bash
python scripts/reproduce_5guard.py --algs iar fgr --iters 10 --interval 140 --workers 10
```
Available algorithms: `opt`, `iar`, `dtr`, `rnr`, `nis`, `cis`, `fgr`.

### Step 3.5: Solver Selection
* `--solver scip` (Default): Uses the open-source SCIP solver via `gurobipy_scip.py`. Unrestricted model sizes.
* `--solver gurobi`: Uses Gurobi if an academic/commercial license is configured.

---

## 4. Generated Plots and Metrics

Outputs are automatically saved to `artifacts/5guard_reproduction/`:

### Numerical Results
* `5guard_results_synthetic.json` (or `5guard_results_brain.json`): Contains final profit, QoS violation cost, cumulative migration count, isolation overhead, deployment cost, resource efficiency, rejections by level ($L0, L1, L2$), and solver latency.

### Publication SVG Plots (`artifacts/5guard_reproduction/plots/`)
Matches the figures from the IEEE TMC paper:
| Plot File | Metric | Description |
|---|---|---|
| `profit_0.svg` | **Profit over time** | Cumulative profit comparison across OPT, IAR, DTR, RNR, and 5Guard |
| `admission_0.svg` | **Slice Admission (%)** | Grouped bar chart comparing admission rates across Isolation Levels 0, 1, and 2 |
| `migration_0.svg` | **Cumulative Migration** | Frequency of VNF relocations over time |
| `alloc_time_0.svg` | **Allocation Time (sec)** | Solver latency per step plotted against slice timeout deadlines |
| `overhead_0.svg` | **Total Overhead Cost** | Virtualization (Host OS, K8s, Guest OS) and guardband costs across all 7 algorithms |
| `resource_eff_0.svg` | **Resource Efficiency (%)** | Effective resource utilization across radio, optical, and computing domains |
| `violation_0.svg` | **Violation Cost** | SLA delay and bandwidth penalty costs |
| `deployment_0.svg` | **Deployment Cost** | Direct physical resource allocation cost |

---

## 5. Running the SecGuard Pipeline

To evaluate SecGuard's ML threat detection, dynamic isolation adaptation, and surrogate policy learning:

```bash
# 1. Train the Random Forest intrusion detector on 5G packet telemetry
python -m secguard.train

# 2. Run trace-driven 4-slice risk aggregation demo
python -m secguard.demo

# 3. Test the SLA-preserving 5Guard adapter interface
python -m secguard.fiveguard_demo

# 4. Run the security-vs-profit allocation experiment (static vs dynamic)
python -m secguard.security_experiment

# 5. Execute surrogate-assisted policy learning across 165 threshold triplets
python -m secguard.policy_learning

# 6. Run full research validation (oracle, random baseline, Wilcoxon tests, Pareto frontier)
python -m secguard.research_validation

# 7. Verify claims ledger against paper LaTeX draft
python scripts/check_paper.py

# 8. Train and evaluate Objective 2 DQN admission control
python -m secguard.admission_control

# 9. Train and evaluate Objective 3 intelligent algorithm selection
python -m secguard.algorithm_selector
```

Generated SecGuard artifacts will appear in `artifacts/`:
* `metrics.json` & `confusion_matrix.png`: Classifier test accuracy and confusion matrix.
* `security_experiment.json` & `security_tradeoff.png`: Allocation outcomes under static vs. dynamic isolation.
* `learned_policy.json` & `learned_policy_comparison.png`: Optimal threshold policy $(0.30, 0.35, 0.90)$ and confidence intervals.
* `research_validation.json` & `pareto_frontier.png`: Complete statistical validation and Pareto trade-off curve.
* `objective2_admission_control.json` & `objective2_admission_control.png`: Held-out DQN admission-control comparison against greedy and value-density baselines.
* `objective3_algorithm_selector.json`, `objective3_algorithm_selector.png`, and `objective3_architecture.png`: Held-out learned solver-selection results and system diagram.

---

## 6. Project Structure

```text
secguard/
├── src/secguard/                     # SecGuard ML and policy package
│   ├── train.py                      # Random Forest classifier training
│   ├── policy.py                     # Dynamic isolation policy with SLA floor
│   ├── fiveguard_adapter.py          # Adapter mapping SecGuard decisions to 5Guard sr
│   ├── policy_learning.py            # Surrogate RF model for threshold optimization
│   └── research_validation.py        # Oracle, random search control, Wilcoxon tests
├── external/5guard/                  # Pinned 5Guard upstream implementation
│   ├── algorithms/                   # OPT, IAR, DTR, RNR, NIS, CIS, FGR
│   ├── dataset/                      # brain.xml (Berlin SNDlib topology)
│   ├── gurobipy_scip.py              # SCIP solver compatibility layer
│   ├── libraries.py                  # Auto-detecting solver import hub
│   └── setup.py                      # Network topology and resource calibration
├── scripts/
│   ├── reproduce_5guard.py           # Parallel multi-core 5Guard reproduction driver
│   ├── fetch_5guard.py               # Fetches pinned 5Guard repository
│   ├── fetch_dataset.py              # Downloads 5G intrusion detection traces
│   └── check_paper.py                # Asserts paper claims match experiment artifacts
├── artifacts/                        # Output figures, JSON metrics, and learned models
│   └── 5guard_reproduction/          # 5Guard base paper plots and benchmark results
│       └── plots/                    # SVG publication plots
├── paper/                            # LaTeX manuscript and ARS claims ledger
└── tests/                            # Pytest validation test suite
```

---

## 7. License and Attribution

* **5Guard Base Paper**: Bolourian et al., *"5Guard: Isolation-Aware End-to-End Slicing of 5G Networks"*, IEEE Transactions on Mobile Computing, 2026. Code under `external/5guard/`.
* **5G Intrusion Dataset**: Saeid Sheikhi, [5G Intrusion Detection Dataset](https://github.com/saeidsheikhi/5G-Intrusion-Detection-Dataset) (MIT License).
