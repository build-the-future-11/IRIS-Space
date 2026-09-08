# Source inventory for the 2026-09-07 review

This is an AST inventory of every existing tracked Python file in the inspected working tree, including legacy duplicates, tests, and paper tools. Successful parsing establishes syntax structure, not behavioral correctness. Deep review findings and acceptance criteria are in [the full review](FULL_CODE_REVIEW_2026-09-07.md).

Generated build copies, virtual environments, caches, runtime outputs, and bytecode were not treated as independent source implementations. No applicable AGENTS.md was found in the repository scan.

| File | Lines | Classes | Functions/methods | Module description |
|---|---:|---:|---:|---|
| [ai_candidate_hunter.py](/Volumes/PRO-BLADE/IRIS-Project/ai_candidate_hunter.py) | 599 | 1 | 17 | AI-assisted multi-object transient hunter. |
| [blackhole_candidate_hunter.py](/Volumes/PRO-BLADE/IRIS-Project/blackhole_candidate_hunter.py) | 524 | 1 | 19 | Search for black-hole-related optical candidates. |
| [build_tns_report.py](/Volumes/PRO-BLADE/IRIS-Project/build_tns_report.py) | 36 | 0 | 1 | Fail-closed tombstone for the retired legacy TNS report builder. |
| [catalog_validation_engine.py](/Volumes/PRO-BLADE/IRIS-Project/catalog_validation_engine.py) | 397 | 0 | 14 | Validate transient candidates against stellar and variable-star catalogs. |
| [cool-stuff-master/ai_candidate_hunter.py](/Volumes/PRO-BLADE/IRIS-Project/cool-stuff-master/ai_candidate_hunter.py) | 599 | 1 | 17 | AI-assisted multi-object transient hunter. |
| [cool-stuff-master/blackhole_candidate_hunter.py](/Volumes/PRO-BLADE/IRIS-Project/cool-stuff-master/blackhole_candidate_hunter.py) | 524 | 1 | 19 | Search for black-hole-related optical candidates. |
| [cool-stuff-master/build_tns_report.py](/Volumes/PRO-BLADE/IRIS-Project/cool-stuff-master/build_tns_report.py) | 33 | 0 | 1 | Fail-closed tombstone for the archived legacy TNS report builder. |
| [cool-stuff-master/catalog_validation_engine.py](/Volumes/PRO-BLADE/IRIS-Project/cool-stuff-master/catalog_validation_engine.py) | 397 | 0 | 14 | Validate transient candidates against stellar and variable-star catalogs. |
| [cool-stuff-master/distant_reservoir_catalog.py](/Volumes/PRO-BLADE/IRIS-Project/cool-stuff-master/distant_reservoir_catalog.py) | 541 | 0 | 18 | Build a known-object catalog for distant comet reservoirs. |
| [cool-stuff-master/fetch_alerce_detections.py](/Volumes/PRO-BLADE/IRIS-Project/cool-stuff-master/fetch_alerce_detections.py) | 76 | 0 | 2 | Fetch live ALeRCE ZTF detections into a CSV usable by optical_transient_pipeline.py. |
| [cool-stuff-master/final_candidate_filter.py](/Volumes/PRO-BLADE/IRIS-Project/cool-stuff-master/final_candidate_filter.py) | 251 | 0 | 8 | Build the final reportable transient shortlist. |
| [cool-stuff-master/optical_transient_pipeline.py](/Volumes/PRO-BLADE/IRIS-Project/cool-stuff-master/optical_transient_pipeline.py) | 795 | 1 | 21 | End-to-end optical transient pipeline. |
| [cool-stuff-master/run_1000_candidate_hunt.py](/Volumes/PRO-BLADE/IRIS-Project/cool-stuff-master/run_1000_candidate_hunt.py) | 125 | 0 | 3 | Run a medium ALeRCE/ZTF transient-candidate sweep. |
| [cool-stuff-master/verify_candidates.py](/Volumes/PRO-BLADE/IRIS-Project/cool-stuff-master/verify_candidates.py) | 314 | 1 | 11 | Verify transient candidates and keep likely new objects only. |
| [distant_reservoir_catalog.py](/Volumes/PRO-BLADE/IRIS-Project/distant_reservoir_catalog.py) | 541 | 0 | 18 | Build a known-object catalog for distant comet reservoirs. |
| [fetch_alerce_detections.py](/Volumes/PRO-BLADE/IRIS-Project/fetch_alerce_detections.py) | 76 | 0 | 2 | Fetch live ALeRCE ZTF detections into a CSV usable by optical_transient_pipeline.py. |
| [final_candidate_filter.py](/Volumes/PRO-BLADE/IRIS-Project/final_candidate_filter.py) | 251 | 0 | 8 | Build the final reportable transient shortlist. |
| [optical_transient_pipeline.py](/Volumes/PRO-BLADE/IRIS-Project/optical_transient_pipeline.py) | 795 | 1 | 21 | End-to-end optical transient pipeline. |
| [paper/figures/make_figures.py](/Volumes/PRO-BLADE/IRIS-Project/paper/figures/make_figures.py) | 780 | 1 | 16 | Reproduce manuscript figures from the I SPY operations record. |
| [run_1000_candidate_hunt.py](/Volumes/PRO-BLADE/IRIS-Project/run_1000_candidate_hunt.py) | 126 | 0 | 3 | Run a medium ALeRCE/ZTF transient-candidate sweep. |
| [src/siderea/__init__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/__init__.py) | 30 | 0 | 0 | SIDEREA astronomical discovery platform. |
| [src/siderea/__main__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/__main__.py) | 6 | 0 | 0 | Allow ``python -m siderea`` to behave like the ``siderea`` command. |
| [src/siderea/anomaly.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/anomaly.py) | 242 | 3 | 5 | Interpretable robust anomaly baseline with optional Isolation Forest. |
| [src/siderea/atomic.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/atomic.py) | 104 | 0 | 5 | Secure, durable same-directory atomic file publication. |
| [src/siderea/bands.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/bands.py) | 51 | 0 | 1 | Canonical passband labels shared by feature and representation pipelines. |
| [src/siderea/campaigns.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/campaigns.py) | 132 | 1 | 2 | Advisory science-campaign concepts for experiment planning. |
| [src/siderea/cli.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/cli.py) | 1825 | 0 | 55 | Command-line interface for the SIDEREA discovery and review platform. |
| [src/siderea/clients/__init__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/clients/__init__.py) | 5 | 0 | 0 | External-service adapters with explicit, fail-closed results. |
| [src/siderea/clients/base.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/clients/base.py) | 104 | 2 | 3 | Shared retry and result handling for remote astronomy services. |
| [src/siderea/clients/catalogs.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/clients/catalogs.py) | 294 | 4 | 16 | Lazy, fail-closed adapters for SkyBoT, SIMBAD, and VSX. |
| [src/siderea/clients/tns.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/clients/tns.py) | 254 | 2 | 10 | Transient Name Server search client with no write/submission capability. |
| [src/siderea/config.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/config.py) | 554 | 10 | 22 | Strict, typed TOML configuration for SIDEREA. |
| [src/siderea/data/__init__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/data/__init__.py) | 5 | 0 | 0 | Dataset and photometry data utilities. |
| [src/siderea/data/snapshot.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/data/snapshot.py) | 68 | 2 | 2 | Hashed dataset snapshots for reproducible training and backtests. |
| [src/siderea/domain.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/domain.py) | 248 | 6 | 12 | Core, dependency-free domain types used throughout SIDEREA. |
| [src/siderea/evaluation.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/evaluation.py) | 191 | 1 | 5 | Leakage-aware metrics centered on finite nightly review capacity. |
| [src/siderea/evidence_context.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/evidence_context.py) | 137 | 0 | 4 | Canonical context evidence produced alongside external verification checks. |
| [src/siderea/features/__init__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/features/__init__.py) | 20 | 0 | 0 | Scientific feature extraction for SIDEREA observations. |
| [src/siderea/features/photometry.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/features/photometry.py) | 984 | 1 | 22 | Filter-aware features for irregular astronomical photometry. |
| [src/siderea/followup.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/followup.py) | 105 | 2 | 4 | Transparent urgency and observability ranking for human-approved follow-up. |
| [src/siderea/host.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/host.py) | 407 | 3 | 6 | Transparent angular host-association utilities. |
| [src/siderea/identity.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/identity.py) | 222 | 1 | 7 | Short-lived, signed principal assertions for authenticated review workflows. |
| [src/siderea/ingest/__init__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ingest/__init__.py) | 27 | 0 | 0 | Photometry ingestion adapters and canonical schema utilities. |
| [src/siderea/ingest/alerce.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ingest/alerce.py) | 562 | 1 | 12 | Optional, lazy ALeRCE broker adapter. |
| [src/siderea/ingest/base.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ingest/base.py) | 182 | 5 | 8 | Shared contracts for obtaining candidate photometry. |
| [src/siderea/ingest/csv.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ingest/csv.py) | 213 | 0 | 1 | Local CSV ingestion with alias resolution and content provenance. |
| [src/siderea/ingest/schema.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ingest/schema.py) | 453 | 0 | 9 | Strict schema resolution and canonicalization for photometry tables. |
| [src/siderea/ingest/snapshot.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ingest/snapshot.py) | 54 | 0 | 1 | Integrity contract for broker-produced CSV snapshots. |
| [src/siderea/integrity.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/integrity.py) | 494 | 0 | 14 | Self-verifying scientific candidate records. |
| [src/siderea/ledger.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ledger.py) | 1186 | 4 | 22 | SQLite-backed scientific outcome and independent-review ledger. |
| [src/siderea/manifest.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/manifest.py) | 214 | 2 | 9 | Immutable-ish, atomic run manifests for reproducible pipeline execution. |
| [src/siderea/ml/__init__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ml/__init__.py) | 87 | 0 | 0 | Optional representation-learning tools for SIDEREA light curves. |
| [src/siderea/ml/baseline.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ml/baseline.py) | 707 | 5 | 23 | Leakage-resistant supervised baseline for candidate prioritisation. |
| [src/siderea/ml/dataset.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ml/dataset.py) | 656 | 3 | 20 | Light-curve tokenization and batching for SIDEREA representation learning. |
| [src/siderea/ml/evaluate.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ml/evaluate.py) | 319 | 1 | 8 | Evaluation and embedding extraction for the optional SIDEREA TS-JEPA path. |
| [src/siderea/ml/jepa.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ml/jepa.py) | 623 | 4 | 20 | A compact irregular-time Joint-Embedding Predictive Architecture. |
| [src/siderea/ml/train.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ml/train.py) | 439 | 1 | 9 | Small, reproducible training and checkpoint APIs for the SIDEREA TS-JEPA. |
| [src/siderea/operations/__init__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/__init__.py) | 25 | 0 | 0 | Durable replay, evidence-asset, and operational qualification tools. |
| [src/siderea/operations/assets.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/assets.py) | 231 | 1 | 7 | Content-bound image-triplet and forced-photometry evidence bundles. |
| [src/siderea/operations/broker_store.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/broker_store.py) | 342 | 2 | 10 | Durable, replayable storage for content-bound broker snapshots. |
| [src/siderea/operations/fixtures.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/fixtures.py) | 256 | 1 | 10 | Content-addressed recorded HTTP/service fixtures for deterministic replay. |
| [src/siderea/operations/observability.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/observability.py) | 294 | 2 | 10 | Append-only operational events, schema qualification, and recovery drills. |
| [src/siderea/pipeline.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/pipeline.py) | 965 | 1 | 25 | Deterministic local SIDEREA analysis pipeline. |
| [src/siderea/promotion.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/promotion.py) | 544 | 2 | 10 | Fail-closed scientific-promotion evidence and authenticated sign-offs. |
| [src/siderea/provenance.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/provenance.py) | 342 | 3 | 16 | Provenance primitives used by every external scientific check. |
| [src/siderea/ranking.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ranking.py) | 251 | 3 | 7 | Deterministic, capacity-aware nightly review queues. |
| [src/siderea/reporting/__init__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/reporting/__init__.py) | 5 | 0 | 0 | Human-gated reporting helpers. |
| [src/siderea/reporting/preflight.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/reporting/preflight.py) | 417 | 1 | 6 | Preflight checks that must pass before any report draft is considered ready. |
| [src/siderea/research/__init__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/research/__init__.py) | 20 | 0 | 0 | Prospective-study and scientific-evaluation infrastructure. |
| [src/siderea/research/benchmark.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/research/benchmark.py) | 235 | 0 | 5 | Rolling-origin, finite-budget comparisons for precomputed ranking signals. |
| [src/siderea/research/cohort.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/research/cohort.py) | 390 | 2 | 12 | Append-only prospective cohort enrollment and exact-version outcome export. |
| [src/siderea/research/injection.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/research/injection.py) | 193 | 0 | 3 | Deterministic, explicitly simulated light-curve injection/recovery experiments. |
| [src/siderea/research/preregistration.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/research/preregistration.py) | 404 | 1 | 15 | Frozen, machine-verifiable prospective study protocols. |
| [src/siderea/review/__init__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/review/__init__.py) | 16 | 0 | 0 | Human-review artifacts and local adjudication service. |
| [src/siderea/review/assembly.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/review/assembly.py) | 525 | 1 | 9 | Build portable, evidence-bound nightly review sets. |
| [src/siderea/review/dossier.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/review/dossier.py) | 141 | 0 | 6 | Generate a portable, evidence-first candidate review dossier. |
| [src/siderea/review/server.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/review/server.py) | 436 | 2 | 16 | Small, local-only candidate review service backed by the SIDEREA ledger. |
| [src/siderea/scoring/__init__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/scoring/__init__.py) | 5 | 0 | 0 | Transparent candidate-priority scoring. |
| [src/siderea/scoring/heuristic.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/scoring/heuristic.py) | 383 | 1 | 8 | A bounded, inspectable heuristic priority for transient candidates. |
| [src/siderea/similarity.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/similarity.py) | 213 | 2 | 7 | Small, dependency-light cosine index for scientific analogue retrieval. |
| [src/siderea/state.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/state.py) | 203 | 3 | 6 | Candidate lifecycle and fail-closed evidence gating. |
| [src/siderea/validation/__init__.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/validation/__init__.py) | 27 | 0 | 0 | Scientific safety gates. |
| [src/siderea/validation/binding.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/validation/binding.py) | 475 | 1 | 11 | Bind completed external-check evidence to one candidate and query policy. |
| [src/siderea/validation/catalog_policy.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/validation/catalog_policy.py) | 233 | 1 | 4 | Convert raw SIMBAD evidence into a conservative scientific veto decision. |
| [src/siderea/validation/gates.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/validation/gates.py) | 156 | 2 | 2 | Fail-closed reportability decisions. |
| [src/siderea/validation/suite.py](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/validation/suite.py) | 344 | 2 | 6 | Coordinated, provenance-rich external validation for one candidate. |
| [tests/test_atomic.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_atomic.py) | 60 | 1 | 3 | No module docstring. |
| [tests/test_baseline_ranking_host.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_baseline_ranking_host.py) | 508 | 4 | 25 | No module docstring. |
| [tests/test_cli.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_cli.py) | 684 | 1 | 22 | No module docstring. |
| [tests/test_clients.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_clients.py) | 243 | 7 | 22 | No module docstring. |
| [tests/test_config_domain.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_config_domain.py) | 322 | 2 | 24 | No module docstring. |
| [tests/test_core_trust_boundaries.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_core_trust_boundaries.py) | 757 | 14 | 53 | No module docstring. |
| [tests/test_evidence_binding.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_evidence_binding.py) | 178 | 1 | 8 | No module docstring. |
| [tests/test_jepa.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_jepa.py) | 815 | 3 | 23 | CPU-small tests for the optional SIDEREA irregular-time TS-JEPA path. |
| [tests/test_ledger_versions.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_ledger_versions.py) | 640 | 1 | 13 | No module docstring. |
| [tests/test_legacy_reporting_quarantine.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_legacy_reporting_quarantine.py) | 77 | 1 | 3 | No module docstring. |
| [tests/test_packaging.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_packaging.py) | 29 | 0 | 3 | Distribution-contract checks that also run from an editable checkout. |
| [tests/test_photometry_features.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_photometry_features.py) | 421 | 0 | 21 | No module docstring. |
| [tests/test_pipeline_ingest.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_pipeline_ingest.py) | 1048 | 4 | 37 | No module docstring. |
| [tests/test_reproducibility.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_reproducibility.py) | 117 | 1 | 8 | No module docstring. |
| [tests/test_review_assembly.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_review_assembly.py) | 384 | 1 | 9 | No module docstring. |
| [tests/test_review_server.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_review_server.py) | 205 | 1 | 11 | No module docstring. |
| [tests/test_safety_foundation.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_safety_foundation.py) | 659 | 2 | 21 | No module docstring. |
| [tests/test_science_platform.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_science_platform.py) | 185 | 3 | 17 | No module docstring. |
| [tests/test_scoring.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_scoring.py) | 167 | 0 | 10 | No module docstring. |
| [tests/test_similarity.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_similarity.py) | 117 | 0 | 8 | No module docstring. |
| [tests/test_verification_suite.py](/Volumes/PRO-BLADE/IRIS-Project/tests/test_verification_suite.py) | 233 | 5 | 16 | No module docstring. |
| [verify_candidates.py](/Volumes/PRO-BLADE/IRIS-Project/verify_candidates.py) | 314 | 1 | 11 | Verify transient candidates and keep likely new objects only. |
