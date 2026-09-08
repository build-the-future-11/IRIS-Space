"""Frozen, machine-verifiable prospective study protocols."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from siderea.atomic import atomic_create_binary
from siderea.provenance import digest_value, stable_json, utc_now

PREREGISTRATION_SCHEMA = "siderea.preregistration.v1"

_PROTOCOL_FIELDS = frozenset(
    {
        "study_id",
        "title",
        "scientific_question",
        "hypotheses",
        "cohort",
        "selection",
        "endpoints",
        "analysis",
        "operations",
        "governance",
    }
)
_COHORT_FIELDS = frozenset(
    {
        "opens_at",
        "closes_at",
        "matures_at",
        "population",
        "inclusion_criteria",
        "exclusion_criteria",
    }
)
_SELECTION_FIELDS = frozenset(
    {
        "pipeline_version",
        "configuration_digest",
        "eligibility_policy",
        "review_budget",
        "audit_slots",
    }
)
_ENDPOINT_FIELDS = frozenset({"primary", "secondary"})
_ANALYSIS_FIELDS = frozenset(
    {
        "primary_metric",
        "comparison",
        "minimum_useful_effect",
        "confidence_level",
        "bootstrap_repeats",
        "random_seed",
        "subgroup_fields",
        "missing_outcome_policy",
        "minimum_injection_recovery",
        "injection_amplitude_sigma",
    }
)
_OPERATIONS_FIELDS = frozenset(
    {
        "required_services",
        "minimum_broker_snapshots",
        "require_image_evidence",
        "required_recovery_drills",
        "maximum_schema_drifts",
    }
)
_GOVERNANCE_FIELDS = frozenset(
    {
        "protocol_owner",
        "statistics_reviewer",
        "independent_signoffs_required",
        "principal_policy",
        "required_signoff_areas",
        "trusted_assertion_key_ids",
    }
)


def _mapping(value: Any, name: str, fields: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    result = dict(value)
    unknown = sorted(set(result) - fields)
    missing = sorted(fields - set(result))
    if unknown:
        raise ValueError(f"{name} has unknown fields: {unknown}")
    if missing:
        raise ValueError(f"{name} is missing fields: {missing}")
    return result


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _texts(value: Any, name: str, *, allow_empty: bool = False) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be an array of strings")
    result = [_text(item, f"{name} item") for item in value]
    if not allow_empty and not result:
        raise ValueError(f"{name} must not be empty")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _integer(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be a finite number")
    return numeric


def _timestamp(value: Any, name: str) -> str:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")
    return parsed.isoformat()


def _digest(value: Any, name: str) -> str:
    text = _text(value, name).casefold()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{name} must be a SHA-256 hexadecimal digest")
    return text


def _canonical_protocol(payload: Mapping[str, Any]) -> dict[str, Any]:
    protocol = _mapping(payload, "protocol", _PROTOCOL_FIELDS)
    cohort = _mapping(protocol["cohort"], "cohort", _COHORT_FIELDS)
    selection = _mapping(protocol["selection"], "selection", _SELECTION_FIELDS)
    endpoints = _mapping(protocol["endpoints"], "endpoints", _ENDPOINT_FIELDS)
    raw_analysis = protocol["analysis"]
    reference_score = None
    if isinstance(raw_analysis, Mapping) and "reference_score" in raw_analysis:
        raw_analysis = dict(raw_analysis)
        reference_score = _text(raw_analysis.pop("reference_score"), "analysis.reference_score")
    analysis = _mapping(raw_analysis, "analysis", _ANALYSIS_FIELDS)
    operations = _mapping(protocol["operations"], "operations", _OPERATIONS_FIELDS)
    governance = _mapping(protocol["governance"], "governance", _GOVERNANCE_FIELDS)

    opens_at = _timestamp(cohort["opens_at"], "cohort.opens_at")
    closes_at = _timestamp(cohort["closes_at"], "cohort.closes_at")
    matures_at = _timestamp(cohort["matures_at"], "cohort.matures_at")
    if not datetime.fromisoformat(opens_at) < datetime.fromisoformat(closes_at):
        raise ValueError("cohort.opens_at must precede cohort.closes_at")
    if datetime.fromisoformat(matures_at) < datetime.fromisoformat(closes_at):
        raise ValueError("cohort.matures_at must not precede cohort.closes_at")

    confidence = _number(analysis["confidence_level"], "analysis.confidence_level")
    if not 0.0 < confidence < 1.0:
        raise ValueError("analysis.confidence_level must be within (0, 1)")
    missing_policy = _text(
        analysis["missing_outcome_policy"], "analysis.missing_outcome_policy"
    ).casefold()
    if missing_policy not in {"count_as_negative", "exclude_and_report", "censor"}:
        raise ValueError(
            "analysis.missing_outcome_policy must be count_as_negative, exclude_and_report, "
            "or censor"
        )
    eligibility_policy = _text(
        selection["eligibility_policy"], "selection.eligibility_policy"
    ).casefold()
    if eligibility_policy not in {"triage", "gate-clear"}:
        raise ValueError("selection.eligibility_policy must be triage or gate-clear")
    principal_policy = _text(
        governance["principal_policy"], "governance.principal_policy"
    ).casefold()
    if principal_policy not in {"local_named_research", "authenticated_external"}:
        raise ValueError(
            "governance.principal_policy must be local_named_research or authenticated_external"
        )
    minimum_injection_recovery = _number(
        analysis["minimum_injection_recovery"], "analysis.minimum_injection_recovery"
    )
    if not 0.0 <= minimum_injection_recovery <= 1.0:
        raise ValueError("analysis.minimum_injection_recovery must be within [0, 1]")
    injection_amplitude = _number(
        analysis["injection_amplitude_sigma"], "analysis.injection_amplitude_sigma"
    )
    if injection_amplitude <= 0:
        raise ValueError("analysis.injection_amplitude_sigma must be positive")

    return {
        "study_id": _text(protocol["study_id"], "study_id"),
        "title": _text(protocol["title"], "title"),
        "scientific_question": _text(protocol["scientific_question"], "scientific_question"),
        "hypotheses": _texts(protocol["hypotheses"], "hypotheses"),
        "cohort": {
            "opens_at": opens_at,
            "closes_at": closes_at,
            "matures_at": matures_at,
            "population": _text(cohort["population"], "cohort.population"),
            "inclusion_criteria": _texts(cohort["inclusion_criteria"], "cohort.inclusion_criteria"),
            "exclusion_criteria": _texts(
                cohort["exclusion_criteria"],
                "cohort.exclusion_criteria",
                allow_empty=True,
            ),
        },
        "selection": {
            "pipeline_version": _text(selection["pipeline_version"], "selection.pipeline_version"),
            "configuration_digest": _digest(
                selection["configuration_digest"], "selection.configuration_digest"
            ),
            "eligibility_policy": eligibility_policy,
            "review_budget": _integer(
                selection["review_budget"], "selection.review_budget", minimum=1
            ),
            "audit_slots": _integer(selection["audit_slots"], "selection.audit_slots", minimum=0),
        },
        "endpoints": {
            "primary": _text(endpoints["primary"], "endpoints.primary"),
            "secondary": _texts(endpoints["secondary"], "endpoints.secondary", allow_empty=True),
        },
        "analysis": {
            **({"reference_score": reference_score} if reference_score is not None else {}),
            "primary_metric": _text(analysis["primary_metric"], "analysis.primary_metric"),
            "comparison": _text(analysis["comparison"], "analysis.comparison"),
            "minimum_useful_effect": _number(
                analysis["minimum_useful_effect"], "analysis.minimum_useful_effect"
            ),
            "confidence_level": confidence,
            "bootstrap_repeats": _integer(
                analysis["bootstrap_repeats"], "analysis.bootstrap_repeats", minimum=100
            ),
            "random_seed": _integer(analysis["random_seed"], "analysis.random_seed", minimum=0),
            "subgroup_fields": _texts(
                analysis["subgroup_fields"], "analysis.subgroup_fields", allow_empty=True
            ),
            "missing_outcome_policy": missing_policy,
            "minimum_injection_recovery": minimum_injection_recovery,
            "injection_amplitude_sigma": injection_amplitude,
        },
        "operations": {
            "required_services": _texts(
                operations["required_services"], "operations.required_services"
            ),
            "minimum_broker_snapshots": _integer(
                operations["minimum_broker_snapshots"],
                "operations.minimum_broker_snapshots",
                minimum=1,
            ),
            "require_image_evidence": (
                operations["require_image_evidence"]
                if isinstance(operations["require_image_evidence"], bool)
                else _raise_boolean("operations.require_image_evidence")
            ),
            "required_recovery_drills": _integer(
                operations["required_recovery_drills"],
                "operations.required_recovery_drills",
                minimum=1,
            ),
            "maximum_schema_drifts": _integer(
                operations["maximum_schema_drifts"],
                "operations.maximum_schema_drifts",
                minimum=0,
            ),
        },
        "governance": {
            "protocol_owner": _text(governance["protocol_owner"], "governance.protocol_owner"),
            "statistics_reviewer": _text(
                governance["statistics_reviewer"], "governance.statistics_reviewer"
            ),
            "independent_signoffs_required": _integer(
                governance["independent_signoffs_required"],
                "governance.independent_signoffs_required",
                minimum=1,
            ),
            "principal_policy": principal_policy,
            "required_signoff_areas": _texts(
                governance["required_signoff_areas"],
                "governance.required_signoff_areas",
            ),
            "trusted_assertion_key_ids": [
                _digest(value, "governance.trusted_assertion_key_ids item")
                for value in _texts(
                    governance["trusted_assertion_key_ids"],
                    "governance.trusted_assertion_key_ids",
                )
            ],
        },
    }


def _raise_boolean(name: str) -> bool:
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True, slots=True)
class Preregistration:
    """A frozen protocol whose digest excludes only the freeze timestamp."""

    protocol: Mapping[str, Any]
    protocol_digest: str
    frozen_at: str
    schema: str = PREREGISTRATION_SCHEMA

    @classmethod
    def from_protocol(
        cls,
        protocol: Mapping[str, Any],
        *,
        frozen_at: str | None = None,
    ) -> Preregistration:
        canonical = _canonical_protocol(protocol)
        timestamp = _timestamp(frozen_at or utc_now(), "frozen_at")
        if datetime.fromisoformat(timestamp) > datetime.fromisoformat(
            canonical["cohort"]["opens_at"]
        ):
            raise ValueError("preregistration must be frozen before cohort opens_at")
        return cls(
            protocol=canonical,
            protocol_digest=digest_value(canonical),
            frozen_at=timestamp,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Preregistration:
        allowed = {"schema", "protocol", "protocol_digest", "frozen_at"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"preregistration has unknown fields: {unknown}")
        if payload.get("schema") != PREREGISTRATION_SCHEMA:
            raise ValueError(f"preregistration schema must be {PREREGISTRATION_SCHEMA!r}")
        protocol = payload.get("protocol")
        if not isinstance(protocol, Mapping):
            raise ValueError("preregistration protocol must be an object")
        result = cls.from_protocol(
            protocol,
            frozen_at=_text(payload.get("frozen_at"), "frozen_at"),
        )
        stored_digest = _digest(payload.get("protocol_digest"), "protocol_digest")
        if stored_digest != result.protocol_digest:
            raise ValueError("preregistration protocol digest does not match its content")
        return result

    @property
    def study_id(self) -> str:
        return str(self.protocol["study_id"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "protocol": deepcopy(dict(self.protocol)),
            "protocol_digest": self.protocol_digest,
            "frozen_at": self.frozen_at,
        }

    def validated(self) -> Preregistration:
        """Return an independent canonical copy, rejecting in-memory digest drift."""
        return self.from_dict(self.to_dict())


def freeze_preregistration(
    source: str | Path,
    destination: str | Path,
    *,
    frozen_at: str | None = None,
) -> Preregistration:
    """Validate a protocol JSON file and publish a no-clobber frozen record."""

    source_path = Path(source).expanduser().resolve()
    try:
        raw = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read preregistration protocol {source_path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("preregistration protocol input must be a JSON object")
    preregistration = Preregistration.from_protocol(raw, frozen_at=frozen_at)
    content = (stable_json(preregistration.to_dict()) + "\n").encode("utf-8")
    atomic_create_binary(
        Path(destination).expanduser().resolve(), lambda handle: handle.write(content)
    )
    return preregistration


def load_preregistration(path: str | Path) -> Preregistration:
    """Load and authenticate a frozen preregistration by its embedded digest."""

    source = Path(path).expanduser().resolve()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read preregistration {source}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("preregistration must contain a JSON object")
    return Preregistration.from_dict(raw)


__all__ = [
    "PREREGISTRATION_SCHEMA",
    "Preregistration",
    "freeze_preregistration",
    "load_preregistration",
]
