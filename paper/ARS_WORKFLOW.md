# ARS-Codex paper workflow record

This record documents how `ars-codex:academic-research-suite` was applied to
the SecGuard manuscript on 2026-08-14. It is an audit trail, not a certificate
of publication readiness.

## Phase 0: Paper configuration record

| Parameter | Value |
|---|---|
| Topic | Risk-adaptive isolation for profit-aware 5G network slicing |
| Research question | Can telemetry-derived risk safely control 5Guard isolation while recovering profit lost by conservative fixed thresholds? |
| Paper type | Empirical conference paper |
| Discipline | Computer networking, network security, and machine learning |
| Target venue | General IEEE-style conference; no venue-specific limits declared |
| Citation format | IEEE |
| Output format | LaTeX, with bilingual abstracts as a Markdown supplement |
| Body language | English |
| Word-count target | Approximately 3,000 words excluding references |
| Existing materials | Source code, held-out results, figures, bibliography, and preliminary draft |
| Authors | Anonymous placeholders; named CRediT assignments pending |
| Funding and conflicts | Not supplied; explicitly marked pending rather than inferred |
| Style profile | None supplied |
| Domain evidence profile | `cs_ml` |
| Citation verification | Advisory for standards/software; DOI verification where available |
| Operational mode | Full paper writing, balanced spectrum |

The user's repeated instructions to write the paper and resume the existing
project were treated as confirmation of this already-established configuration.

## Phase 1: Literature search report

### Search strategy

- Last searched: 2026-08-14.
- Source families: IEEE/publisher records, author repositories, ITU-T, 3GPP,
  arXiv, and official GitHub repositories.
- Core queries: `5Guard isolation-aware end-to-end slicing`, `5G slice
  isolation DDoS reinforcement learning`, `network slice admission deep
  reinforcement learning`, and the exact titles/DOIs of bibliography entries.
- Include: sources directly supporting isolation-aware placement, adaptive
  security, learned admission, the detector dataset, the algorithm, or the
  implementation.
- Exclude: secondary summaries when a primary paper, standard, or official
  repository was available; off-topic 5G security work; unverifiable entries.
- Date range: 2022–2026 plus Breiman (2001) as the foundational Random Forest
  source.

This was a focused source-verification pass, not a systematic review. Search
engine hit counts were not retained, so no systematic-review completeness claim
is made.

### Screening result and annotations

All 13 final bibliography entries are cited in the manuscript.

| Source | Evidence and use | Quality / qualification |
|---|---|---|
| Bolourian et al. (2026) | 5Guard model, levels, objectives, and baseline boundary | Peer-reviewed primary paper; core |
| 5Guard repository (2025) | Executable upstream implementation and `gamma` interface | Official code; pinned revision |
| ITU-T X.1816 (2023) | Differentiated slice-security capabilities | In-force primary standard |
| ITU-T X.1814 (2022) | IMT-2020 threats and security capabilities | In-force primary standard |
| 3GPP TS 33.501 (2026) | 5G security architecture | Primary technical specification |
| Javadpour et al. (2023) | RL-based DDoS slice isolation | Peer-reviewed adjacent work |
| Troia et al. (2022) | Learned admission plus embedding | Peer-reviewed adjacent work |
| Asdikian et al. (2025) | Explanation and conservative-rejection risk | Peer-reviewed adjacent work |
| Jacoby et al. (2026) | Predictive admission under uncertainty | Archival preprint; labeled as such |
| Sheikhi and Kostakos (2023) | Dataset lineage and 5G DDoS detection | Peer-reviewed conference paper |
| 5G IDS repository (2025) | Feature schema and public files | Official dataset repository |
| Breiman (2001) | Random Forest method | Seminal peer-reviewed source |
| Gurobi manual (2026) | Solver/tool provenance | Official software documentation |

### Literature matrix

| Theme | Core sources | Role in the manuscript |
|---|---|---|
| Isolation-aware allocation | 5Guard paper/code; ITU-T X.1816 | Baseline and integration gap |
| 5G security requirements | 3GPP 33.501; ITU-T X.1814/X.1816 | Standards motivation |
| Security-driven isolation | Javadpour et al. | Nearest security-control work |
| Learned admission | Troia; Asdikian; Jacoby | Learning context and counter-risk |
| Traffic-risk estimation | Sheikhi; dataset repository; Breiman | Detector design and data limits |
| Optimization implementation | 5Guard code; Gurobi manual | Reproducibility |

### Coverage advisory and gaps

- `DISTRIBUTIONAL_SKEW_ADVISORY`: 12/13 sources (92.3%) are from 2022–2026.
  The skew matches the recent 5G focus; Breiman (2001) supplies the foundational
  algorithm reference.
- The empirical research sources are dominated by computational or simulation
  methods. No real-network SecGuard deployment evidence is present.
- The exact integration of telemetry risk, an SLA floor, quarantine, and
  constrained threshold selection within the 5Guard implementation was not
  found in this focused source set. The paper states this as bounded positioning,
  not as a universal “first.”
