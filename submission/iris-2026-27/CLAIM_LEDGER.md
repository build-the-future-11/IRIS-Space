# IRIS 2026–27 — Claim-to-Artifact Ledger

This ledger is the submission control surface. A claim may enter the synopsis, paper, video, poster, or portal only if its evidence row is complete enough for that use.

| Claim | Evidence class | Canonical source | Current status | Submission wording |
|---|---|---|---|---|
| 24 productive historical campaign runs | Historical operations | `PIPELINE_OPERATIONS_RECORD.md`; manuscript appendix | SUPPORTED, reconciliation still required by paper checklist B01 | “surviving record contains 24 productive runs” |
| 3,824 distinct broker objects | Historical operations | `PIPELINE_OPERATIONS_RECORD.md`; `paper/siderea_transient_triage.tex` | SUPPORTED in manuscript; B01 final reconciliation open | “3,824 distinct broker objects in surviving campaign record” |
| 30 existing TNS objects among 200 recorded registry checks | Historical stage-specific count | manuscript + campaign records | SUPPORTED AS STAGE-SPECIFIC ONLY | Never convert to purity/accuracy |
| 55 known/suspected variables among 193 catalog evaluations | Historical stage-specific count | manuscript + campaign records | SUPPORTED AS STAGE-SPECIFIC ONLY | Never combine denominator with TNS stage |
| Early-veto fraction 54.5% → 2.68% and shortlist fraction 0.51% → 13.9% around policy discontinuity | Historical observational comparison | manuscript; figure generator; audit bootstrap record | SUPPORTED DESCRIPTIVELY | Must state policy/time/input population are confounded; no causal claim |
| Run-cluster bootstrap change in early-veto fraction −0.518, 95% interval [−0.812, −0.282] | Historical statistical summary | `paper/AUDIT.md`; manuscript figure source | SUPPORTED subject to artifact digest completion | State resampling unit and observational limitation |
| Run-cluster bootstrap change in shortlist fraction +0.134, 95% interval [0.098, 0.171] | Historical statistical summary | `paper/AUDIT.md`; manuscript figure source | SUPPORTED subject to artifact digest completion | State resampling unit and observational limitation |
| Current candidate/evidence pipeline fails closed when required evidence is missing | Software invariant | current source/tests; `paper/AUDIT.md` | SOFTWARE-SUPPORTED | Do not convert into scientific completeness/safety guarantee |
| Clean snapshot: 499 tests + 103 parameterized subtests | Software verification | `paper/FINAL_PAPER_CHECKLIST.md`; `paper/research/software-verification-2026-09-13.json` | SUPPORTED FOR FROZEN SNAPSHOT | Include exact revision from verification record |
| Deterministic replay reproduced archived numerical artifacts | Software verification | `paper/AUDIT.md`; software verification record | SUPPORTED | Scope to archived/reconstructed artifacts |
| Synthetic template search can recover injected signals under controlled conditions | Synthetic experiment | `paper/experiments/`; manuscript | SUPPORTED CONDITIONALLY | Must identify as synthetic |
| Synthetic search shows severe false-alarm inflation under misspecified noise | Synthetic adverse result | `paper/experiments/`; `paper/AUDIT.md`; manuscript | SUPPORTED AND REQUIRED | Keep visible in summary/video |
| SIDEREA real-sky completeness / precision / recall | Prospective scientific outcome | none | UNSUPPORTED | PROHIBITED |
| Learned model outperforms existing brokers / baselines on representative sky data | Comparative scientific outcome | none | UNSUPPORTED | PROHIBITED |
| TNS designation implies spectroscopic/physical class | Registry/physical interpretation | none | FALSE BOUNDARY | PROHIBITED |
| Both historical claimed TNS designations are independently verified end-to-end | Primary registry evidence | paper checklist B04 | OPEN | Narrow wording until B04 closes |

## Before final export

For every retained quantitative claim:
- [ ] add exact source path;
- [ ] add exact source revision / commit SHA;
- [ ] add transformation/reproduction command where applicable;
- [ ] add figure/table filename;
- [ ] add digest if the manuscript audit uses one;
- [ ] confirm the claim has not expanded beyond the evidence class.

## Locked-work rule

No row may be upgraded using a held-out/locked evaluation unless a separate authorization gate explicitly opens that evaluation. This ledger is a packaging tool, not result-bearing authorization.
