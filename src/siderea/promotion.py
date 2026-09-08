"""Fail-closed scientific-promotion evidence and authenticated sign-offs."""

from __future__ import annotations

import hmac
import json
import math
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from siderea.identity import AuthenticatedPrincipal
from siderea.ledger import OutcomeLedger, ReviewRecord
from siderea.operations import (
    BrokerArchive,
    OperationsLedger,
    load_service_fixture,
    verify_evidence_asset_bundle,
)
from siderea.provenance import digest_file, digest_value
from siderea.research.preregistration import Preregistration
from siderea.research.qualification import bind_benchmark, cohort_labels, valid_interval

PROMOTION_REPORT_SCHEMA = "siderea.promotion_report.v2"
PROMOTION_SIGNOFF_SCHEMA = "siderea.promotion_signoff.v1"
_SIGNOFF_VERDICTS = frozenset({"approve", "reject"})


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _load_json(path: str | Path, schema: str) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {schema} artifact {source}: {exc}") from exc
    if not isinstance(raw, Mapping) or raw.get("schema") != schema:
        raise ValueError(f"artifact {source} must use schema {schema!r}")
    return dict(raw)


def _verify_embedded_digest(payload: Mapping[str, Any], field: str) -> str:
    materialized = dict(payload)
    stored = _text(materialized.pop(field, None), field).casefold()
    computed = digest_value(materialized)
    if not hmac.compare_digest(stored, computed):
        raise ValueError(f"{field} does not match artifact content")
    return stored


@dataclass(frozen=True, slots=True)
class PromotionSignoff:
    study_id: str
    protocol_digest: str
    evidence_digest: str
    area: str
    verdict: str
    principal_id: str
    principal_assertion_digest: str
    principal_key_id: str
    principal_assurance: str
    rationale: str
    created_at: str


