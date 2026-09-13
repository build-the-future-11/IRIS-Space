"""Command-line interface for the SIDEREA discovery and review platform."""

from __future__ import annotations

import argparse
import contextlib
import hmac
import importlib.util
import json
import math
import os
import platform
import secrets
import shutil
import sqlite3
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from siderea import __version__
from siderea.atomic import atomic_create_binary, atomic_write_text, fsync_directory
from siderea.config import ConfigError, SIDEREAConfig, config_to_dict, load_config

_SCIENTIFIC_PACKAGES = (
    "numpy",
    "pandas",
    "sklearn",
    "torch",
    "astropy",
    "astroquery",
    "alerce",
    "matplotlib",
)


def _config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="TOML configuration (default: SIDEREA_CONFIG, checkout config, or packaged default)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="siderea",
        description="Reproducible, human-supervised astronomical transient discovery.",
    )
    parser.add_argument("--version", action="version", version=f"SIDEREA {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="check local runtime readiness")
    _config_argument(doctor)
    doctor.add_argument(
        "--strict",
        action="store_true",
        help="treat missing optional scientific dependencies as errors",
    )
    doctor.add_argument("--json", action="store_true", help="emit machine-readable output")

    show = commands.add_parser("config-show", help="validate and print effective configuration")
    _config_argument(show)

    analyze = commands.add_parser("analyze", help="analyze a local photometry CSV")
    analyze.add_argument("input", type=Path)
    _config_argument(analyze)
    analyze.add_argument("-o", "--output-dir", type=Path, default=None)
    analyze.add_argument("--ledger", type=Path, default=None)
    analyze.add_argument("--run-id", default=None)
    analyze.add_argument(
        "--column",
        action="append",
        default=[],
        metavar="LOGICAL=PHYSICAL",
        help="explicit input-column mapping; repeat as needed",
    )
    analyze.add_argument(
        "--checks-json",
        action="append",
        type=Path,
        default=[],
        help="verification result JSON; repeat for multiple candidates",
    )
    analyze.add_argument("--coordinate-tolerance-arcsec", type=float, default=2.0)

    broker = commands.add_parser("broker-fetch", help="fetch a bounded canonical broker snapshot")
    _config_argument(broker)
    broker.add_argument("output", type=Path, help="destination CSV (must not already exist)")
    broker.add_argument(
        "--broker",
        choices=("alerce",),
        default=None,
        help="broker adapter (default: hunt.broker from configuration)",
    )
    broker.add_argument(
        "--survey",
        choices=("ztf", "lsst"),
        default="ztf",
        help="ALeRCE survey namespace (default: ztf)",
    )
    broker.add_argument(
        "--classifier",
        default=None,
        help=(
            "ALeRCE classifier name (survey-aware default: "
            "lc_classifier_transient for ZTF, stamp_classifier_rubin_beta for LSST)"
        ),
    )
    broker.add_argument(
        "--classifier-version",
        default=None,
        help=(
            "expected LSST classifier version; required with a custom LSST classifier "
            "and rejected for ZTF"
        ),
    )
    broker.add_argument(
        "--class",
        dest="broker_classes",
        action="append",
        default=None,
        help=(
            "broker class filter; repeat as needed (default: hunt.broker_classes for ZTF, "
            "the qualified SN profile for LSST)"
        ),
    )

    verify = commands.add_parser("verify", help="run fail-closed external catalogue checks")
    _config_argument(verify)
    verify.add_argument("candidate_id")
    verify.add_argument("ra", type=float)
    verify.add_argument("dec", type=float)
    verify.add_argument("peak_mjd", type=float)
    verify.add_argument(
        "--skybot-mjd",
        action="append",
        type=float,
        default=[],
        help="additional distinct detection epoch to clear with SkyBoT; repeat as needed",
    )
    verify.add_argument(
        "--quality-passed",
        action="store_true",
        help="affirm that upstream photometry/image quality gates passed",
    )
    verify.add_argument(
        "--disable-network",
        action="store_true",
        help="emit explicit disabled evidence without making remote calls",
    )
    verify.add_argument("-o", "--output", type=Path, default=None)

    queue = commands.add_parser("queue", help="allocate a reproducible nightly review queue")
    _config_argument(queue)
    queue.add_argument("input", type=Path, help="candidate ranking CSV")
    queue.add_argument("--budget", type=int, default=None)
    queue.add_argument("--anomaly-slots", type=int, default=None)
    queue.add_argument("--anomaly-threshold", type=float, default=0.8)
    queue.add_argument("--audit-slots", type=int, default=None)
    queue.add_argument(
        "--audit-seed",
        default=None,
        help="replay seed for random audit selection (generated and recorded if omitted)",
    )
    queue.add_argument(
        "--eligibility-policy",
        choices=("triage", "gate-clear"),
        default="triage",
        help="triage admits quality-passing pending checks; gate-clear requires completed evidence",
    )
    queue.add_argument("-o", "--output", type=Path, default=None)

    review_set = commands.add_parser(
        "review-set",
        help="atomically package a nightly queue and its candidate dossiers",
    )
    _config_argument(review_set)
    review_set.add_argument("ranking_csv", type=Path)
    review_set.add_argument("candidates_json", type=Path)
    review_set.add_argument("output_dir", type=Path, help="new portable review-set directory")
    review_set.add_argument("--budget", type=int, default=None)
    review_set.add_argument("--anomaly-slots", type=int, default=None)
    review_set.add_argument("--anomaly-threshold", type=float, default=0.8)
    review_set.add_argument("--audit-slots", type=int, default=None)
    review_set.add_argument(
        "--audit-seed",
        default=None,
        help="replay seed for random audit selection (generated and recorded if omitted)",
    )
    review_set.add_argument(
        "--eligibility-policy",
        choices=("triage", "gate-clear"),
        default="triage",
    )

    dossier = commands.add_parser("dossier", help="render a portable candidate evidence dossier")
    dossier.add_argument("candidates_json", type=Path)
    dossier.add_argument("candidate_id")
    dossier.add_argument("-o", "--output-dir", type=Path, required=True)

    review_add = commands.add_parser("review-add", help="append a role-labelled review event")
    _config_argument(review_add)
    review_add.add_argument("candidate_id")
    review_add.add_argument("--ledger", type=Path, default=None)
    review_add.add_argument(
        "--candidate-version",
        required=True,
        help="immutable version digest shown in the reviewed candidate record",
    )
    review_identity = review_add.add_mutually_exclusive_group(required=True)
    review_identity.add_argument("--reviewer")
    review_identity.add_argument(
        "--principal-assertion",
        type=Path,
        help="short-lived signed assertion issued by the configured authentication gateway",
    )
    review_add.add_argument(
        "--principal-key",
        type=Path,
        default=None,
        help="shared verification-key file required with --principal-assertion",
    )
    review_add.add_argument("--role", choices=("screener", "reviewer"), required=True)
    review_add.add_argument(
        "--verdict",
        choices=("approve", "reject", "needs_more_data", "abstain"),
        required=True,
    )
    review_add.add_argument("--reason", required=True)

    adjudication = commands.add_parser(
        "adjudication-add",
        help="resolve ambiguous catalogue context for one immutable candidate version",
    )
    _config_argument(adjudication)
    adjudication.add_argument("candidate_id")
    adjudication.add_argument("--ledger", type=Path, default=None)
    adjudication.add_argument("--candidate-version", required=True)
    adjudication.add_argument("--adjudicator")
    adjudication.add_argument("--principal-assertion", type=Path)
    adjudication.add_argument("--principal-key", type=Path)
    adjudication.add_argument(
        "--verdict",
        choices=("clear_context", "reject", "needs_more_data"),
        required=True,
    )
    adjudication.add_argument("--reason", required=True)

    review_serve = commands.add_parser("review-serve", help="serve the local review UI")
    _config_argument(review_serve)
    review_serve.add_argument("--ledger", type=Path, default=None)
    review_serve.add_argument(
        "--host", choices=("127.0.0.1", "localhost", "::1"), default="127.0.0.1"
    )
    review_serve.add_argument("--port", type=int, default=8765)
    review_serve.add_argument("--principal-assertion", type=Path)
    review_serve.add_argument("--principal-key", type=Path)

    outcome = commands.add_parser("outcome-add", help="record a confirmed downstream outcome")
    _config_argument(outcome)
    outcome.add_argument("candidate_id")
    outcome.add_argument("--ledger", type=Path, default=None)
    outcome.add_argument("--candidate-version", required=True)
    outcome.add_argument("--outcome", required=True)
    outcome.add_argument("--designation", default="")
    outcome.add_argument("--taxonomy-version", default="siderea.outcome.v1")
    outcome.add_argument("--evidence-json", type=Path, default=None)
    summary = commands.add_parser(
        "outcome-summary", help="summarize current-version review workload and outcomes"
    )
    _config_argument(summary)
    summary.add_argument("--ledger", type=Path, default=None)

    preflight = commands.add_parser(
        "preflight",
        help="check whether an immutable candidate version is report-ready",
    )
    _config_argument(preflight)
    preflight.add_argument("candidate_id")
    preflight.add_argument("--ledger", type=Path, default=None)
    preflight.add_argument(
        "--candidate-version",
        required=True,
        help="immutable version digest shown in the reviewed candidate record",
    )

    baseline = commands.add_parser(
        "baseline-train",
        help="train and evaluate the leakage-resistant supervised baseline",
    )
    baseline.add_argument("input", type=Path)
    baseline.add_argument("output", type=Path, help="new model bundle directory")
    baseline.add_argument("--label", required=True, help="binary target column")
    baseline.add_argument("--time", required=True, help="chronological split column")
    entity_policy = baseline.add_mutually_exclusive_group(required=True)
    entity_policy.add_argument("--entity", help="source ID used for leakage purging")
    entity_policy.add_argument(
        "--assert-unique-entities",
        action="store_true",
        help="explicitly assert that every input row is a distinct physical entity",
    )
    baseline.add_argument("--features", nargs="+", required=True)
    baseline.add_argument("--train-fraction", type=float, default=0.70)
    baseline.add_argument("--calibration-fraction", type=float, default=0.15)
    baseline.add_argument("--calibration", choices=("sigmoid", "none"), default="sigmoid")
    baseline.add_argument("--review-budget", type=int, default=10)

    jepa = commands.add_parser("jepa-train", help="train TS-JEPA in the isolated research path")
    _config_argument(jepa)
    jepa.add_argument("train_jsonl", type=Path)
    jepa.add_argument("validation_jsonl", type=Path)
    jepa.add_argument("output", type=Path, help="new checkpoint bundle directory")
    jepa.add_argument("--epochs", type=int, default=10)
    jepa.add_argument("--batch-size", type=int, default=None)
    jepa.add_argument("--device", default="cpu")
    jepa.add_argument(
        "--split-policy",
        choices=("chronological", "predefined"),
        default="chronological",
        help="chronological is enforced; predefined is an explicit external-split assertion",
    )
    jepa.add_argument("--evaluation-masks", type=int, default=5)
    jepa.add_argument(
        "--allow-nondeterministic",
        action="store_true",
        help="permit faster backend algorithms whose results may not reproduce exactly",
    )
    jepa.add_argument(
        "--require-prediction-cutoffs",
        action="store_true",
        help="require entity_id and prediction_cutoff_mjd and reject future observations",
    )

    jepa_embed = commands.add_parser(
        "jepa-embed", help="extract provenance-bound JEPA embeddings for a shadow experiment"
    )
    jepa_embed.add_argument("checkpoint", type=Path)
    jepa_embed.add_argument("input_jsonl", type=Path)
    jepa_embed.add_argument("output", type=Path)
    jepa_embed.add_argument("--batch-size", type=int, default=64)
    jepa_embed.add_argument("--device", default="cpu")
    jepa_embed.add_argument(
        "--reference-cohort",
        type=Path,
        default=None,
        help="bind embeddings to a frozen JEPA anomaly-reference cohort",
    )

    reference_freeze = commands.add_parser(
        "jepa-reference-freeze", help="freeze the exact JEPA anomaly-reference population"
    )
    reference_freeze.add_argument("input_jsonl", type=Path)
    reference_freeze.add_argument("output", type=Path)
    reference_freeze.add_argument("--cohort-id", required=True)
    reference_freeze.add_argument("--selection-policy", required=True)

    shadow_assemble = commands.add_parser(
        "shadow-assemble", help="assemble separate detector and JEPA anomaly evidence"
    )
    shadow_assemble.add_argument("transient_search", type=Path)
    shadow_assemble.add_argument("candidate_embeddings", type=Path)
    shadow_assemble.add_argument("reference_embeddings", type=Path)
    shadow_assemble.add_argument("output", type=Path)
    shadow_assemble.add_argument(
        "--pipeline-candidates",
        type=Path,
        default=None,
        help="bind immutable candidates.json from Aadi's operational analysis path",
    )
    shadow_assemble.add_argument("--pipeline-manifest", type=Path, default=None)
    shadow_assemble.add_argument("--pilot-manifest", type=Path, default=None)
    shadow_assemble.add_argument("--reference-cohort", type=Path, default=None)
    shadow_assemble.add_argument("--random-state", type=int, default=17)

    shadow_rank = commands.add_parser(
        "shadow-rank", help="allocate separate heuristic, template, JEPA, and audit review routes"
    )
    shadow_rank.add_argument("evidence", type=Path)
    shadow_rank.add_argument("output", type=Path)
    shadow_rank.add_argument("--budget", type=int, required=True)
    shadow_rank.add_argument("--detector-slots", type=int, required=True)
    shadow_rank.add_argument("--jepa-slots", type=int, required=True)
    shadow_rank.add_argument("--jepa-threshold", type=float, default=0.8)
    shadow_rank.add_argument("--audit-slots", type=int, default=0)
    shadow_rank.add_argument("--audit-seed", default=None)

    pilot_prepare = commands.add_parser(
        "pilot-prepare", help="prepare one cutoff-bound detector and JEPA dataset bundle"
    )
    pilot_prepare.add_argument("input", type=Path)
    pilot_prepare.add_argument("output", type=Path, help="new prepared-data directory")
    pilot_prepare.add_argument("--prediction-cutoff-mjd", type=float, required=True)
    pilot_prepare.add_argument("--flux-unit", required=True)
    pilot_prepare.add_argument("--calibration", required=True)
    pilot_identity = pilot_prepare.add_mutually_exclusive_group(required=True)
    pilot_identity.add_argument("--entity-column")
    pilot_identity.add_argument("--assert-source-is-entity", action="store_true")
    pilot_detection = pilot_prepare.add_mutually_exclusive_group(required=True)
    pilot_detection.add_argument("--detection-column")
    pilot_detection.add_argument("--assume-measured-detections", action="store_true")
    pilot_prepare.add_argument(
        "--require-pipeline-view",
        action="store_true",
        help="require ra_deg and dec_deg and emit canonical operational pipeline photometry",
    )

    transient_shard = commands.add_parser(
        "transient-shard", help="partition measured flux without splitting physical entities"
    )
    transient_shard.add_argument("input", type=Path)
    transient_shard.add_argument("output", type=Path)
    transient_shard.add_argument("--max-channels", type=int, default=100)

    transient_merge = commands.add_parser(
        "transient-merge", help="verify and merge compatible transient-search shard outputs"
    )
    transient_merge.add_argument("output", type=Path)
    transient_merge.add_argument("inputs", nargs="+", type=Path)

    study = commands.add_parser(
        "study-freeze", help="validate and freeze a prospective study protocol"
    )
    study.add_argument("protocol_json", type=Path)
    study.add_argument("output", type=Path)

    cohort_enroll = commands.add_parser(
        "cohort-enroll", help="append exact candidate versions to a prospective cohort"
    )
    cohort_enroll.add_argument("preregistration", type=Path)
    cohort_enroll.add_argument("candidates_json", type=Path)
    cohort_enroll.add_argument("registry", type=Path)
    cohort_enroll.add_argument(
        "--selected-id",
        action="append",
        default=[],
        help="candidate selected inside the finite review budget; repeat as needed",
    )
    cohort_enroll.add_argument("--stratum", default="main")
    cohort_enroll.add_argument("--enrolled-at", default=None)
    cohort_enroll.add_argument(
        "--review-set", type=Path, help="derive selection from a verified review set"
    )

    cohort_export = commands.add_parser(
        "cohort-export", help="export matured exact-version outcomes for a frozen cohort"
    )
    cohort_export.add_argument("preregistration", type=Path)
    cohort_export.add_argument("registry", type=Path)
    cohort_export.add_argument("ledger", type=Path)
    cohort_export.add_argument("output", type=Path)
    cohort_export.add_argument("--as-of", default=None)

    benchmark = commands.add_parser(
        "benchmark-run", help="run a preregistered rolling-origin ranking comparison"
    )
    benchmark.add_argument("preregistration", type=Path)
    benchmark.add_argument("input", type=Path)
    benchmark.add_argument("output", type=Path)
    benchmark.add_argument("--entity", required=True)
    benchmark.add_argument("--time", required=True)
    benchmark.add_argument("--label", required=True)
    benchmark.add_argument("--scores", nargs="+", required=True)
    benchmark.add_argument("--minimum-history-blocks", type=int, default=2)
    benchmark.add_argument("--time-block-days", type=float, default=None)
    benchmark.add_argument(
        "--cohort", type=Path, help="bind to a matured cohort with binary labels"
    )

    transient = commands.add_parser(
        "transient-search", help="shadow search of measured flux with calibrated template trials"
    )
    transient.add_argument("input", type=Path)
    transient.add_argument("output", type=Path)
    transient.add_argument("--width-days", type=float, action="append", default=[])
    transient.add_argument("--centers", type=int, default=21)
    transient.add_argument("--null-trials", type=int, default=999)
    transient.add_argument(
        "--null-method",
        choices=("gaussian", "wild_residual"),
        default="gaussian",
        help="parametric Gaussian or conditional wild-residual calibration",
    )
    transient.add_argument(
        "--wild-block-size",
        type=int,
        default=1,
        help="consecutive epochs sharing one sign in wild-residual calibration",
    )
    transient.add_argument("--seed", type=int, default=0)
    transient.add_argument("--alpha", type=float, default=0.01)
    transient.add_argument(
        "--survey-object-count",
        type=int,
        default=None,
        help="complete predeclared object universe for campaign-level correction",
    )
    transient.add_argument(
        "--planned-looks",
        type=int,
        default=1,
        help="total monitoring looks declared before inspecting results",
    )
    transient.add_argument(
        "--look-index",
        type=int,
        default=1,
        help="one-based index of this look within the predeclared campaign",
    )
    transient.add_argument(
        "--prediction-cutoff-mjd",
        type=float,
        default=None,
        help="latest observation time permitted in this point-in-time shadow run",
    )
    transient.add_argument(
        "--noise-timescale-days",
        type=float,
        default=None,
        help="declared exponential covariance timescale; 80%% correlated variance, never fitted",
    )

    injection = commands.add_parser(
        "injection-run", help="run a preregistered deterministic injection-recovery study"
    )
    injection.add_argument("preregistration", type=Path)
    injection.add_argument("input", type=Path)
    injection.add_argument("output", type=Path)
    injection.add_argument("--source", default="source_id")
    injection.add_argument("--time", default="mjd")
    injection.add_argument("--flux", default="flux")
    injection.add_argument("--error", default="flux_error")
    injection.add_argument("--amplitude", action="append", type=float, default=[])
    injection.add_argument("--width-days", type=float, default=1.0)
    injection.add_argument("--threshold-sigma", type=float, default=5.0)
    injection.add_argument("--trials", type=int, default=200)

    live_tns = commands.add_parser(
        "tns-qualify", help="run one read-only live TNS search qualification case"
    )
    live_tns.add_argument("query_json", type=Path)
    live_tns.add_argument("output", type=Path)
    live_tns.add_argument("--expected-status", choices=("clear", "match"), required=True)
    live_tns.add_argument("--expected-name", action="append", default=[])

    fixture_record = commands.add_parser(
        "fixture-record", help="archive a sanitized service response for exact replay"
    )
    qualify = commands.add_parser(
        "fixture-qualify-tns", help="execute recorded fixtures through the TNS parser"
    )
    qualify.add_argument("query_json", type=Path)
    qualify.add_argument("output", type=Path)
    qualify.add_argument("fixtures", nargs="+", type=Path)
    qualify.add_argument("--expected-status", choices=("clear", "match", "error"), required=True)
    fixture_record.add_argument("service")
    fixture_record.add_argument("service_version")
    fixture_record.add_argument("request_json", type=Path)
    fixture_record.add_argument("response_file", type=Path)
    fixture_record.add_argument("output", type=Path)
    fixture_record.add_argument("--capture-mode", choices=("live", "synthetic"), required=True)
    fixture_record.add_argument("--scenario", choices=("success", "failure"), required=True)
    fixture_record.add_argument("--status-code", type=int, required=True)
    fixture_record.add_argument("--headers-json", type=Path, default=None)

    fixture_verify = commands.add_parser(
        "fixture-verify", help="verify a recorded service fixture and optional replay request"
    )
    fixture_verify.add_argument("fixture", type=Path)
    fixture_verify.add_argument("--request-json", type=Path, default=None)

    broker_archive = commands.add_parser(
        "broker-archive", help="archive a published broker snapshot with a monotonic watermark"
    )
    broker_archive.add_argument("archive", type=Path)
    broker_archive.add_argument("photometry_csv", type=Path)
    broker_archive.add_argument("--stream", required=True)
    broker_archive.add_argument("--cursor", required=True)
    broker_archive.add_argument("--watermark-mjd", type=float, required=True)

    broker_replay = commands.add_parser(
        "broker-replay", help="recreate an exact broker snapshot from the durable archive"
    )
    broker_replay.add_argument("archive", type=Path)
    broker_replay.add_argument("snapshot_id")
    broker_replay.add_argument("output_dir", type=Path)
    broker_inventory = commands.add_parser(
        "broker-inventory", help="list snapshots and unresolved dead letters"
    )
    broker_inventory.add_argument("archive", type=Path)
    broker_check = commands.add_parser(
        "broker-check", help="reconstruct and validate archived broker snapshots"
    )
    broker_check.add_argument("archive", type=Path)
    dead_resolve = commands.add_parser(
        "dead-letter-resolve", help="append an evidenced dead-letter disposition"
    )
    dead_resolve.add_argument("archive", type=Path)
    dead_resolve.add_argument("id", type=int)
    dead_resolve.add_argument("evidence_json", type=Path)
    dead_resolve.add_argument("--reason", required=True)
    incident = commands.add_parser(
        "incident-resolve", help="resolve a recorded incident without deleting history"
    )
    incident.add_argument("operations_ledger", type=Path)
    incident.add_argument("event_id")
    incident.add_argument("evidence_json", type=Path)
    incident.add_argument("--reason", required=True)
    recovery_check = commands.add_parser(
        "recovery-check", help="execute a SQLite backup/restore drill"
    )
    recovery_check.add_argument("operations_ledger", type=Path)
    recovery_check.add_argument("database", type=Path)
    backup = commands.add_parser(
        "evidence-backup", help="back up a ledger and its referenced run evidence"
    )
    backup.add_argument("ledger", type=Path)
    backup.add_argument("artifact_root", type=Path)
    backup.add_argument("output", type=Path)
    backup.add_argument(
        "--include", dest="additional_files", action="append", type=Path, default=[]
    )
    backup_verify = commands.add_parser(
        "evidence-backup-verify", help="verify every backup file and database"
    )
    backup_verify.add_argument("archive", type=Path)
    restore = commands.add_parser(
        "evidence-restore", help="restore offline without replacing existing data"
    )
    restore.add_argument("archive", type=Path)
    restore.add_argument("destination", type=Path)

    asset_bundle = commands.add_parser(
        "asset-bundle", help="bind images and forced photometry to a candidate evidence version"
    )
    asset_bundle.add_argument("candidates_json", type=Path)
    asset_bundle.add_argument("candidate_id")
    asset_bundle.add_argument("assets_json", type=Path)
    asset_bundle.add_argument("output_dir", type=Path)

    schema_register = commands.add_parser(
        "schema-register", help="freeze an operational input schema contract"
    )
    schema_register.add_argument("operations_ledger", type=Path)
    schema_register.add_argument("stream")
    schema_register.add_argument("fields_json", type=Path)

    schema_observe = commands.add_parser(
        "schema-observe", help="compare an observed input schema to its frozen contract"
    )
    schema_observe.add_argument("operations_ledger", type=Path)
    schema_observe.add_argument("stream")
    schema_observe.add_argument("fields_json", type=Path)

    drill = commands.add_parser("recovery-drill", help="append a recovery-drill result")
    drill.add_argument("operations_ledger", type=Path)
    drill.add_argument("name")
    drill.add_argument("evidence_json", type=Path)
    drill.add_argument("--passed", action="store_true")

    health = commands.add_parser("ops-health", help="summarize operational qualification events")
    health.add_argument("operations_ledger", type=Path)
    health.add_argument("--since", default=None)

    assertion_create = commands.add_parser(
        "principal-assertion-create",
        help="sign a short-lived principal assertion for a trusted local auth gateway",
    )
    assertion_create.add_argument("assertion_json", type=Path)
    assertion_create.add_argument("key_file", type=Path)
    assertion_create.add_argument("output", type=Path)

    assertion_verify = commands.add_parser(
        "principal-assertion-verify", help="verify a signed principal assertion"
    )
    assertion_verify.add_argument("assertion", type=Path)
    assertion_verify.add_argument("key_file", type=Path)
    assertion_verify.add_argument("--role", default=None)

    promotion = commands.add_parser(
        "promotion-check", help="evaluate every frozen scientific-promotion gate"
    )
    promotion.add_argument("preregistration", type=Path)
    promotion.add_argument("cohort_export", type=Path)
    promotion.add_argument("outcome_ledger", type=Path)
    promotion.add_argument("benchmark", type=Path)
    promotion.add_argument("injection", type=Path)
    promotion.add_argument("fixture_directory", type=Path)
    promotion.add_argument("broker_archive", type=Path)
    promotion.add_argument("asset_directory", type=Path)
    promotion.add_argument("operations_ledger", type=Path)
    promotion.add_argument("signoff_registry", type=Path)
    promotion.add_argument("--output", type=Path, default=None)

    promotion_sign = commands.add_parser(
        "promotion-sign", help="append an authenticated sign-off over promotion evidence"
    )
    promotion_sign.add_argument("preregistration", type=Path)
    promotion_sign.add_argument("promotion_report", type=Path)
    promotion_sign.add_argument("signoff_registry", type=Path)
    promotion_sign.add_argument("principal_assertion", type=Path)
    promotion_sign.add_argument("key_file", type=Path)
    promotion_sign.add_argument("--area", required=True)
    promotion_sign.add_argument("--verdict", choices=("approve", "reject"), required=True)
    promotion_sign.add_argument("--rationale", required=True)
    return parser


def _json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _render_json(value: Any) -> str:
    return json.dumps(_json_value(value), indent=2, sort_keys=True, allow_nan=False) + "\n"


def _atomic_text(path: Path, content: str) -> None:
    destination = path.expanduser().resolve()
    atomic_write_text(destination, content)


def _unlink_if_same_file(path: Path, staged_path: Path) -> bool:
    """Remove a publication only when it is our staged file's hard link."""

    try:
        if path.is_file() and staged_path.is_file() and os.path.samefile(path, staged_path):
            path.unlink()
            return True
    except OSError:
        # Preserve the original publication error.  A later invocation still
        # fails closed because existing partial outputs are never overwritten.
        pass
    return False


def _cleanup_published_link(path: Path, staged_path: Path) -> None:
    """Unlink our publication and durably record that rollback when possible."""

    if not _unlink_if_same_file(path, staged_path):
        return
    with contextlib.suppress(OSError):
        fsync_directory(path.parent)


def _publish_broker_snapshot(
    destination: Path,
    photometry_bytes: bytes,
    sidecar_bytes: bytes,
    *,
    after_publish: Callable[[Path, Path], None] | None = None,
) -> tuple[Path, Path]:
    """Publish a CSV/sidecar pair with the CSV acting as the commit point.

    Both complete files are staged on the destination filesystem.  Atomic
    hard-link creation publishes the sidecar first and the CSV last, so the
    user-facing CSV path is never visible without its complete provenance.
    Hard links also provide no-clobber semantics under concurrent writers.
    """

    destination = destination.expanduser().resolve()
    sidecar = destination.with_suffix(destination.suffix + ".provenance.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or sidecar.exists():
        raise FileExistsError("broker output or provenance sidecar already exists")

    staging = destination.parent / (f".{destination.name}.{os.getpid()}.{uuid4().hex}.broker.tmp")
    staging.mkdir(mode=0o700)
    staged_photometry = staging / "photometry.csv"
    staged_sidecar = staging / "provenance.json"
    try:
        for path, content in (
            (staged_photometry, photometry_bytes),
            (staged_sidecar, sidecar_bytes),
        ):
            with path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

        # Provenance becomes visible first.  The CSV path is the transaction's
        # commit point and therefore cannot be observed without its sidecar.
        os.link(staged_sidecar, sidecar)
        fsync_directory(destination.parent)
        os.link(staged_photometry, destination)
        fsync_directory(destination.parent)
        if after_publish is not None:
            after_publish(destination, sidecar)
    except (Exception, KeyboardInterrupt):
        # Same-inode checks also cover an interrupt delivered immediately after
        # a successful link without risking a concurrent writer's artifacts.
        _cleanup_published_link(destination, staged_photometry)
        _cleanup_published_link(sidecar, staged_sidecar)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return destination, sidecar


def _emit_json(value: Any, output: Path | None = None) -> None:
    content = _render_json(value)
    if output is None:
        print(content, end="")
    else:
        _atomic_text(output, content)
        print(output.expanduser().resolve())


def _emit_new_json(value: Any, output: Path) -> None:
    destination = output.expanduser().resolve()
    content = _render_json(value).encode("utf-8")
    atomic_create_binary(destination, lambda handle: handle.write(content))
    print(destination)


def _load_json_mapping(path: Path, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {description} {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"{description} must contain a JSON object")
    return dict(payload)


def _doctor(config_path: Path | None, *, strict: bool, as_json: bool) -> int:
    checks: list[dict[str, str]] = [
        {
            "name": "python",
            "status": "ok",
            "detail": f"{platform.python_version()} ({sys.executable})",
        }
    ]
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        checks.append({"name": "config", "status": "error", "detail": str(exc)})
    else:
        checks.append({"name": "config", "status": "ok", "detail": str(config.source_path)})
        root = config.storage.root
        parent = root
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        writable = parent.is_dir() and os.access(parent, os.W_OK)
        checks.append(
            {
                "name": "storage",
                "status": "ok" if writable else "warning",
                "detail": f"root={root}; nearest parent={parent}",
            }
        )
    for package in _SCIENTIFIC_PACKAGES:
        available = importlib.util.find_spec(package) is not None
        checks.append(
            {
                "name": f"dependency:{package}",
                "status": "ok" if available else "warning",
                "detail": "available" if available else "not installed",
            }
        )
    has_error = any(item["status"] == "error" for item in checks)
    has_warning = any(item["status"] == "warning" for item in checks)
    exit_code = 1 if has_error or (strict and has_warning) else 0
    if as_json:
        print(_render_json({"ok": exit_code == 0, "checks": checks}), end="")
    else:
        print("SIDEREA doctor")
        for item in checks:
            print(f"[{item['status'].upper():7}] {item['name']}: {item['detail']}")
    return exit_code


def _column_map(values: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        logical, separator, physical = value.partition("=")
        logical, physical = logical.strip(), physical.strip()
        if not separator or not logical or not physical:
            raise ValueError(f"invalid --column {value!r}; expected LOGICAL=PHYSICAL")
        if logical in result:
            raise ValueError(f"duplicate --column mapping for {logical!r}")
        result[logical] = physical
    return result


def _load_verification_files(
    paths: Sequence[Path],
) -> tuple[
    dict[str, tuple[Any, ...]],
    dict[str, bool],
    dict[str, dict[str, tuple[str, ...]]],
]:
    from siderea.evidence_context import canonical_verification_context
    from siderea.provenance import CheckProvenance, CheckStatus

    checks: dict[str, tuple[CheckProvenance, ...]] = {}
    manual: dict[str, bool] = {}
    contexts: dict[str, dict[str, tuple[str, ...]]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"verification file must contain a JSON object: {path}")
        if payload.get("schema") != "siderea.verification.v1":
            raise ValueError(f"verification file schema must be 'siderea.verification.v1': {path}")
        if "candidate_id" not in payload:
            raise ValueError(f"verification file lacks candidate_id: {path}")
        raw_candidate_id = payload["candidate_id"]
        if not isinstance(raw_candidate_id, str) or not raw_candidate_id.strip():
            raise ValueError(f"verification file has an invalid candidate_id: {path}")
        candidate_id = raw_candidate_id.strip()
        if candidate_id in checks:
            raise ValueError(f"duplicate verification evidence for {candidate_id}")
        raw_checks = payload.get("checks")
        if not isinstance(raw_checks, list) or any(
            not isinstance(item, Mapping) for item in raw_checks
        ):
            raise ValueError(f"verification file lacks a checks array: {path}")
        if "manual_review_required" not in payload or not isinstance(
            payload["manual_review_required"], bool
        ):
            raise ValueError(
                f"verification file needs a boolean manual_review_required field: {path}"
            )
        manual[candidate_id] = payload["manual_review_required"]
        parsed_checks = tuple(CheckProvenance.from_dict(item) for item in raw_checks)
        if "context" not in payload:
            raise ValueError(f"verification file lacks context evidence: {path}")
        context = canonical_verification_context(
            payload["context"],
            manual_review_required=manual[candidate_id],
        )
        if manual[candidate_id]:
            simbad = tuple(check for check in parsed_checks if check.service == "simbad")
            if len(simbad) != 1 or simbad[0].status is not CheckStatus.CLEAR:
                raise ValueError(
                    f"verification file manual review lacks one relevant clear SIMBAD check: {path}"
                )
        checks[candidate_id] = parsed_checks
        contexts[candidate_id] = context
    return checks, manual, contexts


def _command_analyze(args: argparse.Namespace, config: SIDEREAConfig) -> int:
    from siderea.pipeline import analyze_csv

    checks, manual, contexts = _load_verification_files(args.checks_json)
    result = analyze_csv(
        args.input,
        config,
        column_map=_column_map(args.column) or None,
        coordinate_tolerance_arcsec=args.coordinate_tolerance_arcsec,
        output_dir=args.output_dir,
        ledger_path=args.ledger,
        checks_by_candidate=checks,
        manual_review_by_candidate=manual,
        context_by_candidate=contexts,
        run_id=args.run_id,
    )
    _emit_json(result)
    return 0


def _command_broker_fetch(args: argparse.Namespace, config: SIDEREAConfig) -> int:
    from siderea.ingest import AlerceAdapter, BrokerQuery
    from siderea.ingest.snapshot import (
        BROKER_SNAPSHOT_ID_COLUMN,
        BROKER_SNAPSHOT_SCHEMA,
        broker_snapshot_id,
    )

    destination = args.output.expanduser().resolve()
    sidecar = destination.with_suffix(destination.suffix + ".provenance.json")
    if destination.exists() or sidecar.exists():
        raise FileExistsError("broker output or provenance sidecar already exists")
    current_mjd = datetime.now(UTC).timestamp() / 86_400.0 + 40_587.0
    requested_classes = (
        tuple(args.broker_classes)
        if args.broker_classes is not None
        else (("SN",) if args.survey == "lsst" else config.hunt.broker_classes)
    )
    query = BrokerQuery(
        classes=requested_classes,
        max_objects=config.hunt.object_limit,
        discovered_after_mjd=current_mjd - config.hunt.discovered_within_days,
        min_detections=config.hunt.min_detections,
    )
    selected_broker = args.broker or config.hunt.broker
    if selected_broker != "alerce":  # pragma: no cover - configuration constrains this.
        raise ValueError(f"unsupported broker: {selected_broker}")
    batch = AlerceAdapter(
        classifier=args.classifier,
        classifier_version=args.classifier_version,
        survey=args.survey,
        timeout_seconds=config.network.timeout_seconds,
        user_agent=config.network.user_agent,
        max_retries=config.network.max_retries,
        backoff_seconds=config.network.backoff_seconds,
    ).fetch(query)
    snapshot_id = broker_snapshot_id(
        source=batch.source,
        retrieved_at=batch.retrieved_at,
        provenance=batch.provenance,
        warnings=batch.warnings,
    )
    photometry = batch.to_frame()
    if BROKER_SNAPSHOT_ID_COLUMN in photometry.columns:
        raise ValueError(f"broker output uses reserved column {BROKER_SNAPSHOT_ID_COLUMN!r}")
    photometry[BROKER_SNAPSHOT_ID_COLUMN] = snapshot_id
    photometry_bytes = photometry.to_csv(index=False, lineterminator="\n").encode("utf-8")
    sidecar_bytes = _render_json(
        {
            "schema": BROKER_SNAPSHOT_SCHEMA,
            "snapshot_id": snapshot_id,
            "source": batch.source,
            "retrieved_at": batch.retrieved_at,
            "photometry_sha256": sha256(photometry_bytes).hexdigest(),
            "provenance": batch.provenance,
            "warnings": batch.warnings,
        }
    ).encode("utf-8")
    _publish_broker_snapshot(
        destination,
        photometry_bytes,
        sidecar_bytes,
        after_publish=lambda photometry_path, provenance_path: _emit_json(
            {"photometry": photometry_path, "provenance": provenance_path}
        ),
    )
    return 0


def _tns_client(config: SIDEREAConfig, *, disabled: bool) -> Any | None:
    if disabled:
        return None
    from siderea.clients.base import ResilientExecutor
    from siderea.clients.tns import TNSClient, TNSCredentials

    values = {
        "api_key": os.environ.get("TNS_API_KEY", ""),
        "bot_id": os.environ.get("TNS_BOT_ID", ""),
        "bot_name": os.environ.get("TNS_BOT_NAME", ""),
    }
    present = [bool(value) for value in values.values()]
    if any(present) and not all(present):
        raise ValueError("set all of TNS_API_KEY, TNS_BOT_ID, and TNS_BOT_NAME or none")
    if not all(present):
        return None
    executor = ResilientExecutor(
        attempts=config.network.max_retries + 1,
        base_delay_seconds=config.network.backoff_seconds,
    )
    return TNSClient(
        TNSCredentials(**values),
        timeout_seconds=config.network.timeout_seconds,
        executor=executor,
    )


def _command_verify(args: argparse.Namespace, config: SIDEREAConfig) -> int:
    from siderea.clients.base import ResilientExecutor
    from siderea.clients.catalogs import SimbadClient, SkyBotClient, VSXClient
    from siderea.validation import VerificationSuite

    executor = ResilientExecutor(
        attempts=config.network.max_retries + 1,
        base_delay_seconds=config.network.backoff_seconds,
    )
    enabled = not args.disable_network
    suite = VerificationSuite(
        skybot=SkyBotClient(
            executor,
            enabled=enabled,
            timeout_seconds=config.network.timeout_seconds,
            user_agent=config.network.user_agent,
        ),
        simbad=SimbadClient(
            executor,
            enabled=enabled,
            timeout_seconds=config.network.timeout_seconds,
            user_agent=config.network.user_agent,
        ),
        vsx=VSXClient(
            executor,
            enabled=enabled,
            timeout_seconds=config.network.timeout_seconds,
            user_agent=config.network.user_agent,
        ),
        tns=_tns_client(config, disabled=args.disable_network),
        evidence_ttl_hours=config.validation.evidence_ttl_hours,
    )
    result = suite.verify(
        candidate_id=args.candidate_id,
        ra=args.ra,
        dec=args.dec,
        peak_mjd=args.peak_mjd,
        reference_mjds=args.skybot_mjd,
        mandatory_services=config.validation.required_checks,
        quality_passed=args.quality_passed,
        skybot_radius_arcsec=config.validation.skybot_radius_arcsec,
        tns_radius_arcsec=config.validation.tns_radius_arcsec,
        catalog_radius_arcsec=config.validation.catalog_radius_arcsec,
    )
    payload = {
        "schema": "siderea.verification.v1",
        "candidate_id": args.candidate_id,
        "manual_review_required": result.manual_review_required,
        "context": result.context,
        "checks": [check.to_dict() for check in result.checks],
        "gate": {
            "decision": result.gate.decision.value,
            "reportable": result.gate.reportable,
            "reasons": result.gate.reasons,
            "missing_services": result.gate.missing_services,
            "matched_services": result.gate.matched_services,
        },
    }
    _emit_json(payload, args.output)
    return 0 if result.gate.reportable else 3


def _queue_policy(args: argparse.Namespace, config: SIDEREAConfig) -> tuple[int, int, str | None]:
    audit_slots = args.audit_slots if args.audit_slots is not None else config.ranking.audit_slots
    audit_seed = args.audit_seed
    if audit_slots > 0 and not (audit_seed or "").strip():
        audit_seed = secrets.token_hex(16)
    anomaly_slots = (
        args.anomaly_slots if args.anomaly_slots is not None else config.ranking.anomaly_slots
    )
    return anomaly_slots, audit_slots, audit_seed


def _command_queue(args: argparse.Namespace, config: SIDEREAConfig) -> int:
    from siderea.review import queue_from_csv

    anomaly_slots, audit_slots, audit_seed = _queue_policy(args, config)
    queue = queue_from_csv(
        args.input,
        budget=args.budget if args.budget is not None else config.review.nightly_budget,
        anomaly_slots=anomaly_slots,
        anomaly_threshold=args.anomaly_threshold,
        audit_slots=audit_slots,
        audit_seed=audit_seed,
        eligibility_policy=args.eligibility_policy,
    )
    _emit_json(queue, args.output)
    return 0


def _command_review_set(args: argparse.Namespace, config: SIDEREAConfig) -> int:
    from siderea.review import assemble_review_set

    anomaly_slots, audit_slots, audit_seed = _queue_policy(args, config)
    result = assemble_review_set(
        args.ranking_csv,
        args.candidates_json,
        args.output_dir,
        budget=args.budget if args.budget is not None else config.review.nightly_budget,
        anomaly_slots=anomaly_slots,
        anomaly_threshold=args.anomaly_threshold,
        audit_slots=audit_slots,
        audit_seed=audit_seed,
        eligibility_policy=args.eligibility_policy,
    )
    _emit_json(result)
    return 0


def _load_candidate(path: Path, candidate_id: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("candidates") if isinstance(payload, Mapping) else None
    if not isinstance(records, list):
        raise ValueError("candidates JSON does not contain a candidates array")
    if any(not isinstance(item, Mapping) for item in records):
        raise ValueError("candidates JSON contains a non-object candidate record")
    matches = [item for item in records if str(item.get("candidate_id")) == candidate_id]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one candidate {candidate_id!r}; found {len(matches)}")
    return dict(matches[0])


def _command_dossier(args: argparse.Namespace) -> int:
    from siderea.review import write_candidate_dossier

    record = _load_candidate(args.candidates_json, args.candidate_id)
    path = write_candidate_dossier(
        args.output_dir,
        candidate=record,
        features=dict(record.get("features", {})),
        checks=list(record.get("external_checks", [])),
    )
    print(path.resolve())
    return 0


def _ledger(config: SIDEREAConfig, path: Path | None) -> Any:
    from siderea.ledger import OutcomeLedger

    return OutcomeLedger(
        path.expanduser().resolve() if path else config.storage.root / "outcomes.sqlite"
    )


def _command_review_add(args: argparse.Namespace, config: SIDEREAConfig) -> int:
    from siderea.identity import verify_principal_assertion

    ledger = _ledger(config, args.ledger)
    if ledger.candidate(args.candidate_id) is None:
        raise ValueError(f"unknown candidate in ledger: {args.candidate_id}")
    principal = None
    reviewer = args.reviewer
    if args.principal_assertion is not None:
        if args.principal_key is None:
            raise ValueError("--principal-key is required with --principal-assertion")
        principal = verify_principal_assertion(
            args.principal_assertion,
            verification_key=args.principal_key.read_bytes(),
            required_role=args.role,
        )
        reviewer = principal.principal_id
    elif args.principal_key is not None:
        raise ValueError("--principal-key is only valid with --principal-assertion")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("reviewer identity is required")
    record = ledger.add_review(
        args.candidate_id,
        reviewer=reviewer,
        role=args.role,
        verdict=args.verdict,
        reason=args.reason,
        candidate_version=args.candidate_version,
        principal=principal,
    )
    _emit_json(record)
    return 0


def _command_adjudication_add(args: argparse.Namespace, config: SIDEREAConfig) -> int:
    from siderea.identity import verify_principal_assertion

    if (args.principal_assertion is None) != (args.principal_key is None):
        raise ValueError("--principal-assertion and --principal-key must be supplied together")
    principal = None
    if args.principal_assertion is not None:
        principal = verify_principal_assertion(
            args.principal_assertion,
            verification_key=args.principal_key.read_bytes(),
            required_role="adjudicator",
        )
    actor = principal.principal_id if principal is not None else args.adjudicator
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("adjudicator identity is required")
    record = _ledger(config, args.ledger).add_adjudication(
        args.candidate_id,
        adjudicator=actor,
        verdict=args.verdict,
        reason=args.reason,
        candidate_version=args.candidate_version,
        principal=principal,
    )
    _emit_json(record)
    return 0


def _command_review_serve(args: argparse.Namespace, config: SIDEREAConfig) -> int:
    from siderea.identity import verify_principal_assertion
    from siderea.review import serve_review

    if (args.principal_assertion is None) != (args.principal_key is None):
        raise ValueError("--principal-assertion and --principal-key must be supplied together")
    loader = None
    if args.principal_assertion is not None:

        def load_principal() -> Any:
            return verify_principal_assertion(
                args.principal_assertion, verification_key=args.principal_key.read_bytes()
            )

        load_principal()
        loader = load_principal
    if config.review.require_authenticated and loader is None:
        raise ValueError("authenticated review policy requires a signed principal session")
    serve_review(
        _ledger(config, args.ledger), host=args.host, port=args.port, principal_loader=loader
    )
    return 0


def _command_outcome_add(args: argparse.Namespace, config: SIDEREAConfig) -> int:
    evidence: Mapping[str, Any] = {}
    if args.evidence_json is not None:
        loaded = json.loads(args.evidence_json.read_text(encoding="utf-8"))
        if not isinstance(loaded, Mapping):
            raise ValueError("outcome evidence JSON must be an object")
        evidence = loaded
    ledger = _ledger(config, args.ledger)
    if ledger.candidate(args.candidate_id) is None:
        raise ValueError(f"unknown candidate in ledger: {args.candidate_id}")
    record = ledger.record_outcome(
        args.candidate_id,
        outcome=args.outcome,
        designation=args.designation,
        evidence=evidence,
        candidate_version=args.candidate_version,
        taxonomy_version=args.taxonomy_version,
    )
    _emit_json(record)
    return 0


def _command_outcome_summary(args: argparse.Namespace, config: SIDEREAConfig) -> int:
    from siderea.review.metrics import outcome_summary

    _emit_json(outcome_summary(_ledger(config, args.ledger)))
    return 0


def _command_preflight(args: argparse.Namespace, config: SIDEREAConfig) -> int:
    """Evaluate the stored, immutable evidence package without drafting a report."""

    from siderea.provenance import CheckProvenance
    from siderea.reporting import reporting_preflight

    ledger = _ledger(config, args.ledger)
    candidate = ledger.candidate(args.candidate_id)
    if candidate is None:
        raise ValueError(f"unknown candidate in ledger: {args.candidate_id}")
    payload = candidate.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("candidate ledger payload must be an object")
    quality = payload.get("quality")
    if not isinstance(quality, Mapping) or not isinstance(quality.get("passed"), bool):
        raise ValueError("candidate ledger payload has invalid quality evidence")
    manual_review_required = payload.get("manual_review_required")
    if not isinstance(manual_review_required, bool):
        raise ValueError("candidate ledger payload has invalid manual-review evidence")
    raw_checks = payload.get("external_checks")
    if not isinstance(raw_checks, list) or any(
        not isinstance(item, Mapping) for item in raw_checks
    ):
        raise ValueError("candidate ledger payload has invalid external-check evidence")
    checks = tuple(CheckProvenance.from_dict(item) for item in raw_checks)
    result = reporting_preflight(
        args.candidate_id,
        checks=checks,
        quality_passed=quality["passed"],
        manual_review_required=manual_review_required,
        ledger=ledger,
        candidate_version=args.candidate_version,
    )
    _emit_json(
        {
            "candidate_id": args.candidate_id,
            "candidate_version": args.candidate_version,
            "ready": result.ready,
            "reasons": result.reasons,
        }
    )
    return 0 if result.ready else 3


def _command_baseline_train(args: argparse.Namespace) -> int:
    import pandas as pd

    from siderea.ml.baseline import BaselineConfig, fit_baseline, save_baseline_bundle

    frame = pd.read_csv(args.input)
    requested = [args.label, args.time, *args.features]
    if args.entity:
        requested.append(args.entity)
    missing = sorted(set(requested) - set(frame.columns))
    if missing:
        raise ValueError(f"baseline input is missing columns: {missing}")
    if len(set(args.features)) != len(args.features):
        raise ValueError("baseline feature names must be unique")
    overlap = {args.label, args.time, args.entity} & set(args.features)
    if overlap:
        raise ValueError(f"label/time/entity columns cannot be features: {sorted(overlap)}")
    model = fit_baseline(
        frame[args.features].to_numpy(dtype=float),
        frame[args.label].to_numpy(),
        frame[args.time].to_numpy(dtype=float),
        feature_names=args.features,
        entity_ids=frame[args.entity].astype(str).to_numpy() if args.entity else None,
        unique_entities_asserted=args.assert_unique_entities,
        config=BaselineConfig(
            train_fraction=args.train_fraction,
            calibration_fraction=args.calibration_fraction,
            calibration=args.calibration,
            evaluation_review_budget=args.review_budget,
        ),
    )
    bundle = save_baseline_bundle(args.output, model)
    _emit_json({"bundle": bundle, "metadata": model.metadata})
    return 0


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, Mapping):
                raise ValueError(f"JSONL record at {path}:{line_number} is not an object")
            records.append(dict(value))
    if not records:
        raise ValueError(f"JSONL dataset is empty: {path}")
    return records


def _object_ids(records: Sequence[Mapping[str, Any]], source: Path) -> set[str]:
    identifiers: set[str] = set()
    for item in records:
        value = item.get("object_id")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"every JEPA record needs a non-empty string object_id: {source}")
        identifier = value.strip().casefold()
        if identifier in identifiers:
            raise ValueError(f"duplicate JEPA object_id {identifier!r} in {source}")
        identifiers.add(identifier)
    return identifiers


def _jepa_group_ids(records: Sequence[Mapping[str, Any]], source: Path) -> set[str]:
    groups: set[str] = set()
    for item in records:
        raw = item.get("entity_id", item.get("group_id", item.get("object_id")))
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"JEPA entity/group IDs must be non-empty strings: {source}")
        groups.add(raw.strip().casefold())
    return groups


def _jepa_time_extent(records: Sequence[Mapping[str, Any]], source: Path) -> tuple[float, float]:
    values: list[float] = []
    for item in records:
        raw_times = item.get("times")
        if isinstance(raw_times, (str, bytes)) or not isinstance(raw_times, Sequence):
            raise ValueError(f"every JEPA record needs a times array: {source}")
        for raw in raw_times:
            if isinstance(raw, bool):
                raise ValueError(f"JEPA times must be finite numbers: {source}")
            try:
                value = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"JEPA times must be finite numbers: {source}") from exc
            if not math.isfinite(value):
                raise ValueError(f"JEPA times must be finite numbers: {source}")
            values.append(value)
    if not values:
        raise ValueError(f"JEPA dataset has no observation times: {source}")
    return min(values), max(values)


def _jepa_prediction_cutoffs(
    records: Sequence[Mapping[str, Any]],
    source: Path,
    *,
    require_uniform: bool = False,
) -> tuple[float, float]:
    cutoffs: list[float] = []
    entities: set[str] = set()
    for item in records:
        entity = item.get("entity_id")
        if not isinstance(entity, str) or not entity.strip():
            raise ValueError(f"every strict JEPA record needs a non-empty entity_id: {source}")
        canonical = " ".join(entity.casefold().split())
        if canonical in entities:
            raise ValueError(f"duplicate strict JEPA entity_id {canonical!r} in {source}")
        entities.add(canonical)
        raw_cutoff = item.get("prediction_cutoff_mjd")
        if isinstance(raw_cutoff, bool) or not isinstance(raw_cutoff, (int, float)):
            raise ValueError(f"JEPA prediction_cutoff_mjd must be finite: {source}")
        cutoff = float(raw_cutoff)
        if not math.isfinite(cutoff):
            raise ValueError(f"JEPA prediction_cutoff_mjd must be finite: {source}")
        raw_times = item.get("times")
        if isinstance(raw_times, (str, bytes)) or not isinstance(raw_times, Sequence):
            raise ValueError(f"every JEPA record needs a times array: {source}")
        try:
            times = [float(value) for value in raw_times]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"JEPA times must be finite numbers: {source}") from exc
        if not times or not all(math.isfinite(value) for value in times):
            raise ValueError(f"JEPA times must be finite numbers: {source}")
        if max(times) > cutoff:
            raise ValueError(
                f"JEPA record {entity!r} contains an observation after its prediction cutoff"
            )
        cutoffs.append(cutoff)
    if require_uniform and len(set(cutoffs)) != 1:
        raise ValueError("JEPA embedding batch requires one shared prediction_cutoff_mjd")
    return min(cutoffs), max(cutoffs)


