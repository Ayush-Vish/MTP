# SecGuard

SecGuard is an MTP research prototype that extends 5Guard with an ML-derived
attack-risk score and an SLA-safe dynamic isolation policy.

This first milestone answers one focused question:

> Can real 5G packet/GTP telemetry be converted into a per-slice security risk
> and an actionable L0/L1/L2/quarantine decision?

## Pipeline

```text
5G traffic -> Random Forest risk model -> per-slice risk aggregation
           -> KEEP / UPGRADE_L1 / UPGRADE_L2 / QUARANTINE
```

The policy never lowers the isolation level requested in the slice SLA.

## Reproduce

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\fetch_dataset.py
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m secguard.train
.\.venv\Scripts\python.exe -m secguard.demo
.\.venv\Scripts\python.exe scripts\fetch_5guard.py
.\.venv\Scripts\python.exe -m secguard.fiveguard_demo
.\.venv\Scripts\python.exe -m pip install -e ".[fiveguard]"
.\.venv\Scripts\python.exe -m secguard.security_experiment
.\.venv\Scripts\python.exe -m secguard.policy_learning
.\.venv\Scripts\python.exe -m secguard.research_validation
```

Generated outputs are written to `artifacts/`:

- `metrics.json`: held-out test metrics.
- `confusion_matrix.png`: normal/attack confusion matrix.
- `feature_importance.csv`: interpretable feature ranking.
- `slice_decisions.json`: sample dynamic isolation decisions.
- `risk_model.joblib`: trained model (ignored by Git).
- `fiveguard_adapter.json`: SecGuard decisions applied to 5Guard requests.
- `security_experiment.json`: static versus adaptive isolation experiment.
- `security_tradeoff.png`: presentation-ready pilot trade-off plot.
- `learned_policy.json`: learned thresholds and held-out policy metrics.
- `learned_policy_comparison.png`: learned-versus-fixed policy comparison.
- `research_validation.json`: oracle, statistics, ablations, and extended metrics.
- `pareto_frontier.png`: training security--profit frontier.
- `extended_metrics.png`: six-metric reviewer-oriented comparison.

## Milestone documentation

Progress, measurements, blockers, and next steps are maintained in
[`docs/MILESTONES.md`](docs/MILESTONES.md). Detailed evidence for each completed
milestone is stored under [`docs/milestones/`](docs/milestones/). A milestone is
only marked complete after its tests and reproducibility commands pass.

## Research scope

This milestone detects anomalous traffic and produces decisions, but it does not
yet modify 5Guard resource mappings. The next milestone will feed the target
isolation level to 5Guard and measure security exposure, profit, migration cost,
and resource efficiency.

## Dataset and attribution

The project uses the MIT-licensed
[5G Intrusion Detection Dataset](https://github.com/saeidsheikhi/5G-Intrusion-Detection-Dataset),
generated with Open5GS and UERANSIM. It contains normal traffic and simulated
DDoS, PFCP, and IP-spoofing anomalies. Raw CSV files are downloaded locally and
excluded from this repository.

Please cite the dataset authors' related publications listed in their repository.
