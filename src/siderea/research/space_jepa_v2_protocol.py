"""Frozen protocol contract for the Space JEPA 2 research path."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from siderea.atomic import atomic_create_binary
from siderea.provenance import digest_value, stable_json, utc_now

SPACE_JEPA_V2_PROTOCOL_SCHEMA = "siderea.space_jepa_v2_protocol.v1"
SPACE_JEPA_V2_FROZEN_SCHEMA = "siderea.space_jepa_v2_protocol_frozen.v1"

_REQUIRED_MODELS = frozenset(
    {
        "heuristic",
        "template",
        "persistence",
        "linear",
        "quadratic",
        "gru",
        "real_transformer",
        "real_jepa",
        "quaternion_jepa",
        "quaternion_flow_jepa",
        "aqpm_no_memory",
        "aqpm_full",
        "aqpm_no_physics",
        "kernel_residual",
    }
)
_REQUIRED_CONTROLS = frozenset(
    {
        "memory_off",
        "gate_closed",
        "gate_open",
        "uniform_metric",
        "shuffled_residuals",
        "shuffled_keys",
        "wrong_population",
        "source_exclusion_attack",
        "kernel_residual",
    }
)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return dict(value)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        qualifier = "positive and " if positive else ""
        raise ValueError(f"{name} must be {qualifier}finite")
    return result


def _integers(value: Any, name: str, *, minimum: int = 0) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be an array of integers")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item < minimum:
            raise ValueError(f"{name} values must be integers >= {minimum}")
        result.append(item)
    if not result or len(result) != len(set(result)):
        raise ValueError(f"{name} must be non-empty and contain unique values")
    return tuple(result)


def _numbers(value: Any, name: str, *, positive: bool = False) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be an array of numbers")
    result = tuple(_number(item, f"{name} item", positive=positive) for item in value)
    if not result or len(result) != len(set(result)):
        raise ValueError(f"{name} must be non-empty and contain unique values")
    return result


def _texts(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be an array of strings")
    result = tuple(_text(item, f"{name} item") for item in value)
    if not result or len(result) != len(set(result)):
        raise ValueError(f"{name} must be non-empty and contain unique values")
    return result


@dataclass(frozen=True)
class SpaceJEPAV2Protocol:
    """Canonical validated protocol plus its content digest."""

    payload: Mapping[str, Any]
    protocol_digest: str

    @property
    def study_id(self) -> str:
        return str(self.payload["study_id"])

    @property
    def horizons_days(self) -> tuple[float, ...]:
        return tuple(float(value) for value in self.payload["horizons_days"])

    @property
    def seeds(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.payload["seeds"])


def validate_space_jepa_v2_protocol(payload: Mapping[str, Any]) -> SpaceJEPAV2Protocol:
    """Validate and canonicalize the complete prospective experiment contract."""

    raw = dict(payload)
    expected = {
        "schema",
        "study_id",
        "title",
        "system",
        "engine",
        "horizons_days",
        "seeds",
        "split",
        "review",
        "model",
        "models",
        "memory_controls",
        "stress_tests",
        "statistics",
        "promotion",
        "failure_policy",
    }
    missing = sorted(expected - set(raw))
    unknown = sorted(set(raw) - expected)
    if missing or unknown:
        raise ValueError(f"protocol fields differ; missing={missing}, unknown={unknown}")
    if raw["schema"] != SPACE_JEPA_V2_PROTOCOL_SCHEMA:
        raise ValueError(f"protocol schema must be {SPACE_JEPA_V2_PROTOCOL_SCHEMA!r}")

    horizons = _numbers(raw["horizons_days"], "horizons_days", positive=True)
    if tuple(sorted(horizons)) != horizons:
        raise ValueError("horizons_days must be strictly increasing")
    seeds = _integers(raw["seeds"], "seeds")

    split = _mapping(raw["split"], "split")
    if set(split) != {
        "unit",
        "ordering",
        "train_fraction",
        "validation_fraction",
        "test_fraction",
        "population_b_policy",
    }:
        raise ValueError("split has missing or unknown fields")
    fractions = tuple(
        _number(split[name], f"split.{name}", positive=True)
        for name in ("train_fraction", "validation_fraction", "test_fraction")
    )
    if not math.isclose(sum(fractions), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("split fractions must sum to one")

    review = _mapping(raw["review"], "review")
    if set(review) != {"primary_fraction", "minimum", "maximum", "secondary", "audit_slots"}:
        raise ValueError("review has missing or unknown fields")
    primary_fraction = _number(review["primary_fraction"], "review.primary_fraction", positive=True)
    if primary_fraction > 1.0:
        raise ValueError("review.primary_fraction must not exceed one")
    review_minimum = _integers([review["minimum"]], "review.minimum", minimum=1)[0]
    review_maximum = _integers([review["maximum"]], "review.maximum", minimum=1)[0]
    if review_minimum > review_maximum:
        raise ValueError("review.minimum must not exceed review.maximum")
    secondary = _integers(review["secondary"], "review.secondary", minimum=1)
    audit_slots = _integers([review["audit_slots"]], "review.audit_slots", minimum=1)[0]

    model = _mapping(raw["model"], "model")
    required_model_fields = {
        "quaternion_width",
        "encoder_blocks",
        "attention_heads",
        "predictor_blocks",
        "dropout",
        "ema_start",
        "ema_end",
        "learning_rate",
        "weight_decay",
        "gradient_clip",
    }
    if set(model) != required_model_fields:
        raise ValueError("model has missing or unknown fields")
    for field in ("quaternion_width", "encoder_blocks", "attention_heads", "predictor_blocks"):
        _integers([model[field]], f"model.{field}", minimum=1)
    if int(model["quaternion_width"]) % int(model["attention_heads"]):
        raise ValueError("model.quaternion_width must be divisible by attention_heads")
    dropout = _number(model["dropout"], "model.dropout")
    if not 0.0 <= dropout < 1.0:
        raise ValueError("model.dropout must be within [0, 1)")
    ema_start = _number(model["ema_start"], "model.ema_start")
    ema_end = _number(model["ema_end"], "model.ema_end")
    if not 0.0 < ema_start <= ema_end < 1.0:
        raise ValueError("EMA values must satisfy 0 < start <= end < 1")
    for field in ("learning_rate", "weight_decay", "gradient_clip"):
        _number(model[field], f"model.{field}", positive=True)

    models = _texts(raw["models"], "models")
    missing_models = sorted(_REQUIRED_MODELS - set(models))
    if missing_models:
        raise ValueError(f"protocol is missing required models: {missing_models}")
    controls = _texts(raw["memory_controls"], "memory_controls")
    missing_controls = sorted(_REQUIRED_CONTROLS - set(controls))
    if missing_controls:
        raise ValueError(f"protocol is missing memory controls: {missing_controls}")

    stress_tests = _mapping(raw["stress_tests"], "stress_tests")
    if set(stress_tests) != {
        "primary_ood",
        "intervention",
        "survey_fidelity",
        "zero_shot",
        "limited_example",
    }:
        raise ValueError("stress_tests has missing or unknown fields")
    survey_fidelity = _texts(stress_tests["survey_fidelity"], "stress_tests.survey_fidelity")
    if set(survey_fidelity) != {"filter", "cadence", "depth"}:
        raise ValueError("stress_tests.survey_fidelity must contain filter, cadence and depth")
    for field in ("zero_shot", "limited_example"):
        if not isinstance(stress_tests[field], bool):
            raise ValueError(f"stress_tests.{field} must be boolean")

    statistics = _mapping(raw["statistics"], "statistics")
    if set(statistics) != {"bootstrap_repeats", "bootstrap_seed", "confidence_level"}:
        raise ValueError("statistics has missing or unknown fields")
    bootstrap_repeats = _integers(
        [statistics["bootstrap_repeats"]], "statistics.bootstrap_repeats", minimum=100
    )[0]
    bootstrap_seed = _integers([statistics["bootstrap_seed"]], "statistics.bootstrap_seed")[0]
    confidence = _number(statistics["confidence_level"], "statistics.confidence_level")
    if not 0.0 < confidence < 1.0:
        raise ValueError("statistics.confidence_level must be within (0, 1)")

    promotion = _mapping(raw["promotion"], "promotion")
    required_promotion = {
        "component_relative_improvement",
        "calibration_max_worsening",
        "ranking_absolute_recall_gain",
        "workload_reduction",
        "recall_noninferiority_margin",
        "rare_family_max_drop",
    }
    if set(promotion) != required_promotion:
        raise ValueError("promotion has missing or unknown fields")
    canonical_promotion = {
        name: _number(value, f"promotion.{name}") for name, value in promotion.items()
    }
    if any(abs(value) > 1.0 for value in canonical_promotion.values()):
        raise ValueError("promotion thresholds must lie within [-1, 1]")

    failure_policy = _texts(raw["failure_policy"], "failure_policy")
    canonical: dict[str, Any] = {
        "schema": SPACE_JEPA_V2_PROTOCOL_SCHEMA,
        "study_id": _text(raw["study_id"], "study_id"),
        "title": _text(raw["title"], "title"),
        "system": _text(raw["system"], "system"),
        "engine": _text(raw["engine"], "engine"),
        "horizons_days": list(horizons),
        "seeds": list(seeds),
        "split": {
            "unit": _text(split["unit"], "split.unit"),
            "ordering": _text(split["ordering"], "split.ordering"),
            "train_fraction": fractions[0],
            "validation_fraction": fractions[1],
            "test_fraction": fractions[2],
            "population_b_policy": _text(split["population_b_policy"], "split.population_b_policy"),
        },
        "review": {
            "primary_fraction": primary_fraction,
            "minimum": review_minimum,
            "maximum": review_maximum,
            "secondary": list(secondary),
            "audit_slots": audit_slots,
        },
        "model": {
            **{
                name: int(model[name])
                for name in (
                    "quaternion_width",
                    "encoder_blocks",
                    "attention_heads",
                    "predictor_blocks",
                )
            },
            "dropout": dropout,
            "ema_start": ema_start,
            "ema_end": ema_end,
            "learning_rate": float(model["learning_rate"]),
            "weight_decay": float(model["weight_decay"]),
            "gradient_clip": float(model["gradient_clip"]),
        },
        "models": list(models),
        "memory_controls": list(controls),
        "stress_tests": {
            "primary_ood": _text(stress_tests["primary_ood"], "stress_tests.primary_ood"),
            "intervention": _text(stress_tests["intervention"], "stress_tests.intervention"),
            "survey_fidelity": list(survey_fidelity),
            "zero_shot": stress_tests["zero_shot"],
            "limited_example": stress_tests["limited_example"],
        },
        "statistics": {
            "bootstrap_repeats": bootstrap_repeats,
            "bootstrap_seed": bootstrap_seed,
            "confidence_level": confidence,
        },
        "promotion": canonical_promotion,
        "failure_policy": list(failure_policy),
    }
    return SpaceJEPAV2Protocol(canonical, digest_value(canonical))


def load_space_jepa_v2_protocol(path: str | Path) -> SpaceJEPAV2Protocol:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read Space JEPA 2 protocol {source}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("Space JEPA 2 protocol must contain a JSON object")
    if raw.get("schema") == SPACE_JEPA_V2_FROZEN_SCHEMA:
        protocol = raw.get("protocol")
        if not isinstance(protocol, Mapping):
            raise ValueError("frozen Space JEPA 2 protocol lacks protocol object")
        validated = validate_space_jepa_v2_protocol(protocol)
        if raw.get("protocol_digest") != validated.protocol_digest:
            raise ValueError("frozen Space JEPA 2 protocol digest differs")
        return validated
    return validate_space_jepa_v2_protocol(raw)


def freeze_space_jepa_v2_protocol(source: str | Path, output: str | Path) -> SpaceJEPAV2Protocol:
    """Validate and publish a new immutable protocol envelope."""

    protocol = load_space_jepa_v2_protocol(source)
    envelope = {
        "schema": SPACE_JEPA_V2_FROZEN_SCHEMA,
        "frozen_at": utc_now(),
        "protocol_digest": protocol.protocol_digest,
        "protocol": dict(protocol.payload),
    }
    encoded = (stable_json(envelope) + "\n").encode("utf-8")

    def _write(handle: BinaryIO) -> None:
        handle.write(encoded)

    atomic_create_binary(output, _write)
    return protocol


__all__ = [
    "SPACE_JEPA_V2_FROZEN_SCHEMA",
    "SPACE_JEPA_V2_PROTOCOL_SCHEMA",
    "SpaceJEPAV2Protocol",
    "freeze_space_jepa_v2_protocol",
    "load_space_jepa_v2_protocol",
    "validate_space_jepa_v2_protocol",
]
