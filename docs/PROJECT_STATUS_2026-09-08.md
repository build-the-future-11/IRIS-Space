# SIDEREA: current status, implementation quality and next work

Updated 2026-09-08 during the autonomous finishing session. The current operating backlog is [PROJECT_FINISH_CHECKLIST.md](../PROJECT_FINISH_CHECKLIST.md). The [September 7 review](FULL_CODE_REVIEW_2026-09-07.md) describes the starting state; its findings are historical and must not be read as if this session's fixes had not happened.

## What this project is for

SIDEREA turns irregular astronomical observations into an explainable, finite human-review queue and preserves the evidence behind each decision. Its primary users are transient screeners, scientific reviewers and researchers evaluating selection policies. Its strongest possible product is a reproducible discovery workbench: intake → evidence → prioritization → independent review → outcome → measured improvement.

It currently implements a local research workflow. It does not establish an autonomous discovery service, calibrated discovery probabilities, an operational telescope network or a scientifically validated prospective campaign. Shipping the local research package and qualifying scientific deployment are separate milestones.

## What is implemented well

- **Evidence rather than score controls reportability.** Missing, failed, stale or unrelated catalogue evidence blocks clearance. A model score cannot bypass that boundary.
- **Reproducibility is structural.** Analysis retains the exact ingested bytes, configuration and code provenance, deterministic scientific fingerprints, candidate versions and terminal manifests.
- **Photometry respects physical channels.** Survey/passband separation and separate magnitude/flux handling avoid misleading pooled measurements. Missing uncertainties and non-detections remain explicit.
- **Review history has real semantics.** Immutable evidence versions, append-only decisions and historical reconstruction prevent old approvals silently following changed evidence.
- **Capacity is modeled.** The queue has a finite budget, anomaly reserve, reproducible audit sampling and recorded audit propensities.
- **The learning code is executable.** The logistic baseline has chronological partitions and held-out calibration. JEPA contains actual training, EMA targets, masking, checkpointing and collapse diagnostics. Scientific usefulness still needs experiments.
- **The security posture is conservative.** Strict configuration, HTML escaping, CSRF and Host checks, no unattended submission endpoint, and now explicit authenticated-review policies are appropriate foundations.
- **Recovery and negative paths receive attention.** New tests exercise concurrent broker writes, exact replay, credential rejection, incident dispositions, corrupted storage, cohort mismatches and real HTTP decisions.

## Substantial changes made in this session

| Area | Starting problem | Implemented change |
|---|---|---|
| Fixture storage | Nested credentials and empty response bodies crossed the wrong boundaries | Recursive structured credential rejection, URL/cookie/body checks, empty-body round trips |
| Study qualification | Unrelated or policy-mismatched summaries could satisfy gates | Exact cohort/outcome/policy bindings and recomputation of benchmark metrics from recorded inputs |
| Readiness claims | Diagnostic presence could sound like scientific promotion | Version-2 promotion reports explicitly describe local evidence review; diagnostic, fixture and asset scopes are named |
| Authentication | Typed names could appear independent; browser/adjudication paths lacked equivalent integration | Immutable authentication policy, trusted keys, assertion lifetime/expiry checks, persisted verification envelope, signed browser and adjudication paths |
| Broker operations | Cursor races, ambiguous retries and irreversible dead-letter failure status | Transactional watermark updates, fact-checked retries, actual replay verification and append-only resolution |
| Recovery | A declaration could overwrite reserved status; resolved incidents remained permanent failures | Reserved-field checks, UTC comparisons, incident lifecycle and an executed SQLite backup/restore check |
| Cohorts | Caller timestamps looked prospective and selection was manually detached from queues | Separate capture modes/times, one entity per study, budget enforcement, verified review-set enrollment with route and audit metadata |
| Review interface | Raw evidence was hard to inspect and queues lacked navigation | Filtering/pagination, summaries, channel-local SVG measurements/error bars/limits, responsive CSS and HTTP integration coverage |
| Asset packaging | Calibration fields existed without enough type/position checking | Finite/ranged calibration validation, candidate-position association and bundle path containment |
| Pipeline failures | Ledger initialization could leave an unterminated run | Initialization falls inside terminal-failure handling |
| Packaging and checks | Supported-version and local artifact gaps | Python 3.12 CI coverage, generated coverage ignores, current pandas typing fixes and clean-source-distribution wheel verification |

## What is genuinely incomplete