class PromotionSignoffRegistry:
    """Append-only sign-offs over one complete promotion-evidence digest."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 5000")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS signoffs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    study_id TEXT NOT NULL,
                    protocol_digest TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    area TEXT NOT NULL,
                    verdict TEXT NOT NULL CHECK(verdict IN ('approve','reject')),
                    principal_id TEXT NOT NULL,
                    principal_assertion_digest TEXT NOT NULL,
                    principal_key_id TEXT NOT NULL,
                    principal_assurance TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS promotion_signoffs_no_update
                BEFORE UPDATE ON signoffs BEGIN
                    SELECT RAISE(ABORT, 'promotion signoffs are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS promotion_signoffs_no_delete
                BEFORE DELETE ON signoffs BEGIN
                    SELECT RAISE(ABORT, 'promotion signoffs are append-only');
                END;
                """
            )

    def add(
        self,
        preregistration: Preregistration,
        *,
        evidence_digest: str,
        area: str,
        verdict: str,
        rationale: str,
        principal: AuthenticatedPrincipal,
    ) -> PromotionSignoff:
        preregistration = preregistration.validated()
        governance = preregistration.protocol.get("governance")
        if not isinstance(governance, Mapping):
            raise ValueError("preregistration has invalid governance policy")
        signoff_area = _text(area, "area").casefold()
        required_areas = governance.get("required_signoff_areas")
        if isinstance(required_areas, (str, bytes)) or not isinstance(required_areas, Sequence):
            raise ValueError("preregistration has invalid sign-off areas")
        normalized_areas = {str(value).strip().casefold() for value in required_areas}
        if signoff_area not in normalized_areas:
            raise ValueError("sign-off area is not required by the preregistration")
        trusted_keys = governance.get("trusted_assertion_key_ids")
        if isinstance(trusted_keys, (str, bytes)) or not isinstance(trusted_keys, Sequence):
            raise ValueError("preregistration has invalid trusted assertion keys")
        if principal.key_id not in {str(value).casefold() for value in trusted_keys}:
            raise ValueError("principal assertion key is not trusted by the preregistration")
        required_role = f"{signoff_area}_signoff"
        if required_role not in principal.roles and "promotion_signoff" not in principal.roles:
            raise ValueError(f"principal assertion lacks role {required_role!r}")
        principal.require_current(
            required_role if required_role in principal.roles else "promotion_signoff",
            tuple(str(value) for value in trusted_keys),
        )
        normalized_verdict = _text(verdict, "verdict").casefold()
        if normalized_verdict not in _SIGNOFF_VERDICTS:
            raise ValueError("sign-off verdict must be approve or reject")
        evidence = _text(evidence_digest, "evidence_digest").casefold()
        if len(evidence) != 64 or any(
            character not in "0123456789abcdef" for character in evidence
        ):
            raise ValueError("evidence_digest must be a SHA-256 digest")
        record = PromotionSignoff(
            study_id=preregistration.study_id,
            protocol_digest=preregistration.protocol_digest,
            evidence_digest=evidence,
            area=signoff_area,
            verdict=normalized_verdict,
            principal_id=principal.principal_id,
            principal_assertion_digest=principal.assertion_digest,
            principal_key_id=principal.key_id,
            principal_assurance=principal.assurance_level,
            rationale=_text(rationale, "rationale"),
            created_at=datetime.now(UTC).isoformat(),
        )
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO signoffs(
                    study_id, protocol_digest, evidence_digest, area, verdict,
                    principal_id, principal_assertion_digest, principal_key_id,
                    principal_assurance, rationale, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(asdict(record).values()),
            )
        return record

    def records(self, study_id: str, evidence_digest: str) -> tuple[PromotionSignoff, ...]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT study_id, protocol_digest, evidence_digest, area, verdict,
                       principal_id, principal_assertion_digest, principal_key_id,
                       principal_assurance, rationale, created_at
                FROM signoffs
                WHERE study_id=? AND evidence_digest=?
                ORDER BY id
                """,
                (study_id.strip(), evidence_digest.strip().casefold()),
            ).fetchall()
        return tuple(PromotionSignoff(**dict(row)) for row in rows)


def _authenticated_review_gate(
    ledger: OutcomeLedger,
    cohort_records: Sequence[Mapping[str, Any]],
) -> tuple[bool, str, int]:
    checked = 0
    for enrollment in cohort_records:
        if not bool(enrollment.get("selected")):
            continue
        candidate_id = _text(enrollment.get("candidate_id"), "cohort candidate_id")
        version = _text(enrollment.get("candidate_version"), "cohort candidate_version")
        archived = ledger.candidate_version(candidate_id, version)
        if archived is None:
            return False, f"cannot reconstruct {candidate_id!r} at its enrolled version", checked
        payload = archived.get("payload")
        if not isinstance(payload, Mapping):
            return False, f"candidate {candidate_id!r} has invalid archived payload", checked
        policy = payload.get("review_policy")
        if not isinstance(policy, Mapping):
            return False, f"candidate {candidate_id!r} has no review policy", checked
        raw_required = policy.get("required_reviewers")
        if isinstance(raw_required, bool) or not isinstance(raw_required, int) or raw_required < 1:
            return False, f"candidate {candidate_id!r} has invalid reviewer policy", checked
        reviews = ledger.reviews_for(candidate_id, candidate_version=version)
        latest: dict[tuple[str, str], ReviewRecord] = {}
        for review in reviews:
            latest[(review.reviewer, review.role)] = review
        active = tuple(latest.values())
        authenticated = ledger._authenticated_decisions(candidate_id, version, "reviews")
        if any(review.verdict == "reject" for review in active):
            return False, f"candidate {candidate_id!r} has an unresolved rejection", checked
        screeners = {
            review.reviewer
            for review in active
            if review.role == "screener"
            and review.verdict == "approve"
            and (review.reviewer, review.created_at) in authenticated
        }
        reviewers = {
            review.reviewer
            for review in active
            if review.role == "reviewer"
            and review.verdict == "approve"
            and (review.reviewer, review.created_at) in authenticated
        }
        independent = reviewers - screeners
        if not screeners or len(independent) < raw_required:
            return (
                False,
                f"candidate {candidate_id!r} lacks authenticated independent approvals",
                checked,
            )
        checked += 1
    return (checked > 0, "authenticated exact-version approvals verified", checked)


def evaluate_promotion(
    preregistration: Preregistration,
    *,
    cohort_export: str | Path,
    outcome_ledger: OutcomeLedger,
    benchmark: str | Path,
    injection: str | Path,
    fixture_directory: str | Path,
    broker_archive: BrokerArchive,
    asset_directory: str | Path,
    operations_ledger: OperationsLedger,
    signoff_registry: PromotionSignoffRegistry,
) -> dict[str, Any]:
    """Evaluate every preregistered promotion gate without granting exceptions."""

    from siderea.research.benchmark import ROLLING_BENCHMARK_SCHEMA
    from siderea.research.cohort import COHORT_EXPORT_SCHEMA
    from siderea.research.injection import INJECTION_RECOVERY_SCHEMA

    preregistration = preregistration.validated()
    protocol = preregistration.protocol
    analysis_raw = protocol.get("analysis")
    operations_raw = protocol.get("operations")
    governance_raw = protocol.get("governance")
    if not isinstance(analysis_raw, Mapping):
        raise ValueError("preregistration promotion analysis policy is invalid")
    if not isinstance(operations_raw, Mapping):
        raise ValueError("preregistration promotion operations policy is invalid")
    if not isinstance(governance_raw, Mapping):
        raise ValueError("preregistration promotion policies are invalid")
    analysis = analysis_raw
    operations = operations_raw
    governance = governance_raw

    gates: list[dict[str, Any]] = []

    cohort = _load_json(cohort_export, COHORT_EXPORT_SCHEMA)
    cohort_digest = _verify_embedded_digest(cohort, "cohort_digest")
    cohort_records = cohort.get("records")
    if isinstance(cohort_records, (str, bytes)) or not isinstance(cohort_records, Sequence):
        raise ValueError("cohort export records must be an array")
    if any(not isinstance(item, Mapping) for item in cohort_records):
        raise ValueError("cohort export records must be objects")
    cohort_detail = "matured exact-version outcomes verified"
    try:
        cohort_labels(cohort, preregistration)
        if cohort.get("capture_mode") != "prospective":
            raise ValueError("retrospective reconstruction cannot qualify as a prospective cohort")
        for enrollment in cohort_records:
            if enrollment.get("capture_mode") != "prospective":
                raise ValueError("cohort contains non-prospective enrollment")
            recorded_at = datetime.fromisoformat(enrollment["recorded_at"])
            enrolled_at = datetime.fromisoformat(enrollment["enrolled_at"])
            if (
                recorded_at.tzinfo is None
                or recorded_at < enrolled_at
                or (recorded_at - enrolled_at).total_seconds() > 60
                or recorded_at > datetime.fromisoformat(protocol["cohort"]["closes_at"])
            ):
                raise ValueError("prospective enrollment was not recorded contemporaneously")
            archived = outcome_ledger.candidate_version(
                str(enrollment["candidate_id"]), str(enrollment["candidate_version"])
            )
            if archived is None:
                raise ValueError("enrolled candidate cannot be reconstructed from the ledger")
            actual = [
                asdict(outcome)
                for outcome in outcome_ledger.outcomes_for(str(enrollment["candidate_id"]))
                if outcome.candidate_version == enrollment["candidate_version"]
                and datetime.fromisoformat(outcome.recorded_at)
                <= datetime.fromisoformat(cohort["as_of"])
            ]
            if actual != enrollment.get("outcomes"):
                raise ValueError("cohort outcomes differ from the outcome ledger")
        cohort_ok = True
    except (ValueError, KeyError, TypeError) as exc:
        cohort_ok = False
        cohort_detail = str(exc)
    gates.append(
        {
            "gate": "prospective_matured_cohort",
            "passed": cohort_ok,
            "detail": cohort_detail,
        }
    )

    review_ok, review_detail, reviewed_count = _authenticated_review_gate(
        outcome_ledger, [dict(item) for item in cohort_records]
    )
    gates.append(
        {
            "gate": "authenticated_exact_version_reviews",
            "passed": review_ok,
            "detail": review_detail,
            "reviewed_candidate_count": reviewed_count,
        }
    )

    benchmark_payload = _load_json(benchmark, ROLLING_BENCHMARK_SCHEMA)
    benchmark_digest = _verify_embedded_digest(benchmark_payload, "result_digest")
    try:
        rebound = bind_benchmark(benchmark_payload, cohort, preregistration)
        if rebound != benchmark_payload:
            raise ValueError("benchmark is not bound to this cohort and protocol")
        benchmark_bound = True
        binding_detail = ""
    except (ValueError, KeyError, TypeError) as exc:
        benchmark_bound = False
        binding_detail = str(exc)
    summary = benchmark_payload.get("summary")
    comparison = str(analysis["comparison"])
    primary_metric = str(analysis["primary_metric"])
    minimum_effect = float(analysis["minimum_useful_effect"])
    benchmark_ok = False
    benchmark_detail = "preregistered comparison or metric is absent"
    if isinstance(summary, Mapping) and isinstance(summary.get(comparison), Mapping):
        comparison_metrics = summary[comparison]
        metric = comparison_metrics.get(primary_metric)
        if isinstance(metric, Mapping):
            delta_interval = metric.get("delta_confidence_interval")
            if isinstance(delta_interval, (list, tuple)) and valid_interval(
                delta_interval, lower=-1.0, upper=1.0
            ):
                lower = float(delta_interval[0])
                benchmark_ok = benchmark_bound and cohort_ok and lower >= minimum_effect
                benchmark_detail = (
                    f"lower confidence bound {lower:.6g}; required {minimum_effect:.6g}"
                )
    if not benchmark_bound:
        benchmark_detail = binding_detail
    gates.append(
        {"gate": "rolling_origin_effect", "passed": benchmark_ok, "detail": benchmark_detail}
    )

    injection_payload = _load_json(injection, INJECTION_RECOVERY_SCHEMA)
    injection_digest = _verify_embedded_digest(injection_payload, "result_digest")
    injection_results = injection_payload.get("results")
    target_amplitude = float(analysis["injection_amplitude_sigma"])
    required_recovery = float(analysis["minimum_injection_recovery"])
    target_result: Mapping[str, Any] | None = None
    if isinstance(injection_results, Sequence) and not isinstance(injection_results, (str, bytes)):
        for raw_result in injection_results:
            if isinstance(raw_result, Mapping) and math.isclose(
                float(raw_result.get("amplitude_sigma", math.nan)),
                target_amplitude,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                target_result = raw_result
                break
    injection_ok = False
    injection_detail = "preregistered injection amplitude is absent"
    if target_result is not None:
        interval = target_result.get("confidence_interval")
        if isinstance(interval, (list, tuple)) and valid_interval(interval, lower=0.0, upper=1.0):
            lower_recovery = float(interval[0])
            injection_ok = (
                lower_recovery >= required_recovery
                and injection_payload.get("protocol_digest") == preregistration.protocol_digest
                and injection_payload.get("study_id") == preregistration.study_id
                and injection_payload.get("seed") == analysis["random_seed"]
                and injection_payload.get("confidence_level") == analysis["confidence_level"]
            )
            injection_detail = (
                f"lower recovery bound {lower_recovery:.6g}; required {required_recovery:.6g}"
            )
    gates.append(
        {
            "gate": "matched_filter_diagnostic",
            "passed": injection_ok,
            "detail": injection_detail,
            "scope": "known_template_diagnostic_does_not_measure_pipeline_completeness",
        }
    )

    fixture_root = Path(fixture_directory).expanduser().resolve()
    fixture_paths = sorted(fixture_root.glob("*.json")) if fixture_root.is_dir() else []
    fixtures = [load_service_fixture(path) for path in fixture_paths]
    required_services = {str(value).casefold() for value in operations["required_services"]}
    missing_fixture_modes: list[str] = []
    for service in sorted(required_services):
        service_fixtures = [fixture for fixture in fixtures if fixture.service == service]
        if not any(
            fixture.capture_mode == "live"
            and fixture.scenario == "success"
            and 200 <= fixture.status_code < 300
            for fixture in service_fixtures
        ):
            missing_fixture_modes.append(f"{service}:live-success")
        if not any(fixture.scenario == "failure" for fixture in service_fixtures):
            missing_fixture_modes.append(f"{service}:failure")
    gates.append(
        {
            "gate": "recorded_service_fixture_coverage",
            "passed": not missing_fixture_modes,
            "detail": (
                f"{len(fixtures)} fixture(s) cover success and failure"
                if not missing_fixture_modes
                else "missing " + ", ".join(missing_fixture_modes)
            ),
        }
    )

    broker_inventory = broker_archive.inventory()
    broker_verification = broker_archive.verify_archive()
    minimum_snapshots = int(operations["minimum_broker_snapshots"])
    broker_ok = (
        int(broker_inventory["snapshot_count"]) >= minimum_snapshots
        and int(broker_inventory["unresolved_dead_letter_count"]) == 0
        and broker_verification["passed"] is True
    )
    gates.append(
        {
            "gate": "verified_broker_replay",
            "passed": broker_ok,
            "detail": (
                f"{broker_inventory['snapshot_count']} snapshot(s), "
                f"{broker_inventory['dead_letter_count']} dead letter(s)"
            ),
        }
    )

    selected_pairs = {
        (str(item.get("candidate_id")), str(item.get("candidate_version")))
        for item in cohort_records
        if bool(item.get("selected"))
    }
    asset_root = Path(asset_directory).expanduser().resolve()
    bundles: list[dict[str, Any]] = []
    if asset_root.is_dir():
        for manifest_path in sorted(asset_root.glob("*/manifest.json")):
            bundles.append(verify_evidence_asset_bundle(manifest_path.parent))
    covered_pairs = {
        (str(bundle["candidate_id"]), str(bundle["candidate_version"])) for bundle in bundles
    }
    require_assets = bool(operations["require_image_evidence"])
    asset_ok = not require_assets or bool(selected_pairs) and selected_pairs <= covered_pairs
    gates.append(
        {
            "gate": "asset_integrity_and_completeness",
            "passed": asset_ok,
            "scope": "packaged_file_integrity_not_image_or_calibration_scientific_validation",
            "detail": (
                f"{len(covered_pairs & selected_pairs)}/{len(selected_pairs)} "
                "selected versions covered"
            ),
        }
    )

    health = operations_ledger.health_report(since=str(protocol["cohort"]["opens_at"]))
    required_drills = int(operations["required_recovery_drills"])
    maximum_drifts = int(operations["maximum_schema_drifts"])
    operations_ok = (
        bool(health["healthy"])
        and int(health["recovery_drill_pass_count"]) >= required_drills
        and int(health["unresolved_schema_drift_count"]) <= maximum_drifts
    )
    gates.append(
        {
            "gate": "observability_and_recovery",
            "passed": operations_ok,
            "detail": (
                f"{health['recovery_drill_pass_count']} recovery drill(s), "
                f"{health['schema_drift_count']} drift(s), {health['failure_count']} failure(s)"
            ),
        }
    )

    scientific_gates = [dict(gate) for gate in gates]
    evidence_basis = {
        "schema": PROMOTION_REPORT_SCHEMA,
        "study_id": preregistration.study_id,
        "protocol_digest": preregistration.protocol_digest,
        "artifacts": {
            "cohort_digest": cohort_digest,
            "cohort_file_sha256": digest_file(Path(cohort_export)),
            "benchmark_digest": benchmark_digest,
            "benchmark_file_sha256": digest_file(Path(benchmark)),
            "injection_digest": injection_digest,
            "injection_file_sha256": digest_file(Path(injection)),
            "fixture_ids": sorted(fixture.fixture_id for fixture in fixtures),
            "broker_inventory_digest": broker_inventory["inventory_digest"],
            "broker_replay_verification_digest": broker_verification["report_digest"],
            "asset_bundle_digests": sorted(str(bundle["bundle_digest"]) for bundle in bundles),
            "operations_report_digest": health["report_digest"],
        },
        "gates": scientific_gates,
    }
    evidence_digest = digest_value(evidence_basis)

    required_areas = {str(value).casefold() for value in governance["required_signoff_areas"]}
    required_signoffs = int(governance["independent_signoffs_required"])
    signoffs = signoff_registry.records(preregistration.study_id, evidence_digest)
    latest: dict[tuple[str, str], PromotionSignoff] = {}
    for signoff in signoffs:
        if signoff.protocol_digest == preregistration.protocol_digest:
            latest[(signoff.area, signoff.principal_id)] = signoff
    active = tuple(latest.values())
    rejected_areas = {signoff.area for signoff in active if signoff.verdict == "reject"}
    approvals = tuple(signoff for signoff in active if signoff.verdict == "approve")
    approved_areas = {signoff.area for signoff in approvals}
    principals = {signoff.principal_id for signoff in approvals}
    signoffs_ok = (
        not rejected_areas
        and required_areas <= approved_areas
        and len(principals) >= required_signoffs
    )
    gates.append(
        {
            "gate": "independent_authenticated_signoff",
            "passed": signoffs_ok,
            "detail": (
                f"{len(principals)} independent principal(s); areas "
                f"{sorted(approved_areas)}; rejected {sorted(rejected_areas)}"
            ),
        }
    )
    ready = all(bool(gate["passed"]) for gate in gates)
    report = {
        **evidence_basis,
        "gates": gates,
        "evidence_digest": evidence_digest,
        "signoffs": [asdict(signoff) for signoff in active],
        "ready": ready,
        "status": "evidence_ready_for_independent_review" if ready else "blocked",
        "readiness_scope": "local_evidence_review_not_scientific_or_production_release",
        "limitations": [
            "promotion authenticates integrity within the configured local trust boundary",
            "an external identity issuer must protect the HMAC assertion key",
            "recorded evidence does not substitute for independent scientific judgment",
            "matched-filter diagnostics do not qualify production pipeline completeness",
            "fixture, asset and operations inventories are not executed live-service qualification",
        ],
    }
    report["report_digest"] = digest_value(report)
    return report


__all__ = [
    "PROMOTION_REPORT_SCHEMA",
    "PROMOTION_SIGNOFF_SCHEMA",
    "PromotionSignoff",
    "PromotionSignoffRegistry",
    "evaluate_promotion",
]
