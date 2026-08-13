# SecGuard paper package

Title: **SecGuard: Risk-Adaptive Isolation for Profit-Aware
End-to-End 5G Network Slicing**.

The package is an IEEE-style proof-of-concept manuscript suitable for an MTP
review and professor presentation. It reports favorable, null, and adverse
controls explicitly. Cross-dataset validation and a measured attack-propagation
outcome remain necessary before making broader deployment claims.

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
.\.venv\Scripts\python.exe -m secguard.research_validation
.\.venv\Scripts\python.exe scripts/check_paper.py
.\.venv\Scripts\python.exe -m pytest -q
```

The source of the manuscript's primary numerical claims is
`../artifacts/research_validation.json`. The ARS-Codex research, writing,
review, citation, visualization, and formatting record is in `ARS_WORKFLOW.md`;
the English and Traditional Chinese abstracts are in `abstracts.md`.