| Component | Classification | What is real | What must not be claimed yet |
|---|---|---|---|
| Local analysis, ranking and ledgers | Working product code | Actual ingestion, features, persistence and evidence gates | Complete live operational qualification |
| Catalogue and broker adapters | Working integrations awaiting qualification | Real request/parse/retry code and explicit failures | That current live services were tested in this session |
| Review UI | Working local interface | Real forms, persistence, role checks and evidence previews | A complete multi-user identity/access platform |
| Signed principal assertions | Authentication integration primitive | Signature verification, roles, expiry and trusted-key policies | Independent people are verified without a trusted issuer; HMAC key holders can mint identities |
| Rolling-origin benchmark | Real numerical diagnostic | Temporal evaluation of supplied scores, uncertainty and reproducible inputs | A rolling refit pipeline or proof that score generation never saw future data |
| Injection/recovery | Real diagnostic, narrower than the desired experiment | Known-location Gaussian matched-filter recovery | End-to-end production selection completeness, realistic population recovery or false-positive control |
| Promotion report | Implemented evidence aggregator | Bound local consistency checks and signoffs | Scientific deployment approval or production readiness |
| Image/forced-photometry bundle | Packaging and integrity implementation | Files, digests, role completeness and typed calibration metadata | FITS/WCS scientific correctness or independent survey calibration |
| Service fixtures | Capture/replay primitive | Exact request matching and response bytes | That a `live` label proves a real capture, or that every fixture was replayed through its actual adapter |
| Operations ledger | Local operations primitive | Events, schema comparisons, incident resolution and backup checks | Continuous monitoring, alert delivery, sustained service availability or full disaster recovery |
| Broker archive | Working persistence primitive | Bytes, cursor transactions, replay and dead letters | A supervised polling daemon with backfill, leases and operational alerting |
| Follow-up utility | Implemented heuristic primitive | A formula over caller-supplied factors | Real observability, information gain, scheduling or telescope requests |
| Campaign profiles | Advisory configuration/data | Named campaign ideas and priorities | Enforced scientific operational policies |
| JEPA/anomaly/retrieval | Working research implementation | Training and numerical/index primitives | Better discovery yield than simpler baselines |
| Report submission | Intentionally absent | Read-only preflight; legacy submission entry point exits 78 | A finished exporter, transport or approved external submission |
| Legacy scripts and duplicate tree | Historical implementations | Executable prior approaches kept for provenance | A second supported production path with the same safety contracts |

The active-package scan did not reveal broad fake `TODO`/`NotImplemented` bodies. Protocol `...` declarations are interfaces; exception-handler `pass` is not automatically scaffolding. The main unfinished area is the gap between a real primitive and a complete, measured workflow. A function can be fully executable yet insufficient evidence for the scientific claim someone wants to attach to it.

## Remaining weaknesses and how to improve them

1. **Scientific claims outrun available observations.** Freeze a real campaign, collect the complete eligible denominator and mature outcomes, and publish useful-effect intervals even when disappointing. Do not tune the endpoint after looking at results.
2. **Prediction provenance is incomplete.** Record model/checkpoint, preprocessing, training cutoff, feature cutoff and prediction creation time per evaluation block. Reconstruct the score from the permitted information or reject the block.
3. **Several operational capabilities are still caller-driven.** Introduce a bounded supervised intake/retry process, adapter replay harness and automatic operational events only after defining their contracts and failure budgets.
4. **Authentication has a trusted-local-process boundary.** Integrate a real issuer, key custody/rotation and server-side per-user sessions before hosting for multiple people. A shared local assertion file is a single session, not multi-user login.
5. **Image interpretation remains external.** Decode supported scientific formats and validate coordinates, time, passband, WCS and calibration against real survey products; retain human adjudication for ambiguous evidence.
6. **The UI needs scientific-user evaluation.** Verify real desktop/mobile rendering, keyboard use and screen-reader labels; measure time to review and disagreement rather than adding decorative dashboards.
7. **Packaging can inherit stale local build artifacts.** The clean wheel produced from an sdist passed the existing identity test. Preserve or move aside old generated build output after package renames; never weaken the test to tolerate the retired package.
8. **Maintainability should follow measured pain.** Split the large CLI into command families and isolate persistence migration logic when behavior-preserving tests cover those interfaces. Avoid a stack rewrite.

## Highest-value extensions

Build these in order, conditional on the preceding evidence:

1. A reviewer-centered evidence workbench with real image stamps, review-set navigation and an unresolved-evidence inbox.
2. An outcome dashboard showing yield at the review budget, missing outcomes, workload, review latency and disagreement with honest denominators.
3. A prospective shadow comparison of heuristic, logistic and JEPA-derived scores using the same frozen arrivals and budget.
4. Broker backfill/replay supervision plus an adapter fault matrix that verifies outages cannot produce clearances.
5. Facility-aware follow-up recommendations with observability and constraints, followed by explicit human-approved request and result tracking.
6. Audited cross-survey entity linking and retrieval explanations, then additional survey adapters once the common measurement contract is explicit.

These are opportunities, not claims that every extension should be implemented. The operating checklist gives specific problems, solutions and acceptance criteria. There is no credible “nothing else can ever change” endpoint; the release target is reproducible behavior with tested boundaries and accurately stated remaining evidence.

## Verification

See the final validation section of [PROJECT_FINISH_CHECKLIST.md](../PROJECT_FINISH_CHECKLIST.md). Counts in the September 7 audit are the baseline, not the final result. No live catalogue campaign, telescope action, external report, push, merge or deployment is claimed by this document.


## Re-audit implementation update

The outcome dashboard is now implemented (JSON CLI and authenticated local HTTP route),
with current-version denominators, missing outcomes, disagreements and conditional yield.
One-ledger evidence backups now include all referenced run files, verify their publication
bindings offline, and block incomplete restores. This does not provide coordinated
multi-database recovery. A TNS offline runner now exercises the real parser without a
network fallback; other adapter qualification remains outstanding. Cohort batches are
atomic. Schema-5 upgrade has a preserved-fixture regression test. Reviewers can download
all observations from the exact displayed evidence version, including archived versions.

These supersede the earlier descriptions of those capabilities as missing. Resettable
MJD/survey/band plot filtering, stale-version comparison, and an authenticated
preflight-blocker inbox have since been implemented. Immutable review-set navigation,
hosted per-user identity and full scientific qualification remain open.
The final browser attempt was denied because browser policy verification
was unavailable; no bypass or successful final visual pass is claimed.