- Measured attack propagation and cross-dataset generalization remain uncovered.

## Phase 2: Approved paper architecture

The existing IEEE conference structure was retained and tightened:

| Section | Purpose | Approx. words |
|---|---|---:|
| Abstract | Problem, method, primary results, counter-result | 200 |
| Introduction | Motivation, RQs, scoped contributions | 450 |
| Background and related work | Establish nearest work and precise delta | 400 |
| System model and objective | Define safety invariant, proxy, constraint | 400 |
| SecGuard design | Detector, adapter, surrogate | 450 |
| Experimental methodology | Separation, baselines, statistics, latency | 500 |
| Results | Primary outcomes, oracle, ablation, operational metrics | 750 |
| Discussion and threats | Interpret findings and bound validity | 650 |
| Reproducibility, conclusion, declarations | Handoff and accountability | 350 |

## Phase 3: Argument blueprint

Central thesis: SecGuard demonstrates that telemetry-derived risk can be
connected safely to 5Guard and can recover profit relative to conservative
fixed thresholds while reducing modeled exposure relative to static allocation;
the present evidence does not show that surrogate search beats random search or
that the controller contains real attacks.

| Sub-argument | Evidence | Strongest counter-argument | Treatment |
|---|---|---|---|
| SLA-safe integration is feasible | Adapter tests and unchanged 5Guard allocator | A threshold adapter is incremental | Position novelty as evaluated integration, not a new allocator |
| Learned thresholds improve the fixed baseline | 30 paired scenarios, Wilcoxon p=.0028, dz=.69 | Fixed thresholds may be intentionally conservative | Report exposure increase versus fixed and avoid free-security claims |
| Security/profit balance improves versus static | 67.12% proxy reduction with 90.44% profit retention | Proxy is not containment | Label it modeled exposure everywhere |
| The learner approaches an oracle | 2.41% held-out regret, p=.284 | Random-81 finds the same oracle | Disclose the equality and deny search-superiority evidence |
| Quarantine is not validated | No-quarantine ablation raises raw profit; proxy unchanged | Quarantine may still contain attacks | Identify missing propagation metric as the required experiment |

## Phase 4: Writer contract record

### Paper-blind pre-commitment

- D1 section completeness: write every approved section and declaration.
- D2 citation density: cite external facts and tie experimental claims to JSON.
- D3 blueprint fidelity: preserve all counter-arguments and qualifications.
- D4 total word count: remain within 10% of the 3,000-word target.
- D5 section allocation: keep emphasis on methods, results, and validity.
- D6 paragraph structure: use claim–evidence–interpretation flow where suitable.
- D7 register consistency: use precise engineering language throughout.

`[PRE-COMMITMENT-ACKNOWLEDGED]`

### Writer self-score

| Dimension | Result | Evidence |
|---|---|---|
| D1 section completeness | Pass | All planned sections and five declaration items are present |
| D2 citation density | Pass | 13/13 bibliography keys are cited; original results point to the artifact |
| D3 blueprint fidelity | Pass | Random and quarantine counter-results remain explicit |
| D4 total word count | Pass | Conference-length draft is approximately 3,000 words |
| D5 per-section balance | Pass | Methods/results/discussion receive the largest allocation |
| D6 paragraph structure | Pass | Results and discussion connect claims to evidence and limits |
| D7 register consistency | Pass | Engineering terminology is consistent |

Writer decision: `writer_decision=accept`.

## Phase 5: Citation and abstract gates

### Citation audit

| Metric | Result |
|---|---:|
| Unique in-text citation keys | 13 |
| Bibliography entries | 13 |
| Missing bibliography entries | 0 |
| Uncited bibliography entries | 0 |
| Metadata/DOI corrections | 5 entries plus one author-name correction |
| Sources from 2022–2026 | 12/13 (92.3%) |

Corrections added verified DOIs for Sheikhi and Kostakos, Javadpour et al.,
Troia et al., Asdikian et al., and the Jacoby et al. arXiv record. The Javadpour
co-author was corrected from “Farhad” to “Forough.” Self-citation cannot be
assessed until author identities are supplied. Retraction status was not
programmatically certified and should be checked again at submission.

### Bilingual abstract gate

- English abstract: 190 words.
- Traditional Chinese abstract: 414 non-space characters.
- Components: background, purpose, method, findings, implications (5/5 each).
- Keywords: six per language.
- Output: `paper/abstracts.md`.

## Phase 6: In-pair peer review

### Paper-blind scoring plan

The evaluator committed to checking a specific contribution and engagement with
prior work (D1), replicable method and explicit limitations (D2), evidence for
all core claims including adverse results (D3), RQ-to-conclusion alignment
(D4), and readable IEEE-consistent prose with referenced figures/tables (D5).
Missing or irreproducible methods and cherry-picked evidence were defined as
blocking conditions before the manuscript was scored.

### Dimension scores

