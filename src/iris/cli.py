"""Command-line interface for the IRIS discovery and review platform."""

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
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from iris import __version__
from iris.atomic import atomic_write_text, fsync_directory
from iris.config import ConfigError, IRISConfig, config_to_dict, load_config

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
        help="TOML configuration (default: IRIS_CONFIG, checkout config, or packaged default)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="iris",
        description="Reproducible, human-supervised astronomical transient discovery.",
    )
    parser.add_argument("--version", action="version", version=f"IRIS {__version__}")
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
    review_add.add_argument("--reviewer", required=True)
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
    adjudication.add_argument("--adjudicator", required=True)
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

    outcome = commands.add_parser("outcome-add", help="record a confirmed downstream outcome")
    _config_argument(outcome)
    outcome.add_argument("candidate_id")
    outcome.add_argument("--ledger", type=Path, default=None)
    outcome.add_argument("--candidate-version", required=True)
    outcome.add_argument("--outcome", required=True)
    outcome.add_argument("--designation", default="")
    outcome.add_argument("--taxonomy-version", default="iris.outcome.v1")
    outcome.add_argument("--evidence-json", type=Path, default=None)

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
        print("IRIS doctor")
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
    from iris.evidence_context import canonical_verification_context
    from iris.provenance import CheckProvenance, CheckStatus

    checks: dict[str, tuple[CheckProvenance, ...]] = {}
    manual: dict[str, bool] = {}
    contexts: dict[str, dict[str, tuple[str, ...]]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"verification file must contain a JSON object: {path}")
        if payload.get("schema") != "iris.verification.v1":
            raise ValueError(f"verification file schema must be 'iris.verification.v1': {path}")
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


def _command_analyze(args: argparse.Namespace, config: IRISConfig) -> int:
    from iris.pipeline import analyze_csv

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


def _command_broker_fetch(args: argparse.Namespace, config: IRISConfig) -> int:
    from iris.ingest import AlerceAdapter, BrokerQuery
    from iris.ingest.snapshot import (
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


def _tns_client(config: IRISConfig, *, disabled: bool) -> Any | None:
    if disabled:
        return None
    from iris.clients.base import ResilientExecutor
    from iris.clients.tns import TNSClient, TNSCredentials

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


def _command_verify(args: argparse.Namespace, config: IRISConfig) -> int:
    from iris.clients.base import ResilientExecutor
    from iris.clients.catalogs import SimbadClient, SkyBotClient, VSXClient
    from iris.validation import VerificationSuite

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
        "schema": "iris.verification.v1",
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


def _queue_policy(args: argparse.Namespace, config: IRISConfig) -> tuple[int, int, str | None]:
    audit_slots = args.audit_slots if args.audit_slots is not None else config.ranking.audit_slots
    audit_seed = args.audit_seed
    if audit_slots > 0 and not (audit_seed or "").strip():
        audit_seed = secrets.token_hex(16)
    anomaly_slots = (
        args.anomaly_slots if args.anomaly_slots is not None else config.ranking.anomaly_slots
    )
    return anomaly_slots, audit_slots, audit_seed


def _command_queue(args: argparse.Namespace, config: IRISConfig) -> int:
    from iris.review import queue_from_csv

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


def _command_review_set(args: argparse.Namespace, config: IRISConfig) -> int:
    from iris.review import assemble_review_set

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
    from iris.review import write_candidate_dossier

    record = _load_candidate(args.candidates_json, args.candidate_id)
    path = write_candidate_dossier(
        args.output_dir,
        candidate=record,
        features=dict(record.get("features", {})),
        checks=list(record.get("external_checks", [])),
    )
    print(path.resolve())
    return 0


def _ledger(config: IRISConfig, path: Path | None) -> Any:
    from iris.ledger import OutcomeLedger

    return OutcomeLedger(
        path.expanduser().resolve() if path else config.storage.root / "outcomes.sqlite"
    )


def _command_review_add(args: argparse.Namespace, config: IRISConfig) -> int:
    ledger = _ledger(config, args.ledger)
    if ledger.candidate(args.candidate_id) is None:
        raise ValueError(f"unknown candidate in ledger: {args.candidate_id}")
    record = ledger.add_review(
        args.candidate_id,
        reviewer=args.reviewer,
        role=args.role,
        verdict=args.verdict,
        reason=args.reason,
        candidate_version=args.candidate_version,
    )
    _emit_json(record)
    return 0


def _command_adjudication_add(args: argparse.Namespace, config: IRISConfig) -> int:
    record = _ledger(config, args.ledger).add_adjudication(
        args.candidate_id,
        adjudicator=args.adjudicator,
        verdict=args.verdict,
        reason=args.reason,
        candidate_version=args.candidate_version,
    )
    _emit_json(record)
    return 0


def _command_review_serve(args: argparse.Namespace, config: IRISConfig) -> int:
    from iris.review import serve_review

    serve_review(_ledger(config, args.ledger), host=args.host, port=args.port)
    return 0


def _command_outcome_add(args: argparse.Namespace, config: IRISConfig) -> int:
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


def _command_preflight(args: argparse.Namespace, config: IRISConfig) -> int:
    """Evaluate the stored, immutable evidence package without drafting a report."""

    from iris.provenance import CheckProvenance
    from iris.reporting import reporting_preflight

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

    from iris.ml.baseline import BaselineConfig, fit_baseline, save_baseline_bundle

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


def _command_jepa_train(args: argparse.Namespace, config: IRISConfig) -> int:
    from iris.ml import (
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
    from iris.provenance import digest_file, digest_value

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
    )
    selected_batch_size = args.batch_size if args.batch_size is not None else config.jepa.batch_size
    training_config = TrainingConfig(
        epochs=args.epochs,
        batch_size=selected_batch_size,
        learning_rate=config.jepa.learning_rate,
        target_fraction=config.jepa.mask_fraction,
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
            "schema": "iris.jepa_training.v2",
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


def main(argv: Sequence[str] | None = None) -> int:
    """Run the IRIS CLI and return a process exit code."""

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
            "preflight": _command_preflight,
            "jepa-train": _command_jepa_train,
        }
        return dispatch[args.command](args, config)
    except (ConfigError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"iris: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
