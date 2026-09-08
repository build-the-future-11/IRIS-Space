"""Canonical context evidence produced alongside external verification checks.

The catalogue labels that trigger manual review are scientific evidence, not UI
decoration.  Keeping their validation and serialization in one dependency-light
module lets the verifier, pipeline, immutable-record checker, and reporting gate
agree on the exact bytes being reviewed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

VERIFICATION_CONTEXT_FIELDS = frozenset({"simbad", "skybot_epochs"})


def _string_sequence(value: Any, *, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"verification context {field} must be an array of strings")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"verification context {field} must be an array of strings")
    normalized = tuple(item.strip() for item in value)
    if any(not item for item in normalized):
        raise ValueError(f"verification context {field} cannot contain empty strings")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"verification context {field} cannot contain duplicates")
    return normalized


def format_skybot_epochs(values: Sequence[float]) -> tuple[str, ...]:
    """Return the canonical, stable serialization for SkyBoT reference epochs."""

    epochs: list[float] = []
    for value in values:
        if isinstance(value, bool):
            raise ValueError("SkyBoT reference epochs must be finite and non-negative")
        try:
            epoch = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("SkyBoT reference epochs must be finite and non-negative") from exc
        if not math.isfinite(epoch) or epoch < 0:
            raise ValueError("SkyBoT reference epochs must be finite and non-negative")
        epochs.append(0.0 if epoch == 0.0 else epoch)
    if len(set(epochs)) != len(epochs):
        raise ValueError("SkyBoT reference epochs cannot contain duplicates")
    serialized = tuple(f"{epoch:.8f}" for epoch in sorted(epochs))
    if len(set(serialized)) != len(serialized):
        raise ValueError("SkyBoT reference epochs collide at the canonical eight-decimal precision")
    return serialized


def canonical_verification_context(
    context: Mapping[str, Any] | None,
    *,
    manual_review_required: bool,
    expected_skybot_reference_mjds: Sequence[float] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Validate and canonicalize one ``siderea.verification.v1`` context object.

    When no serialized verifier output is supplied, an empty SIMBAD context and
    the independently derived SkyBoT epochs form the canonical local default.
    A manual-review flag is never accepted without the actual non-empty SIMBAD
    labels that caused it.
    """

    if not isinstance(manual_review_required, bool):
        raise TypeError("manual_review_required must be boolean")
    expected_epochs = (
        format_skybot_epochs(expected_skybot_reference_mjds)
        if expected_skybot_reference_mjds is not None
        else ()
    )
    if context is None:
        if manual_review_required:
            raise ValueError("manual_review_required needs non-empty SIMBAD context evidence")
        return {"simbad": (), "skybot_epochs": expected_epochs}
    if not isinstance(context, Mapping):
        raise ValueError("verification context must be a JSON object")
    if any(not isinstance(key, str) for key in context):
        raise ValueError("verification context field names must be strings")
    missing = sorted(VERIFICATION_CONTEXT_FIELDS - set(context))
    unknown = sorted(set(context) - VERIFICATION_CONTEXT_FIELDS)
    if missing:
        raise ValueError(f"verification context is missing required fields: {missing}")
    if unknown:
        raise ValueError(f"verification context has unknown fields: {unknown}")

    simbad = _string_sequence(context["simbad"], field="simbad")
    raw_epochs = _string_sequence(context["skybot_epochs"], field="skybot_epochs")
    parsed_epochs: list[float] = []
    for raw_epoch in raw_epochs:
        try:
            epoch = float(raw_epoch)
        except ValueError as exc:
            raise ValueError(
                "verification context skybot_epochs must contain canonical finite epochs"
            ) from exc
        if not math.isfinite(epoch) or epoch < 0 or raw_epoch != f"{epoch:.8f}":
            raise ValueError(
                "verification context skybot_epochs must contain canonical finite epochs"
            )
        parsed_epochs.append(epoch)
    canonical_epochs = format_skybot_epochs(parsed_epochs)
    if raw_epochs != canonical_epochs:
        raise ValueError("verification context skybot_epochs must be sorted and unique")
    if expected_skybot_reference_mjds is not None and canonical_epochs != expected_epochs:
        raise ValueError(
            "verification context SkyBoT epochs differ from the candidate observations"
        )
    if manual_review_required and not simbad:
        raise ValueError("manual_review_required needs non-empty SIMBAD context evidence")
    return {"simbad": simbad, "skybot_epochs": canonical_epochs}


def serialized_verification_context(
    context: Mapping[str, Any] | None,
    *,
    manual_review_required: bool,
    expected_skybot_reference_mjds: Sequence[float] | None = None,
) -> dict[str, list[str]]:
    """Return the canonical context in its JSON scientific-record shape."""

    canonical = canonical_verification_context(
        context,
        manual_review_required=manual_review_required,
        expected_skybot_reference_mjds=expected_skybot_reference_mjds,
    )
    return {name: list(values) for name, values in canonical.items()}


__all__ = [
    "VERIFICATION_CONTEXT_FIELDS",
    "canonical_verification_context",
    "format_skybot_epochs",
    "serialized_verification_context",
]
