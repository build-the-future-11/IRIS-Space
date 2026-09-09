# P06 public-research-bundle audit — 2026-09-09

Target input revision: `a74e8ad3412d628c0ca23523f1d42e67f984cf9e` on the submission-readiness branch.

## Scope

This pass closes the mechanically independent packaging portion of `FINAL_TODO.md` P06 without changing scientific claims, protocols, thresholds, seeds, model behavior, or retained outcomes. The correlated-noise and isolated-outlier failures remain failures; the covariance follow-up remains adaptive/oracle-covariance evidence; no real-sky validation claim is added.

## Packaging gate added

`tools/build_research_bundle.py` now creates a deterministic, allowlisted `tar.gz` research-alpha source bundle from a clean checkout. The archive:

- includes the manuscript source, bibliography, retained `.bbl`, local LaTeX style, figures and figure-generation code;
- includes the retained experiment and research evidence, including protocols, source snapshots, per-trial statistics, reconstruction receipt and claim/source ledger;
- includes source code, tests, examples, configs, release documentation and build metadata needed to inspect the software claim;
- excludes Git metadata, caches and `.coverage`;
- normalizes archive metadata and gzip timestamps so identical files plus the same source revision produce identical archive bytes;
- writes `RESEARCH_BUNDLE_MANIFEST.json` containing the supplied source revision and SHA-256/size for every included file.

`tests/test_research_bundle.py` makes the bundle contract executable. It checks deterministic archive bytes, manifest/source-revision binding, allowlist hygiene, author/contact consistency between `pyproject.toml` and the manuscript, the presence of the Data Availability section, bibliography/source inputs, existence of every manuscript `\includegraphics` target, and preservation of the current proprietary-license warning.

## P06 criterion audit

| P06 requirement | Evidence | Status |
| --- | --- | --- |
| Author/title/contact details | `pyproject.toml`; `paper/siderea_transient_triage.tex`; executable consistency test | Mechanically bound. |
| Data/code availability wording | Manuscript `Data Availability`; `docs/RESEARCH_ALPHA_RELEASE.md` | Present and appropriately limited: tracked audit material is described, intentionally untracked campaign material is disclosed, and the record is not represented as fully reconstructable. |
| Bibliography/source inclusion | `paper/references.bib`, retained `.bbl`, `.tex`, `arxivrefined.sty`; bundle test | Included by the deterministic bundle builder. |
| Figure inclusion/reproducibility | Every manuscript `\includegraphics` target must exist; `paper/figures/make_figures.py` and experiment artifacts are included | Mechanically checked. |
| Release commit identity | `--source-revision` is required and copied into the bundle manifest | Mechanically bound; the exact final submission SHA must still be supplied after the submission candidate is frozen. |
| License compatibility | `pyproject.toml` remains `LicenseRef-Proprietary`; no open-source grant is asserted | **BLOCKED on explicit copyright-owner licensing decision.** The builder itself states that archive creation grants no redistribution rights. |
| Clean source-bundle construction | Deterministic builder plus regression test | Implemented; exact-head CI is the acceptance receipt. |

## Gate decision

The reproducible packaging mechanics and inclusion/metadata checks are now independently closed **subject to exact-head CI**. P06 as a whole is **not** closed because the repository still lacks an explicit redistribution/license decision from the copyright owners. Public GitHub visibility is not permission to call the bundle open source or freely redistributable.

No license was invented, no untracked campaign data was reconstructed, and no scientific result was regenerated or reinterpreted.

## Remaining submission risks

1. **License/redistribution is the P06 blocker.** Until the copyright owners choose explicit terms, describe this as a reviewable source/research package rather than an openly reusable release.
2. **Final revision receipt.** After the submission candidate is frozen, build the archive with that exact SHA and retain its manifest/archive SHA-256. Do not reuse this input SHA if later source or paper changes land.
3. **Manuscript verification freshness.** `paper/research/manuscript-verification.json` records a successful 29-page Tectonic build, but any later manuscript-affecting change requires a new verification receipt on the final submission SHA.
4. **R07 remains independent and open.** Output-collision/interruption qualification is still required for the broader research-alpha release; this packaging pass does not relabel it as complete.

## Single best next action

Let exact-head CI validate the new bundle contract. If green, the next human decision is the explicit code/data/manuscript redistribution license. Once that is resolved, freeze the final submission SHA, generate the deterministic archive with that exact revision, retain `RESEARCH_BUNDLE_MANIFEST.json` plus the archive SHA-256, and refresh manuscript verification only if the manuscript inputs changed.
