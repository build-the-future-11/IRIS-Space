# SIDEREA: An Auditable Pipeline for Human-Supervised Optical Transient Triage

Main source: `siderea_transient_triage.tex`

Bibliography: `references.bib`

Local arXiv layout package: `arxivrefined.sty`

Research synthesis and claim-audit working files are stored under `research/`.
The completed scientific and production assessment is in `AUDIT.md`.

Build with a standard LaTeX distribution:

```bash
latexmk -pdf siderea_transient_triage.tex
```

Or build with Tectonic:

```bash
tectonic --keep-intermediates siderea_transient_triage.tex
```

The checked build also retains `siderea_transient_triage.bbl`, which should be included
with the source bundle when required by an arXiv submission workflow.

The XeTeX/Tectonic layout resolves TeX Gyre Termes, Heros and Cursor from the
TeX distribution by filename. It does not require Times New Roman, Helvetica
or Menlo installed on the operating system. The pdfLaTeX route retains its
Times/Helvetica-compatible TeX fonts and may paginate differently.

Historical figures come from `figures/make_figures.py`. Synthetic search figures
and per-trial results come from `experiments/run_transient_search.py` and
`experiments/run_noise_stress.py`; see `../docs/TRANSIENT_SEARCH.md` for commands.
These experiment directories preserve separate protocols and source snapshots.
Use new output directories when reproducing them; never overwrite earlier results.

The manuscript is deliberately framed as a legacy operational audit plus an
implementation-level SIDEREA safety analysis, not a classifier benchmark. The stage
totals are not a closed cohort, and software tests are not scientific validation;
preserve both caveats when adapting the text or abstract.

The author block contains Aadi Ajeesh Nair and Ryan Gomez and is ready for circulation.
If a journal-specific version is needed, convert the document class while
preserving the decision-state semantics, cohort caveats, and figure captions.