| Dimension | Contract result | Score | Rationale |
|---|---|---:|---|
| D1 originality | Warn | 7/10 | Useful evaluated integration, but no demonstrated advantage over equal-budget random search |
| D2 methodological rigor | Pass | 8/10 | Exact split, seeds, grids, weights, baselines, tests, and limits are reported |
| D3 evidence sufficiency | Pass | 9/10 | Favorable, null, and unfavorable controls are all disclosed |
| D4 argument coherence | Pass | 9/10 | RQ1–RQ3 are answered consistently in discussion and conclusion |
| D5 writing quality | Pass | 8/10 | Clear conference register; source compilation still unavailable |
| **Weighted total** |  | **8.25/10** | Accept range |

Failure conditions F1, F2, F3, and F6 did not fire. F4 fired because the
high-priority originality dimension carries a warning while both mandatory
dimensions pass. Evaluator decision:
`evaluator_decision=accept_with_dissent_note`.

### Dissent note and remaining work

The manuscript is suitable as an MTP proof-of-concept paper and presentation
base. A stronger research submission still needs repeated random-search learning
curves, a larger policy space/topology, cross-dataset detection, and a security
outcome that distinguishes L2 from quarantine. A TeX compiler was unavailable,
so the source passed deterministic checks but not PDF typesetting.

## Phase 7: Visualization and IEEE formatting

### Figure quality gate

- Chart choice: a scatter plot plus nondominated frontier directly represents
  the profit--exposure relationship; marker shape and color identify policies.
- Dimensions: 6.9 by 4.1 inches for IEEE double-column placement.
- Resolution: 300 DPI (2,070 by 1,230 pixels).
- Accessibility: the ARS colorblind-safe categorical palette is used, with no
  red--green distinction as the sole encoding.
- Labels: both axes state the quantity, direction of preference, and units.
- Integrity: the plot is generated directly from all 165 candidate records in
  `artifacts/research_validation.json`.
- Visual verification: PASS after inspection at original resolution; no label
  truncation, overlap, missing series, or chart junk was observed.

```yaml
figure_table_trace:
  - artifact_id: "fig-pareto"
    source_data:
      dataset_id: "secguard-validation-2026-08-14"
      file: "artifacts/research_validation.json#training"
    transformation:
      script: "src/secguard/research_validation.py::_plot_pareto"
      hash: "4c93953b823beb053587b207727bcc2c26ac7a98"
    caption_claim: "The plot covers all 165 training policies; Oracle and Random-81 overlap, while Learned has equal training profit and higher modeled exposure."
    supported_manuscript_claims:
      - claim: "Equal-budget random search found the exhaustive training oracle, and many threshold policies lie on profit plateaus."
        locator: "Results, Oracle and search-efficiency controls"
    limitations:
      - "Each point is an aggregate over only five training scenarios."
      - "Modeled exposure is a design proxy, not measured attack propagation."
      - "The figure shows point estimates rather than uncertainty intervals."
  - artifact_id: "tab-policy-results"
    source_data:
      dataset_id: "secguard-validation-2026-08-14"
      file: "artifacts/research_validation.json#test"
    transformation: "manual derivation: each table cell is the corresponding test.<policy>.<metric>.mean value, rounded to the displayed precision"
    caption_claim: "The table reports held-out aggregate outcomes for six policies over 30 paired scenarios."
    supported_manuscript_claims:
      - claim: "Learned SecGuard improves profit over Fixed and reduces modeled exposure relative to Static while retaining most Static profit."
        locator: "Results, Held-out economic and security outcomes"
      - claim: "The no-quarantine ablation has higher raw profit but identical modeled exposure."
        locator: "Results, Quarantine ablation and operational cost"
    limitations:
      - "Scenarios are trace-derived from a single public data source."
      - "Aggregates do not demonstrate deployment-level generalization."
  - artifact_id: "tab-paired-tests"
    source_data:
      dataset_id: "secguard-validation-2026-08-14"
      file: "artifacts/research_validation.json#statistical_tests"
    transformation: "manual derivation: paired test rows transcribe statistic, two-sided p_value, effect_size_dz, and positive/negative/ties fields with display rounding"
    caption_claim: "The table reports paired two-sided Wilcoxon tests and paired standardized effects for the four preregistered comparisons."
    supported_manuscript_claims:
      - claim: "Learned profit exceeds Fixed and learned exposure is below Static, while differences from Oracle and No-quarantine are not significant."
        locator: "Results"
    limitations:
      - "No multiplicity adjustment was applied; the tests answer distinct research comparisons."
      - "The 30 scenarios are simulation replicates rather than independent network deployments."
```

### Formatting record

- Target: IEEE conference manuscript using `IEEEtran`.
- Citation style: numbered IEEE references with 13 cited bibliography entries.
- Deliverables: `main.tex`, `references.bib`, `abstracts.md`, this workflow
  record, and reproducible validation artifacts.
- Deterministic paper check: balanced braces, complete citation keys, present
  figures, synchronized headline claims, and five declaration items all pass.
- Compilation status: advisory warning only. No TeX distribution is installed
  in the environment, so final pagination and visual typesetting require a
  machine with `pdflatex` and `bibtex`.
