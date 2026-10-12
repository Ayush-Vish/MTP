# SecGuard thesis report

This folder adapts the chapter structure and LaTeX class of `reports/Final_report` to the SecGuard material in `reports/report1/main.tex`. The source draft and the other student's report are unchanged.

Main document: `main.tex`.

Build from this folder with pdfLaTeX and BibTeX:

```text
pdflatex main
bibtex main
pdflatex main
pdflatex main
```

On Overleaf, upload this entire folder, set `main.tex` as the main document, and choose pdfLaTeX.

The report retains the supplied numerical results with preliminary synthetic-evaluation qualifications. Objectives 2 and 3 remain proposed work. The bibliography contains 20 cited entries derived from the original draft and existing project records; this is not a complete external reference verification.

The class, chapter styling package, and margin configuration are identical to the reference template. Front-matter order, chapter opening overviews, numbering, and bibliography style follow it. Caption spacing and abstract formatting have also been aligned. Five numbered tables summarize objectives, isolation mechanisms, policy actions, evaluation scope, and results.

Three literature-review images are extracted from the local 5Guard base paper. Two unrelated programming-framework images formerly used in Chapter 3 have been replaced with editable TikZ diagrams of the SecGuard workflow. No LaTeX compiler is available locally, so final pagination and visual layout still require compilation in Overleaf or a local TeX installation.
