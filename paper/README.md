# SecGuard paper draft

Working title: **SecGuard: ML-Driven Risk-Adaptive Isolation for Profit-Aware
End-to-End 5G Network Slicing**.

The paper is intentionally labeled a preliminary evaluation. Current evidence is
appropriate for an MTP review or professor presentation, but the experiments in
Section VII of `main.tex` should be completed before journal submission.

## Build

The source uses the IEEE conference template:

```powershell
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

A TeX distribution is not installed in the current environment, so the PDF has
not been compiled locally. Figures are loaded directly from `../artifacts/`.

## Reproduce paper results

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\fetch_dataset.py
.\.venv\Scripts\python.exe scripts\fetch_5guard.py
.\.venv\Scripts\python.exe -m secguard.train
.\.venv\Scripts\python.exe -m secguard.policy_learning
.\.venv\Scripts\python.exe -m pytest -q
```

The source of every numerical claim is `../artifacts/learned_policy.json` or
`../artifacts/metrics.json`.