def _command_jepa_train(args: argparse.Namespace, config: SIDEREAConfig) -> int:
    from siderea.ml import (
        DEFAULT_BAND_TO_ID,
        TOKEN_FIELDS,
        TOKENIZATION_CONTRACT_VERSION,
        TSJEPA,
        LightCurveDataset,
        TrainingConfig,
        evaluate_jepa,
        save_checkpoint,
        train_jepa,
    )
    from siderea.provenance import digest_file, digest_value

    if not config.jepa.enabled:
        raise ValueError("jepa.enabled must be true in the selected research configuration")

    destination = args.output.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"JEPA output already exists: {destination}")
    train_records = _load_jsonl(args.train_jsonl)
    validation_records = _load_jsonl(args.validation_jsonl)
    train_ids = _object_ids(train_records, args.train_jsonl)
    validation_ids = _object_ids(validation_records, args.validation_jsonl)
    overlap = train_ids & validation_ids
    if overlap:
        examples = ", ".join(sorted(overlap)[:5])
        raise ValueError(f"JEPA train/validation object IDs overlap: {examples}")
    group_overlap = _jepa_group_ids(train_records, args.train_jsonl) & _jepa_group_ids(
        validation_records, args.validation_jsonl
    )
    if group_overlap:
        examples = ", ".join(sorted(group_overlap)[:5])
        raise ValueError(f"JEPA train/validation entity groups overlap: {examples}")
    train_extent = _jepa_time_extent(train_records, args.train_jsonl)
    validation_extent = _jepa_time_extent(validation_records, args.validation_jsonl)
    train_cutoffs = validation_cutoffs = None
    if args.require_prediction_cutoffs:
        train_cutoffs = _jepa_prediction_cutoffs(train_records, args.train_jsonl)
        validation_cutoffs = _jepa_prediction_cutoffs(validation_records, args.validation_jsonl)
    if args.split_policy == "chronological" and not train_extent[1] < validation_extent[0]:
        raise ValueError(
            "chronological JEPA split requires every training observation to precede "
            "every validation observation; use --split-policy predefined only for an "
            "externally audited split"
        )
    train_data = LightCurveDataset(train_records)
    validation_data = LightCurveDataset(validation_records)
    train_token_metadata = train_data[0].metadata
    validation_token_metadata = validation_data[0].metadata
    train_contract = train_token_metadata.get("token_contract")
    validation_contract = validation_token_metadata.get("token_contract")
    train_contract_digest = train_token_metadata.get("token_contract_sha256")
    validation_contract_digest = validation_token_metadata.get("token_contract_sha256")
    if (
        not isinstance(train_contract, Mapping)
        or not isinstance(validation_contract, Mapping)
        or not isinstance(train_contract_digest, str)
        or not isinstance(validation_contract_digest, str)
        or digest_value(train_contract) != train_contract_digest
        or digest_value(validation_contract) != validation_contract_digest
    ):
        raise ValueError("JEPA train/validation token-contract metadata is incomplete")
    if not hmac.compare_digest(train_contract_digest, validation_contract_digest):
        raise ValueError("JEPA train/validation token contracts differ")
    # Model construction happens before train_jepa's data-loader seed, so seed
    # initialization explicitly as part of the reproducible CLI experiment.
    import torch

    deterministic = not args.allow_nondeterministic
    torch.use_deterministic_algorithms(deterministic)
    torch.manual_seed(config.jepa.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.jepa.seed)
    model = TSJEPA(
        d_model=config.jepa.embedding_dim,
        num_bands=max(DEFAULT_BAND_TO_ID.values()) + 1,
        n_heads=config.jepa.attention_heads,
        num_layers=config.jepa.encoder_layers,
        ema_momentum=config.jepa.ema_momentum,
    )
    selected_batch_size = args.batch_size if args.batch_size is not None else config.jepa.batch_size
    training_config = TrainingConfig(
        epochs=args.epochs,
        batch_size=selected_batch_size,
        learning_rate=config.jepa.learning_rate,
        target_fraction=config.jepa.mask_fraction,
        mask_scale_jitter=config.jepa.mask_scale_jitter,
        ema_momentum=config.jepa.ema_momentum,
        ema_final_momentum=config.jepa.ema_final_momentum,
        seed=config.jepa.seed,
        device=args.device,
        deterministic_algorithms=deterministic,
    )
    history = train_jepa(model, train_data, training_config)
    validation = evaluate_jepa(
        model,
        validation_data,
        batch_size=selected_batch_size,
        target_fraction=config.jepa.mask_fraction,
        mask_scale_jitter=config.jepa.mask_scale_jitter,
        seed=config.jepa.seed + 1,
        mask_repeats=args.evaluation_masks,
        device=args.device,
    )
    trained_contract_digest = history.get("token_contract_sha256")
    evaluated_contract_digest = validation.get("token_contract_sha256")
    if (
        not isinstance(trained_contract_digest, str)
        or not isinstance(evaluated_contract_digest, str)
        or not hmac.compare_digest(trained_contract_digest, train_contract_digest)
        or not hmac.compare_digest(evaluated_contract_digest, train_contract_digest)
    ):
        raise ValueError("JEPA runtime token contract differs from the declared dataset contract")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    temporary.mkdir()
    try:
        temporary_checkpoint = temporary / "checkpoint.pt"
        metadata = save_checkpoint(
            temporary_checkpoint,
            model,
            training_state=history,
            metadata={
                "mode": "shadow_research",
                "train_dataset_sha256": digest_file(args.train_jsonl),
                "validation_dataset_sha256": digest_file(args.validation_jsonl),
                "split_policy": args.split_policy,
                "train_time_extent": train_extent,
                "validation_time_extent": validation_extent,
                "prediction_cutoffs_required": args.require_prediction_cutoffs,
                "train_prediction_cutoff_extent": train_cutoffs,
                "validation_prediction_cutoff_extent": validation_cutoffs,
                "entity_group_disjoint": True,
                "deterministic_algorithms": deterministic,
                "token_fields": list(TOKEN_FIELDS),
                "tokenization_contract_version": TOKENIZATION_CONTRACT_VERSION,
                "token_contract": dict(train_contract),
                "token_contract_sha256": train_contract_digest,
                "band_to_id": DEFAULT_BAND_TO_ID,
                "band_vocabulary_sha256": digest_value(DEFAULT_BAND_TO_ID),
                "normalization_scope": "full_curve_then_context_rebased_during_masking",
                "validation": validation,
            },
        )
        summary = {
            "schema": "siderea.jepa_training.v2",
            "checkpoint": destination / "checkpoint.pt",
            "checkpoint_sha256": digest_file(temporary_checkpoint),
            "training": history,
            "validation": validation,
            "metadata": metadata,
            "operational_status": "shadow_only; never a reporting gate",
        }
        _atomic_text(temporary / "training.json", _render_json(summary))
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    _emit_json(summary)
    return 0


