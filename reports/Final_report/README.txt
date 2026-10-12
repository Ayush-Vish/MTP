MTP Mid-Term Report - Aaditya Karki (2022IMT-001)
==================================================
Main file : MTP_Report_2022IMT001.tex   (class pkmthesis.cls, same structure as MTP_Report_Template_2022.tex)

Build (pdfLaTeX, as with the template):
    pdflatex MTP_Report_2022IMT001
    bibtex   MTP_Report_2022IMT001
    pdflatex MTP_Report_2022IMT001
    pdflatex MTP_Report_2022IMT001
On Overleaf: upload the whole folder and set the compiler to pdfLaTeX, main document MTP_Report_2022IMT001.tex.
(The .eps logo is converted automatically by epstopdf, as in the template.)

Layout
  FrontPages/      title_page, Certificate (declaration), Acknowledgement, Acronyms, institute logo
  chapters/1..4/   one .tex file per chapter: Introduction, Literature Review, Proposed Methodology, Experiments and Results
  chapters/references/references.bib   15 references, unsrt style (numbered in order of citation)
  figures/basepaper/    figures cropped from the base paper (Wang et al., IEEE TMC 2026), cited in captions
  figures/replication/  charts regenerated from the replication outputs (gpn_repro_results.zip)
  Diagrams (GPN architecture, maintenance loop, testbed, replication pipeline) are TikZ, inside the chapter files.

Packages added to the template preamble: xcolor, tikz, array, tabularx, makecell, algorithm, algpseudocode.
Required TeX Live collections: latex-extra, pictures, science, pstricks, plain-generic, fonts-extra (for bbm), as the template itself needs.
