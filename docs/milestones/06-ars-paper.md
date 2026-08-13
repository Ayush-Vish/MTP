# Milestone P2: ARS-reviewed SecGuard manuscript

Status: **Complete** on 2026-08-14  
Paper commit: `2e12dbc`

## Goal

Turn the preliminary SecGuard draft into an evidence-synchronized IEEE paper
that is honest enough for a research review and clear enough for an MTP
presentation.

## What changed

- Reframed the study around three research questions covering economic/security
  performance, oracle/search efficiency, and component/operational limits.
- Defined four scoped contributions without claiming a universally first method.
- Added exact risk, SLA-floor, exposure, and constrained-selection equations.
- Documented the 165-policy grid, 81-policy learner budget, seeds, attack ranges,
  baselines, ablation, statistical tests, and reproducibility commands.
- Integrated favorable, null, and adverse results rather than selecting only
  improved metrics.
- Added related work with 13 verified standards, primary papers, datasets, and
  software references.
- Added English and Traditional Chinese abstracts and five research-integrity
  declarations.
- Added a deterministic checker for LaTeX balance, citation completeness,
  figures, result drift, and declarations.
- Upgraded the Pareto figure to a colorblind-safe 6.9-by-4.1-inch, 300-DPI
  double-column artifact and recorded its data-to-claim trace.

## ARS-Codex gates

| Gate | Result |
|---|---|
| Intake and configuration | Empirical IEEE conference proof-of-concept |
| Literature set | 13 cited entries; 13/13 keys matched |
| Argument integrity | Counter-arguments retained in manuscript |
| Writer check | Accept; approximately 3,000 words |
| Citation check | 0 missing and 0 uncited entries |
| Bilingual abstract | 190 English words; 414 Chinese non-space characters |
| Reviewer simulation | 8.25/10; accept with originality dissent note |
| Figure verification | Pass at original resolution |
| Deterministic paper check | Pass |

The originality warning is intentional: equal-budget random search found the
same oracle, so the present work demonstrates a useful integration and measured
trade-off, not superiority of surrogate threshold search.

## Deliverables

- Manuscript: `paper/main.tex`
- Bibliography: `paper/references.bib`
- Abstracts: `paper/abstracts.md`
- ARS workflow and audit trail: `paper/ARS_WORKFLOW.md`
- Claim ledger: `paper/CLAIMS.md`
- Paper checker: `scripts/check_paper.py`

## Verification

```powershell
.\.venv\Scripts\python.exe scripts/check_paper.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

Results: paper check passed with 13 citations and four synchronized headline
claims; all 21 tests passed; Python compilation passed.

## Remaining submission work

There is no blocker to showing the source and evidence to the professor. A TeX
distribution is not installed in this environment, so PDF compilation and
pagination remain unverified. The author/institution, funding, and conflict
fields also require the researcher's input. Cross-dataset and propagation
experiments are research limitations, not blockers to the current MTP
proof-of-concept presentation.