def _command_jepa_embed(args: argparse.Namespace) -> int:
    from siderea.ml import LightCurveDataset, extract_embeddings, load_checkpoint
    from siderea.provenance import digest_file, digest_value
    from siderea.research.pilot import JEPA_EMBEDDINGS_SCHEMA

    records = _load_jsonl(args.input_jsonl)
    _object_ids(records, args.input_jsonl)
    cutoff_extent = _jepa_prediction_cutoffs(records, args.input_jsonl, require_uniform=True)
    model, checkpoint = load_checkpoint(args.checkpoint, map_location=args.device)
    extracted = extract_embeddings(
        model,
        LightCurveDataset(records),
        batch_size=args.batch_size,
        device=args.device,
    )
    checkpoint_digest = digest_file(args.checkpoint)
    source_root = Path(__file__).resolve().parent
    source_files = {
        name: digest_file(source_root / "ml" / name)
        for name in ("dataset.py", "evaluate.py", "jepa.py", "train.py")
    }
    source_files["cli.py"] = digest_file(Path(__file__))
    object_ids = extracted["object_ids"]
    if tuple(record["object_id"] for record in records) != tuple(object_ids):
        raise RuntimeError("JEPA embedding output object order differs from the input dataset")
    matrix = extracted["embeddings"]
    rows = [
        {
            "entity_id": record["entity_id"].strip(),
            "object_id": object_id,
            "prediction_cutoff_mjd": float(record["prediction_cutoff_mjd"]),
            "embedding": matrix[index].tolist(),
        }
        for index, (record, object_id) in enumerate(zip(records, object_ids, strict=True))
    ]
    output: dict[str, Any] = {
        "schema": JEPA_EMBEDDINGS_SCHEMA,
        "mode": "shadow_only",
        "qualifies_reportability": False,
        "checkpoint_sha256": checkpoint_digest,
        "dataset_snapshot_sha256": digest_file(args.input_jsonl),
        "token_contract_sha256": extracted["token_contract_sha256"],
        "code_identity_sha256": digest_value(source_files),
        "code_file_sha256": source_files,
        "prediction_cutoff_mjd": cutoff_extent[0],
        "checkpoint_metadata": checkpoint["metadata"],
        "diagnostics": extracted["diagnostics"],
        "rows": rows,
    }
    if args.reference_cohort is not None:
        from siderea.research.overnight import verify_reference_embeddings

        cohort = _load_json_mapping(args.reference_cohort, "JEPA reference cohort")
        verified_cohort = verify_reference_embeddings(cohort, output)
        output["embedding_role"] = "jepa_anomaly_reference"
        output["reference_cohort_result_digest"] = verified_cohort["result_digest"]
        output["reference_cohort_id"] = verified_cohort["cohort_id"]
        output["reference_cohort_manifest_sha256"] = digest_file(args.reference_cohort)
    else:
        output["embedding_role"] = "candidate_or_unbound_reference"
    output["result_digest"] = digest_value(output)
    _emit_new_json(output, args.output)
    return 0


