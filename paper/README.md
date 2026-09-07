# IRIS: An Auditable Pipeline for Human-Supervised Optical Transient Triage

Main source: `ispy_transient_search.tex`

Bibliography: `references.bib`

Local arXiv layout package: `arxivrefined.sty`

Research synthesis and claim-audit working files are stored under `research/`.
The completed scientific and production assessment is in `AUDIT.md`.

Build with a standard LaTeX distribution:

```bash
latexmk -pdf ispy_transient_search.tex
```

Or build with Tectonic:

```bash
tectonic ispy_transient_search.tex
```

The checked build also retains `ispy_transient_search.bbl`, which should be included
with the source bundle when required by an arXiv submission workflow.

The manuscript is deliberately framed as a legacy operational audit plus an
implementation-level IRIS safety analysis, not a classifier benchmark. The stage
totals are not a closed cohort, and software tests are not scientific validation;
preserve both caveats when adapting the text or abstract.

The author block contains Aadi Ajeesh Nair and Ryan Gomez and is ready for circulation.
If a journal-specific version is needed, convert the document class while
preserving the decision-state semantics, cohort caveats, and figure captions.
