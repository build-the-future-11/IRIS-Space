# SIDEREA publication next actions — 2026-09-15

## Publication decision

Publish the current line first as a methods/software paper with bounded historical operational evidence and synthetic detector diagnostics. Do not wait for a full prospective real-sky validation campaign unless the target venue requires empirical performance claims. Keep completeness, purity, classifier accuracy, real-sky discovery yield, and physical-classification claims explicitly out of scope until the frozen prospective campaign is complete.

## Evidence already strong enough to write around

- A full manuscript source and rendered paper already exist under `paper/`.
- The historical 24-run campaign accounting is reproducible from the retained operations record.
- The manuscript separates ranking, evidence, reportability, registry state, and physical classification rather than collapsing them into one score.
- Current local verification records 405 tests plus 96 subtests, 78.35% coverage, and strict typing across 74 source files.
- Synthetic transient-search, correlated-noise, covariance-follow-up, and learning-smoke artifacts retain protocols, exact runner/model source snapshots, dependency versions, seeds, per-trial statistics, summaries, and figures.
- The P04 reconstruction closure records equality of preserved primary statistics/counts after implementation evolution.
- The paper includes a 50,000-draw run-cluster bootstrap for the historical policy-regime comparison.
- A deterministic research-bundle builder and regression tests now exist.

## Missing experiment for stronger scientific claims

The decisive missing empirical experiment is the already-defined prospective real-data campaign, not another synthetic benchmark. Freeze and execute one object-grouped, time-forward campaign that preserves every eligible arrival and rejection, binds prediction-time information, archives point-in-time broker/external evidence, records matured outcomes, and obtains independent scientific review.

Until that campaign exists, the paper must remain a methods/software paper rather than claim real-sky completeness, precision, or model superiority.

## Baseline gap

For the future prospective comparison, use the prespecified same-cohort/same-budget matrix already implied by the research plan:

1. incumbent heuristic ranking;
2. calibrated logistic baseline;
3. template-search method;
4. JEPA-derived ranking.

All methods must see the same frozen objects, eligible information, review budget, and outcome definitions. Report uncertainty, missing outcomes, runtime, reviewer burden, and adverse cases. Retain the simpler method if additional complexity does not establish useful improvement.

## Ablation gap

For a future empirical paper, the valuable ablations are operational rather than decorative: evidence/reportability gates, noise-model assumptions, template-grid mismatch, and learned-route contribution under a fixed review budget. The existing synthetic failures must remain visible. Do not promote adaptive/oracle-covariance follow-up evidence into a preregistered success claim.

For the current methods/software paper, no new learned-model ablation is needed before submission.

## Reproducibility gap

The reproducibility package is already unusually strong, but three closure items matter before release:

1. Close R07 by qualifying output collisions, unreadable/unwritable paths, interruption behavior, and recoverable manifests.
2. Resolve the P06 public-bundle licensing/redistribution decision without inventing permissions.
3. After the final submission candidate is frozen, regenerate one exact-SHA manuscript/research-bundle receipt and record hashes for the PDF, sources, figures, bibliography, protocols, and result artifacts.

## Manuscript gap

The current `paper/siderea_transient_triage.tex` and PDF provide a real manuscript base. The final pass should make the scope impossible to misread: historical operational selectivity plus evidence-bound software architecture plus synthetic diagnostics. Keep the adverse correlated-noise and isolated-outlier results, distinguish adaptive follow-up from frozen evidence, and label JEPA/supervised learning artifacts as synthetic smoke tests unless future prospective evidence changes that status.

## Submission gap

Before a methods/software submission, close R07, P06 licensing/redistribution, exact-SHA paper verification, final author/contact metadata, target-venue formatting, and submission receipt retention. An independent scientific signoff is mandatory before upgrading to real-data performance claims; software CI cannot substitute for it.

## Single next move

Freeze the methods/software scope now. Close R07 and the P06 licensing/public-bundle gate, then regenerate the manuscript and deterministic research bundle from one exact candidate SHA. Submit that bounded paper rather than waiting for speculative model improvements.

## Future empirical upgrade path

Only after the current paper is frozen should the project execute S01-S08: preregister one campaign, preserve the full denominator, define outcome labels, bind prediction-time information, use time-forward/entity-disjoint evaluation, choose the uncertainty unit, execute the shadow campaign, and obtain independent scientific review.