def _command_jepa_reference_freeze(args: argparse.Namespace) -> int:
    from siderea.provenance import digest_file
    from siderea.research.overnight import freeze_reference_cohort

    output = freeze_reference_cohort(
        _load_jsonl(args.input_jsonl),
        dataset_sha256=digest_file(args.input_jsonl),
        cohort_id=args.cohort_id,
        selection_policy=args.selection_policy,
    )
    _emit_new_json(output, args.output)
    return 0


def _pilot_detection_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "t", "yes", "y", "detected", "detection", "1"}:
            return True
        if normalized in {"false", "f", "no", "n", "nondetection", "non-detection", "0"}:
            return False
    raise ValueError(f"unrecognized pilot detection value {value!r}")


def _command_pilot_prepare(args: argparse.Namespace) -> int:
    import io

    import pandas as pd

    from siderea.ml import LightCurveDataset
    from siderea.provenance import digest_file, digest_value, stable_json

    if not math.isfinite(args.prediction_cutoff_mjd):
        raise ValueError("prediction cutoff MJD must be finite")
    flux_unit = args.flux_unit.strip()
    calibration = args.calibration.strip()
    if not flux_unit or not calibration:
        raise ValueError("flux unit and calibration must be non-empty")
    input_bytes = args.input.read_bytes()
    identifier_columns = {"source_id": "string", "observation_id": "string"}
    if args.entity_column:
        identifier_columns[args.entity_column] = "string"
    frame = pd.read_csv(io.BytesIO(input_bytes), dtype=identifier_columns)
    required = {"source_id", "survey", "band", "mjd", "flux", "flux_error"}
    if args.entity_column:
        required.add(args.entity_column)
    if args.detection_column:
        required.add(args.detection_column)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"pilot input is missing columns: {missing}")
    if frame.empty:
        raise ValueError("pilot input cannot be empty")
    has_ra, has_dec = "ra_deg" in frame, "dec_deg" in frame
    if has_ra != has_dec:
        raise ValueError("pilot coordinates require both ra_deg and dec_deg")
    if args.require_pipeline_view and not (has_ra and has_dec):
        raise ValueError("--require-pipeline-view requires ra_deg and dec_deg")
    for column in ("mjd", "flux", "flux_error"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not frame[column].map(math.isfinite).all():
            raise ValueError(f"pilot {column} values must be finite")
    if (frame["flux_error"] <= 0).any():
        raise ValueError("pilot flux errors must be positive")
    if has_ra and has_dec:
        for column in ("ra_deg", "dec_deg"):
            frame[column] = pd.to_numeric(frame[column], errors="raise")
            if not frame[column].map(math.isfinite).all():
                raise ValueError(f"pilot {column} values must be finite")
        if not frame["ra_deg"].between(0.0, 360.0, inclusive="left").all():
            raise ValueError("pilot ra_deg values must be within [0, 360)")
        if not frame["dec_deg"].between(-90.0, 90.0).all():
            raise ValueError("pilot dec_deg values must be within [-90, 90]")
    if float(frame["mjd"].max()) > args.prediction_cutoff_mjd:
        raise ValueError("pilot input contains an observation after its prediction cutoff")

    source_ids = frame["source_id"].astype("string").str.strip()
    if source_ids.isna().any() or source_ids.eq("").any():
        raise ValueError("pilot source IDs must be present")
    if args.entity_column:
        entity_values = frame[args.entity_column].astype("string").str.strip()
        if entity_values.isna().any() or entity_values.eq("").any():
            raise ValueError("pilot physical entity IDs must be present")
    else:
        entity_values = source_ids
    frame["_source_id"] = source_ids
    frame["_entity_id"] = entity_values
    frame["_canonical_entity"] = [
        " ".join(str(value).casefold().split()) for value in entity_values
    ]
    if args.detection_column:
        detections = [_pilot_detection_value(value) for value in frame[args.detection_column]]
    else:
        detections = [True] * len(frame)
    frame["_detected"] = detections
    normalized_surveys = [" ".join(str(value).casefold().split()) for value in frame["survey"]]
    if any(not value for value in normalized_surveys) or len(set(normalized_surveys)) != 1:
        raise ValueError("pilot preparation requires exactly one non-empty survey per bundle")
    frame["survey"] = normalized_surveys

    identity_columns = ["_canonical_entity", "survey"]
    measurement_columns = [
        "_canonical_entity",
        "survey",
        "band",
        "mjd",
        "flux",
        "flux_error",
    ]
    if "observation_id" in frame:
        observation_ids = frame["observation_id"].astype("string").str.strip()
        missing_ids = observation_ids.isna() | observation_ids.fillna("").str.casefold().isin(
            {"", "nan", "none", "null"}
        )
        frame["observation_id"] = observation_ids.mask(missing_ids, pd.NA)
        if frame.loc[~missing_ids].duplicated(subset=[*identity_columns, "observation_id"]).any():
            raise ValueError("pilot input reuses an observation ID within a physical entity")
        if (frame.duplicated(subset=measurement_columns, keep=False) & missing_ids).any():
            raise ValueError("pilot input has duplicate measurements with ambiguous identity")
    elif frame.duplicated(subset=measurement_columns).any():
        raise ValueError("pilot input has duplicate measurements without observation identity")

    records: list[dict[str, Any]] = []
    detector_parts: list[Any] = []
    pipeline_parts: list[Any] = []
    for _, group in frame.groupby("_canonical_entity", sort=True):
        ordered = group.sort_values(["mjd", "survey", "band", "_source_id"], kind="stable")
        entity_names = list(dict.fromkeys(str(value).strip() for value in ordered["_entity_id"]))
        if len({" ".join(value.casefold().split()) for value in entity_names}) != 1:
            raise RuntimeError("canonical entity grouping became inconsistent")
        surveys = list(dict.fromkeys(str(value).strip() for value in ordered["survey"]))
        if len(surveys) != 1:
            raise ValueError(
                f"pilot entity {entity_names[0]!r} spans multiple surveys; prepare them separately"
            )
        aliases = list(dict.fromkeys(str(value).strip() for value in ordered["_source_id"]))
        record = {
            "object_id": entity_names[0],
            "entity_id": entity_names[0],
            "source_aliases": aliases,
            "prediction_cutoff_mjd": float(args.prediction_cutoff_mjd),
            "times": [float(value) for value in ordered["mjd"]],
            "values": [float(value) for value in ordered["flux"]],
            "errors": [float(value) for value in ordered["flux_error"]],
            "bands": [str(value).strip() for value in ordered["band"]],
            "detections": [bool(value) for value in ordered["_detected"]],
            "value_kind": "flux",
            "survey": surveys[0],
            "flux_unit": flux_unit,
            "calibration": calibration,
        }
        records.append(record)
        columns = ["survey", "band", "mjd", "flux", "flux_error"]
        if "observation_id" in ordered:
            columns.append("observation_id")
        detector = ordered[columns].copy()
        detector.insert(0, "source_id", entity_names[0])
        detector_parts.append(detector)
        if has_ra and has_dec:
            pipeline_columns = [
                "ra_deg",
                "dec_deg",
                "mjd",
                "band",
                "flux",
                "flux_error",
                "survey",
            ]
            if "observation_id" in ordered:
                pipeline_columns.append("observation_id")
            pipeline = ordered[pipeline_columns].copy()
            pipeline.insert(0, "source_id", entity_names[0])
            pipeline["is_detection"] = [bool(value) for value in ordered["_detected"]]
            pipeline_parts.append(pipeline)

    # Force complete tokenization before publishing either representation.
    dataset = LightCurveDataset(records, allow_unknown_bands=False)
    for index in range(len(dataset)):
        dataset[index]
    detector_frame = pd.concat(detector_parts, ignore_index=True)
    pipeline_frame = None if not pipeline_parts else pd.concat(pipeline_parts, ignore_index=True)
    destination = args.output.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"pilot output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    temporary.mkdir(mode=0o700)
    try:
        flux_path = temporary / "detector_flux.csv"
        jepa_path = temporary / "jepa.jsonl"
        pipeline_path = temporary / "pipeline_photometry.csv"
        flux_path.write_text(detector_frame.to_csv(index=False, lineterminator="\n"))
        jepa_path.write_text("".join(stable_json(record) + "\n" for record in records))
        if pipeline_frame is not None:
            pipeline_path.write_text(pipeline_frame.to_csv(index=False, lineterminator="\n"))
        manifest: dict[str, Any] = {
            "schema": "siderea.pilot_dataset.v2",
            "mode": "shadow_only",
            "qualifies_reportability": False,
            "prediction_cutoff_mjd": float(args.prediction_cutoff_mjd),
            "flux_unit": flux_unit,
            "calibration": calibration,
            "identity_policy": (
                f"column:{args.entity_column}"
                if args.entity_column
                else "caller_asserted_source_id_is_physical_entity"
            ),
            "detection_policy": (
                f"column:{args.detection_column}"
                if args.detection_column
                else "caller_asserted_all_rows_are_detections"
            ),
            "input_sha256": sha256(input_bytes).hexdigest(),
            "detector_flux_sha256": digest_file(flux_path),
            "jepa_dataset_sha256": digest_file(jepa_path),
            "pipeline_view": {
                "status": "available"
                if pipeline_frame is not None
                else "omitted_missing_coordinates",
                "path": "pipeline_photometry.csv" if pipeline_frame is not None else None,
                "sha256": digest_file(pipeline_path) if pipeline_frame is not None else None,
            },
            "preparation_code_sha256": digest_file(Path(__file__)),
            "entities": len(records),
            "observations": len(frame),
        }
        manifest["manifest_digest"] = digest_value(manifest)
        (temporary / "manifest.json").write_text(_render_json(manifest))
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    _emit_json({"output": destination, "manifest": manifest})
    return 0


def _command_shadow_assemble(args: argparse.Namespace) -> int:
    from siderea.provenance import digest_file
    from siderea.research.overnight import (
        verify_integration_manifests,
        verify_reference_embeddings,
    )
    from siderea.research.pilot import assemble_shadow_evidence

    supplied = (
        args.pipeline_candidates,
        args.pipeline_manifest,
        args.pilot_manifest,
        args.reference_cohort,
    )
    if any(value is not None for value in supplied) and not all(
        value is not None for value in supplied
    ):
        raise ValueError(
            "integrated assembly requires pipeline candidates, pipeline manifest, "
            "pilot manifest, and reference cohort together"
        )
    search = _load_json_mapping(args.transient_search, "transient search")
    candidate_embeddings = _load_json_mapping(args.candidate_embeddings, "candidate embeddings")
    reference_embeddings = _load_json_mapping(args.reference_embeddings, "reference embeddings")
    pipeline_candidates = (
        None
        if args.pipeline_candidates is None
        else _load_json_mapping(args.pipeline_candidates, "pipeline candidates")
    )
    manifest_binding = None
    reference_cohort_digest = None
    if args.pipeline_candidates is not None:
        manifest_binding = verify_integration_manifests(
            pilot_manifest_path=args.pilot_manifest,
            pipeline_manifest_path=args.pipeline_manifest,
            pipeline_candidates_path=args.pipeline_candidates,
            transient_search=search,
            candidate_embeddings=candidate_embeddings,
        )
        cohort = _load_json_mapping(args.reference_cohort, "reference cohort")
        verified_cohort = verify_reference_embeddings(cohort, reference_embeddings)
        reference_cohort_digest = verified_cohort["result_digest"]
        if reference_embeddings.get("reference_cohort_result_digest") != reference_cohort_digest:
            raise ValueError("reference embeddings are not bound to the supplied frozen cohort")
    output = assemble_shadow_evidence(
        search,
        candidate_embeddings,
        reference_embeddings,
        pipeline_candidates=pipeline_candidates,
        pipeline_candidates_sha256=(
            None if args.pipeline_candidates is None else digest_file(args.pipeline_candidates)
        ),
        manifest_binding=manifest_binding,
        reference_cohort_result_digest=reference_cohort_digest,
        random_state=args.random_state,
    )
    _emit_new_json(output, args.output)
    return 0


def _command_transient_shard(args: argparse.Namespace) -> int:
    import io

    import pandas as pd

    from siderea.research.overnight import shard_flux_table

    frame = pd.read_csv(
        io.BytesIO(args.input.read_bytes()),
        dtype={"source_id": "string", "observation_id": "string"},
    )
    result = shard_flux_table(frame, args.output, max_channels=args.max_channels)
    _emit_json({"output": args.output.expanduser().resolve(), "manifest": result})
    return 0


def _command_transient_merge(args: argparse.Namespace) -> int:
    from siderea.research.overnight import merge_transient_searches

    searches = [
        _load_json_mapping(path, f"transient shard {index}")
        for index, path in enumerate(args.inputs, start=1)
    ]
    _emit_new_json(merge_transient_searches(searches), args.output)
    return 0


def _command_shadow_rank(args: argparse.Namespace) -> int:
    from siderea.research.pilot import build_integrated_shadow_queue

    output = build_integrated_shadow_queue(
        _load_json_mapping(args.evidence, "shadow evidence"),
        budget=args.budget,
        detector_slots=args.detector_slots,
        jepa_slots=args.jepa_slots,
        audit_slots=args.audit_slots,
        jepa_threshold=args.jepa_threshold,
        audit_seed=args.audit_seed,
    )
    _emit_new_json(output, args.output)
    return 0


def _command_study_freeze(args: argparse.Namespace) -> int:
    from siderea.research import freeze_preregistration

    preregistration = freeze_preregistration(args.protocol_json, args.output)
    _emit_json(
        {
            "path": args.output.expanduser().resolve(),
            "study_id": preregistration.study_id,
            "protocol_digest": preregistration.protocol_digest,
            "frozen_at": preregistration.frozen_at,
        }
    )
    return 0


def _candidate_records(path: Path) -> list[dict[str, Any]]:
    payload = _load_json_mapping(path, "candidate evidence")
    if payload.get("schema") != "siderea.candidates.v1":
        raise ValueError("candidate evidence must use schema 'siderea.candidates.v1'")
    records = payload.get("candidates")
    if not isinstance(records, list) or any(not isinstance(item, Mapping) for item in records):
        raise ValueError("candidate evidence must contain an array of candidate objects")
    return [dict(item) for item in records]


def _command_cohort_enroll(args: argparse.Namespace) -> int:
    from siderea.provenance import digest_value
    from siderea.research import CohortRegistry, CohortSelection, load_preregistration

    preregistration = load_preregistration(args.preregistration)
    records = _candidate_records(args.candidates_json)
    selected_ids = {str(value).strip() for value in args.selected_id if str(value).strip()}
    selection_metadata: dict[str, Any] = {}
    selection_entries: dict[str, Any] = {}
    if args.review_set is not None:
        from siderea.review.assembly import verify_review_set

        if selected_ids or args.stratum != "main":
            raise ValueError("--review-set derives selected IDs and strata; omit manual overrides")
        manifest = verify_review_set(args.review_set)
        if manifest["candidates_sha256"] != sha256(args.candidates_json.read_bytes()).hexdigest():
            raise ValueError("review set is bound to a different candidates file")
        queue = manifest["queue"]
        policy = preregistration.protocol["selection"]
        if (
            queue["budget"] != policy["review_budget"]
            or queue["requested_audit_slots"] != policy["audit_slots"]
            or manifest["eligibility_policy"] != policy["eligibility_policy"]
        ):
            raise ValueError("review-set allocation differs from preregistered selection policy")
        selection_entries = {entry["candidate_id"]: entry for entry in queue["entries"]}
        selected_ids = set(selection_entries)
        selection_metadata = {
            "review_set_id": manifest["review_set_id"],
            "queue_digest": digest_value(queue),
            "audit_seed": queue["audit_seed"],
            "audit_population": queue["audit_population"],
            "audit_selection_probability": queue["audit_selection_probability"],
            "eligible_candidates": queue["eligible_candidates"],
            "excluded_candidates": queue["excluded_candidates"],
        }
    candidate_ids = {str(record.get("candidate_id", "")).strip() for record in records}
    unknown = sorted(selected_ids - candidate_ids)
    if unknown:
        raise ValueError(f"selected candidate IDs are absent from the evidence file: {unknown}")
    registry = CohortRegistry(args.registry)
    selections = [
        CohortSelection(
            record,
            selected=str(record.get("candidate_id", "")).strip() in selected_ids,
            selection_stratum=selection_entries.get(record["candidate_id"], {}).get(
                "selection_route", args.stratum
            ),
            selection_metadata={
                **selection_metadata,
                "entry": selection_entries.get(record["candidate_id"]),
            }
            if selection_metadata
            else {},
        )
        for record in records
    ]
    enrollments = registry.enroll_batch(preregistration, selections, enrolled_at=args.enrolled_at)
    _emit_json(
        {
            "study_id": preregistration.study_id,
            "protocol_digest": preregistration.protocol_digest,
            "enrolled": len(enrollments),
            "selected": sum(enrollment.selected for enrollment in enrollments),
            "registry": args.registry.expanduser().resolve(),
        }
    )
    return 0


def _command_cohort_export(args: argparse.Namespace) -> int:
    from siderea.ledger import OutcomeLedger
    from siderea.research import CohortRegistry, export_matured_cohort, load_preregistration

    payload = export_matured_cohort(
        load_preregistration(args.preregistration),
        CohortRegistry(args.registry),
        OutcomeLedger(args.ledger.expanduser().resolve()),
        args.output,
        as_of=args.as_of,
    )
    _emit_json(
        {
            "output": args.output.expanduser().resolve(),
            "cohort_digest": payload["cohort_digest"],
            "enrollment_count": payload["enrollment_count"],
            "missing_outcome_count": payload["missing_outcome_count"],
        }
    )
    return 0


def _command_benchmark_run(args: argparse.Namespace) -> int:
    import pandas as pd

    from siderea.research import load_preregistration, run_rolling_origin_benchmark

    preregistration = load_preregistration(args.preregistration)
    analysis = preregistration.protocol.get("analysis")
    selection = preregistration.protocol.get("selection")
    if not isinstance(analysis, Mapping) or not isinstance(selection, Mapping):
        raise ValueError("preregistration has invalid analysis or selection policy")
    comparison = str(analysis["comparison"])
    if comparison not in args.scores:
        raise ValueError("--scores must include the preregistered comparison score")
    payload = run_rolling_origin_benchmark(
        pd.read_csv(args.input),
        entity_column=args.entity,
        time_column=args.time,
        label_column=args.label,
        score_columns=args.scores,
        review_budget=int(selection["review_budget"]),
        minimum_history_blocks=args.minimum_history_blocks,
        bootstrap_repeats=int(analysis["bootstrap_repeats"]),
        confidence_level=float(analysis["confidence_level"]),
        seed=int(analysis["random_seed"]),
        time_block_days=args.time_block_days,
    )
    payload["study_id"] = preregistration.study_id
    payload["protocol_digest"] = preregistration.protocol_digest
    from siderea.provenance import digest_value

    payload.pop("result_digest", None)
    payload["result_digest"] = digest_value(payload)
    if args.cohort is not None:
        from siderea.research.qualification import bind_benchmark

        payload = bind_benchmark(
            payload, _load_json_mapping(args.cohort, "matured cohort"), preregistration
        )
    _emit_new_json(payload, args.output)
    return 0


def _command_transient_search(args: argparse.Namespace) -> int:
    import io

    import pandas as pd

    from siderea.provenance import digest_value, stable_json
    from siderea.research.transients import search_flux_table

    data = args.input.read_bytes()
    frame = pd.read_csv(io.BytesIO(data), dtype={"source_id": "string", "observation_id": "string"})
    if args.prediction_cutoff_mjd is not None:
        if not math.isfinite(args.prediction_cutoff_mjd):
            raise ValueError("prediction cutoff MJD must be finite")
        if "mjd" not in frame:
            raise ValueError("transient-search input requires an MJD column")
        observed_times = pd.to_numeric(frame["mjd"], errors="raise")
        if observed_times.empty or not observed_times.map(math.isfinite).all():
            raise ValueError("transient-search MJD values must be finite")
        if float(observed_times.max()) > args.prediction_cutoff_mjd:
            raise ValueError("transient search contains an observation after its prediction cutoff")
    result = search_flux_table(
        frame,
        widths=args.width_days or (1.0, 3.0, 10.0),
        center_count=args.centers,
        null_trials=args.null_trials,
        seed=args.seed,
        alpha=args.alpha,
        noise_timescale_days=args.noise_timescale_days,
        object_universe_size=args.survey_object_count,
        planned_looks=args.planned_looks,
        look_index=args.look_index,
        null_method=args.null_method,
        wild_block_size=args.wild_block_size,
    )
    result.pop("result_digest")
    result["input_sha256"] = sha256(data).hexdigest()
    if args.prediction_cutoff_mjd is not None:
        result["prediction_cutoff_mjd"] = args.prediction_cutoff_mjd
    result["result_digest"] = digest_value(result)
    encoded = (stable_json(result) + "\n").encode("utf-8")
    atomic_create_binary(args.output, lambda handle: handle.write(encoded))
    _emit_json(result)
    return 0


def _command_injection_run(args: argparse.Namespace) -> int:
    import pandas as pd

    from siderea.provenance import digest_value
    from siderea.research import load_preregistration, run_injection_recovery

    preregistration = load_preregistration(args.preregistration)
    analysis = preregistration.protocol.get("analysis")
    if not isinstance(analysis, Mapping):
        raise ValueError("preregistration has invalid analysis policy")
    target = float(analysis["injection_amplitude_sigma"])
    amplitudes = list(args.amplitude) if args.amplitude else [target]
    if target not in amplitudes:
        amplitudes.append(target)
    payload = run_injection_recovery(
        pd.read_csv(args.input),
        source_column=args.source,
        time_column=args.time,
        flux_column=args.flux,
        error_column=args.error,
        amplitudes_sigma=amplitudes,
        width_days=args.width_days,
        recovery_threshold_sigma=args.threshold_sigma,
        trials_per_amplitude=args.trials,
        confidence_level=float(analysis["confidence_level"]),
        seed=int(analysis["random_seed"]),
    )
    payload["study_id"] = preregistration.study_id
    payload["protocol_digest"] = preregistration.protocol_digest
    payload.pop("result_digest", None)
    payload["result_digest"] = digest_value(payload)
    _emit_new_json(payload, args.output)
    return 0


def _command_fixture_record(args: argparse.Namespace) -> int:
    from siderea.operations import record_service_fixture

    request = _load_json_mapping(args.request_json, "fixture request")
    headers: Mapping[str, Any] = {}
    if args.headers_json is not None:
        headers = _load_json_mapping(args.headers_json, "fixture response headers")
    fixture = record_service_fixture(
        args.output,
        service=args.service,
        service_version=args.service_version,
        capture_mode=args.capture_mode,
        scenario=args.scenario,
        request=request,
        status_code=args.status_code,
        response_headers=headers,
        response_body=args.response_file.read_bytes(),
    )
    _emit_json(
        {
            "output": args.output.expanduser().resolve(),
            "fixture_id": fixture.fixture_id,
            "service": fixture.service,
            "capture_mode": fixture.capture_mode,
            "scenario": fixture.scenario,
        }
    )
    return 0


def _command_fixture_verify(args: argparse.Namespace) -> int:
    from siderea.operations import load_service_fixture

    fixture = load_service_fixture(args.fixture)
    replayed = False
    if args.request_json is not None:
        fixture.replay(_load_json_mapping(args.request_json, "fixture replay request"))
        replayed = True
    _emit_json(
        {
            "fixture_id": fixture.fixture_id,
            "service": fixture.service,
            "valid": True,
            "replay_request_verified": replayed,
        }
    )
    return 0


def _command_broker_archive(args: argparse.Namespace) -> int:
    from siderea.operations import BrokerArchive

    record = BrokerArchive(args.archive).archive_snapshot(
        args.photometry_csv,
        stream=args.stream,
        cursor=args.cursor,
        watermark_mjd=args.watermark_mjd,
    )
    _emit_json(record)
    return 0


def _command_broker_replay(args: argparse.Namespace) -> int:
    from siderea.operations import BrokerArchive

    photometry, sidecar = BrokerArchive(args.archive).replay(args.snapshot_id, args.output_dir)
    _emit_json({"photometry": photometry, "provenance": sidecar})
    return 0


def _command_asset_bundle(args: argparse.Namespace) -> int:
    from siderea.operations import EvidenceAssetSpec, create_evidence_asset_bundle

    candidate = _load_candidate(args.candidates_json, args.candidate_id)
    raw = json.loads(args.assets_json.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or any(not isinstance(item, Mapping) for item in raw):
        raise ValueError("assets JSON must contain an array of asset objects")
    allowed = {
        "role",
        "path",
        "media_type",
        "survey",
        "instrument",
        "observation_time",
        "calibration",
    }
    assets = []
    for item in raw:
        if set(item) != allowed:
            raise ValueError("asset specification has missing or unknown fields")
        raw_path = Path(str(item["path"]))
        path = raw_path if raw_path.is_absolute() else args.assets_json.parent / raw_path
        calibration = item["calibration"]
        if not isinstance(calibration, Mapping):
            raise ValueError("asset calibration must be an object")
        assets.append(
            EvidenceAssetSpec(
                role=str(item["role"]),
                path=path,
                media_type=str(item["media_type"]),
                survey=str(item["survey"]),
                instrument=str(item["instrument"]),
                observation_time=str(item["observation_time"]),
                calibration=dict(calibration),
            )
        )
    payload = create_evidence_asset_bundle(
        args.output_dir,
        candidate=candidate,
        assets=assets,
    )
    _emit_json(
        {
            "output": args.output_dir.expanduser().resolve(),
            "bundle_digest": payload["bundle_digest"],
            "candidate_version": payload["candidate_version"],
        }
    )
    return 0


def _command_schema_register(args: argparse.Namespace) -> int:
    from siderea.operations import OperationsLedger

    digest = OperationsLedger(args.operations_ledger).register_schema_contract(
        args.stream, _load_json_mapping(args.fields_json, "schema fields")
    )
    _emit_json({"stream": args.stream, "fields_digest": digest})
    return 0


def _command_schema_observe(args: argparse.Namespace) -> int:
    from siderea.operations import OperationsLedger

    event = OperationsLedger(args.operations_ledger).observe_schema(
        args.stream, _load_json_mapping(args.fields_json, "observed schema fields")
    )
    _emit_json(event)
    return 0 if event.level == "info" else 3


def _command_recovery_drill(args: argparse.Namespace) -> int:
    from siderea.operations import OperationsLedger

    event = OperationsLedger(args.operations_ledger).record_recovery_drill(
        args.name,
        passed=args.passed,
        evidence=_load_json_mapping(args.evidence_json, "recovery evidence"),
    )
    _emit_json(event)
    return 0 if args.passed else 3


def _command_operations_action(args: argparse.Namespace) -> int:
    from siderea.operations import BrokerArchive, OperationsLedger
    from siderea.operations.recovery import check_sqlite_recovery

    if args.command == "tns-qualify":
        from siderea.clients.base import ResilientExecutor
        from siderea.clients.tns import TNSClient, TNSCredentials
        from siderea.operations.qualification import qualify_tns_live
        from siderea.provenance import stable_json

        if args.output.exists():
            raise ValueError("qualification output already exists; choose a new report path")
        values = [
            os.environ.get(key, "").strip() for key in ("TNS_API_KEY", "TNS_BOT_ID", "TNS_BOT_NAME")
        ]
        if not all(values):
            raise ValueError("set TNS_API_KEY, TNS_BOT_ID, and TNS_BOT_NAME for live qualification")
        client = TNSClient(TNSCredentials(*values), executor=ResilientExecutor(attempts=1))
        qualification = qualify_tns_live(
            client,
            query=_load_json_mapping(args.query_json, "TNS qualification query"),
            expected_status=args.expected_status,
            expected_names=args.expected_name,
        )
        encoded = (stable_json(qualification) + "\n").encode()
        atomic_create_binary(args.output, lambda handle: handle.write(encoded))
        _emit_json(qualification)
        return 0 if qualification["passed"] else 3

    if args.command == "fixture-qualify-tns":
        from siderea.operations.fixtures import load_service_fixture
        from siderea.operations.qualification import qualify_tns_fixtures
        from siderea.provenance import stable_json

        qualification = qualify_tns_fixtures(
            [load_service_fixture(path) for path in args.fixtures],
            query=_load_json_mapping(args.query_json, "TNS qualification query"),
            expected_status=args.expected_status,
        )
        encoded = (stable_json(qualification) + "\n").encode()
        atomic_create_binary(args.output, lambda handle: handle.write(encoded))
        _emit_json(qualification)
        return 0 if qualification["passed"] else 3

    if args.command.startswith("evidence-"):
        import zipfile

        from siderea.operations.backup import (
            create_evidence_backup,
            restore_evidence_backup,
            verify_evidence_backup,
        )

        try:
            if args.command == "evidence-backup":
                backup_result = create_evidence_backup(
                    args.ledger,
                    args.artifact_root,
                    args.output,
                    additional_files=args.additional_files,
                )
            elif args.command == "evidence-restore":
                backup_result = restore_evidence_backup(args.archive, args.destination)
            else:
                backup_result = verify_evidence_backup(args.archive)
        except (zipfile.BadZipFile, KeyError) as exc:
            raise ValueError("backup is malformed or lacks a required file") from exc
        _emit_json(backup_result)
        return 0

    if args.command == "incident-resolve":
        result = OperationsLedger(args.operations_ledger).resolve_incident(
            args.event_id,
            reason=args.reason,
            evidence=_load_json_mapping(args.evidence_json, "resolution evidence"),
        )
        _emit_json(result)
    elif args.command == "recovery-check":
        report = check_sqlite_recovery(args.database)
        evidence = {key: value for key, value in report.items() if key != "passed"}
        OperationsLedger(args.operations_ledger).record_recovery_drill(
            "sqlite_backup_restore",
            passed=report["passed"],
            evidence=evidence,
        )
        _emit_json(report)
        return 0 if report["passed"] else 3
    else:
        archive = BrokerArchive(args.archive)
        if args.command == "dead-letter-resolve":
            archive.resolve_dead_letter(
                args.id,
                reason=args.reason,
                evidence=_load_json_mapping(args.evidence_json, "resolution evidence"),
            )
        report = archive.verify_archive() if args.command == "broker-check" else archive.inventory()
        _emit_json(report)
        if args.command == "broker-check":
            return 0 if report["passed"] else 3
    return 0


def _command_ops_health(args: argparse.Namespace) -> int:
    from siderea.operations import OperationsLedger

    report = OperationsLedger(args.operations_ledger).health_report(since=args.since)
    _emit_json(report)
    return 0 if report["healthy"] else 3


def _command_principal_assertion_create(args: argparse.Namespace) -> int:
    from siderea.identity import create_principal_assertion

    payload = create_principal_assertion(
        args.output,
        _load_json_mapping(args.assertion_json, "principal assertion payload"),
        signing_key=args.key_file.read_bytes(),
    )
    _emit_json(
        {
            "output": args.output.expanduser().resolve(),
            "assertion_digest": payload["assertion_digest"],
            "key_id": payload["key_id"],
        }
    )
    return 0


def _command_principal_assertion_verify(args: argparse.Namespace) -> int:
    from siderea.identity import verify_principal_assertion

    principal = verify_principal_assertion(
        args.assertion,
        verification_key=args.key_file.read_bytes(),
        required_role=args.role,
    )
    _emit_json(principal)
    return 0


def _command_promotion_check(args: argparse.Namespace) -> int:
    from siderea.ledger import OutcomeLedger
    from siderea.operations import BrokerArchive, OperationsLedger
    from siderea.promotion import PromotionSignoffRegistry, evaluate_promotion
    from siderea.research import load_preregistration

    report = evaluate_promotion(
        load_preregistration(args.preregistration),
        cohort_export=args.cohort_export,
        outcome_ledger=OutcomeLedger(args.outcome_ledger.expanduser().resolve()),
        benchmark=args.benchmark,
        injection=args.injection,
        fixture_directory=args.fixture_directory,
        broker_archive=BrokerArchive(args.broker_archive),
        asset_directory=args.asset_directory,
        operations_ledger=OperationsLedger(args.operations_ledger),
        signoff_registry=PromotionSignoffRegistry(args.signoff_registry),
    )
    if args.output is None:
        _emit_json(report)
    else:
        _emit_new_json(report, args.output)
    return 0 if report["ready"] else 3


def _command_promotion_sign(args: argparse.Namespace) -> int:
    from siderea.identity import verify_principal_assertion
    from siderea.promotion import PROMOTION_REPORT_SCHEMA, PromotionSignoffRegistry
    from siderea.provenance import digest_value
    from siderea.research import load_preregistration

    preregistration = load_preregistration(args.preregistration)
    report = _load_json_mapping(args.promotion_report, "promotion report")
    if report.get("schema") != PROMOTION_REPORT_SCHEMA:
        raise ValueError(f"promotion report schema must be {PROMOTION_REPORT_SCHEMA!r}")
    materialized = dict(report)
    stored_report_digest = str(materialized.pop("report_digest", "")).casefold()
    if not hmac.compare_digest(stored_report_digest, digest_value(materialized)):
        raise ValueError("promotion report digest differs from its content")
    evidence_digest = str(report.get("evidence_digest", ""))
    principal = verify_principal_assertion(
        args.principal_assertion,
        verification_key=args.key_file.read_bytes(),
        required_role=None,
    )
    signoff = PromotionSignoffRegistry(args.signoff_registry).add(
        preregistration,
        evidence_digest=evidence_digest,
        area=args.area,
        verdict=args.verdict,
        rationale=args.rationale,
        principal=principal,
    )
    _emit_json(signoff)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the SIDEREA CLI and return a process exit code."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return _doctor(args.config, strict=args.strict, as_json=args.json)
        if args.command == "config-show":
            _emit_json(config_to_dict(load_config(args.config)))
            return 0
        if args.command == "dossier":
            return _command_dossier(args)
        if args.command == "baseline-train":
            return _command_baseline_train(args)
        local_dispatch = {
            **{
                name: _command_operations_action
                for name in (
                    "broker-inventory",
                    "broker-check",
                    "dead-letter-resolve",
                    "incident-resolve",
                    "recovery-check",
                    "fixture-qualify-tns",
                    "tns-qualify",
                    "evidence-backup",
                    "evidence-backup-verify",
                    "evidence-restore",
                )
            },
            "study-freeze": _command_study_freeze,
            "cohort-enroll": _command_cohort_enroll,
            "cohort-export": _command_cohort_export,
            "benchmark-run": _command_benchmark_run,
            "pilot-prepare": _command_pilot_prepare,
            "transient-shard": _command_transient_shard,
            "transient-merge": _command_transient_merge,
            "jepa-embed": _command_jepa_embed,
            "jepa-reference-freeze": _command_jepa_reference_freeze,
            "shadow-assemble": _command_shadow_assemble,
            "shadow-rank": _command_shadow_rank,
            "injection-run": _command_injection_run,
            "transient-search": _command_transient_search,
            "fixture-record": _command_fixture_record,
            "fixture-verify": _command_fixture_verify,
            "broker-archive": _command_broker_archive,
            "broker-replay": _command_broker_replay,
            "asset-bundle": _command_asset_bundle,
            "schema-register": _command_schema_register,
            "schema-observe": _command_schema_observe,
            "recovery-drill": _command_recovery_drill,
            "ops-health": _command_ops_health,
            "principal-assertion-create": _command_principal_assertion_create,
            "principal-assertion-verify": _command_principal_assertion_verify,
            "promotion-check": _command_promotion_check,
            "promotion-sign": _command_promotion_sign,
        }
        if args.command in local_dispatch:
            return local_dispatch[args.command](args)

        config = load_config(args.config)
        dispatch = {
            "analyze": _command_analyze,
            "broker-fetch": _command_broker_fetch,
            "verify": _command_verify,
            "queue": _command_queue,
            "review-set": _command_review_set,
            "review-add": _command_review_add,
            "adjudication-add": _command_adjudication_add,
            "review-serve": _command_review_serve,
            "outcome-add": _command_outcome_add,
            "outcome-summary": _command_outcome_summary,
            "preflight": _command_preflight,
            "jepa-train": _command_jepa_train,
        }
        return dispatch[args.command](args, config)
    except (
        ConfigError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        sqlite3.DatabaseError,
    ) as exc:
        print(f"siderea: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
