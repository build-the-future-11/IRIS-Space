"""Fail-closed phase receipts for the prospective robust-search v2 study.

The v2 protocol already separates development, calibration, locked evaluation,
and generalization data.  This module makes that separation operational: every
phase transition is represented by a deterministic receipt that binds the exact
artifacts produced so far and, after the first phase, the exact predecessor
receipt.  A changed artifact, skipped phase, overwritten receipt, or path outside
the study root fails closed.

The module does not compute a search statistic, threshold, recovery fraction, or
false-alarm rate.  It is control-plane infrastructure intended to be called by
the eventual runner before it enters the next scientific phase.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from siderea.provenance import stable_json

PHASE_ORDER = (
    "development_complete",
    "selection_frozen",
    "calibration_complete",
    "threshold_frozen",
    "locked_evaluation_complete",
    "generalization_complete",
)
_RECEIPT_SCHEMA = "siderea.robust_search_phase_receipt.v2"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_file(root: Path, path: Path) -> tuple[Path, str]:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"artifact is outside the study root: {path}") from exc
    if not resolved.is_file():
        raise FileNotFoundError(f"required phase artifact does not exist: {path}")
    return resolved, relative.as_posix()


def _phase_index(phase: str) -> int:
    try:
        return PHASE_ORDER.index(phase)
    except ValueError as exc:
        raise ValueError(f"unknown robust-search phase: {phase}") from exc


def build_phase_receipt(
    *,
    phase: str,
    study_root: Path,
    artifacts: Sequence[Path],
    previous_receipt: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic phase receipt without writing it.

    ``artifacts`` must be non-empty, unique files beneath ``study_root``.  Every
    phase after ``development_complete`` must bind the immediately preceding
    receipt, which is itself verified recursively before its digest is accepted.
    """

    phase_index = _phase_index(phase)
    if not artifacts:
        raise ValueError("a phase receipt must bind at least one artifact")

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for artifact in artifacts:
        resolved, relative = _relative_file(study_root, artifact)
        if relative in seen:
            raise ValueError(f"duplicate phase artifact: {relative}")
        seen.add(relative)
        rows.append({"path": relative, "sha256": _sha256_file(resolved)})
    rows.sort(key=lambda row: row["path"])

    previous: dict[str, str] | None = None
    if phase_index == 0:
        if previous_receipt is not None:
            raise ValueError("development_complete must not bind a predecessor receipt")
    else:
        if previous_receipt is None:
            raise ValueError(f"{phase} requires the immediately preceding phase receipt")
        previous_resolved, previous_relative = _relative_file(study_root, previous_receipt)
        previous_payload = verify_phase_receipt(previous_resolved, study_root=study_root)
        expected_phase = PHASE_ORDER[phase_index - 1]
        if previous_payload["phase"] != expected_phase:
            raise RuntimeError(
                f"{phase} requires predecessor {expected_phase}, got {previous_payload['phase']}"
            )
        previous = {
            "path": previous_relative,
            "sha256": _sha256_file(previous_resolved),
        }

    return {
        "schema": _RECEIPT_SCHEMA,
        "phase": phase,
        "previous_receipt": previous,
        "artifacts": rows,
    }


def freeze_phase_receipt(
    destination: Path,
    *,
    phase: str,
    study_root: Path,
    artifacts: Sequence[Path],
    previous_receipt: Path | None = None,
) -> str:
    """Write one immutable phase receipt and return its SHA-256 digest."""

    resolved_root = study_root.resolve()
    resolved_destination = destination.resolve()
    try:
        resolved_destination.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("phase receipt destination must be inside the study root") from exc
    if destination.exists():
        raise FileExistsError("phase receipt already exists; preserve the frozen artifact")

    payload = build_phase_receipt(
        phase=phase,
        study_root=study_root,
        artifacts=artifacts,
        previous_receipt=previous_receipt,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = (stable_json(payload) + "\n").encode("utf-8")
    destination.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def verify_phase_receipt(path: Path, *, study_root: Path) -> dict[str, Any]:
    """Verify one receipt, its bound artifacts, and its predecessor chain."""

    return _verify_phase_receipt(path, study_root=study_root, visited=set())


def _verify_phase_receipt(
    path: Path,
    *,
    study_root: Path,
    visited: set[Path],
) -> dict[str, Any]:
    resolved, _ = _relative_file(study_root, path)
    if resolved in visited:
        raise RuntimeError("phase receipt chain contains a cycle")
    visited.add(resolved)

    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid phase receipt JSON: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != _RECEIPT_SCHEMA:
        raise RuntimeError("unexpected robust-search phase receipt schema")

    phase = payload.get("phase")
    if not isinstance(phase, str):
        raise RuntimeError("phase receipt is missing a string phase")
    phase_index = _phase_index(phase)

    rows = payload.get("artifacts")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("phase receipt must bind a non-empty artifact list")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("phase receipt artifact row must be an object")
        relative = row.get("path")
        expected = row.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise RuntimeError("phase receipt artifact row is malformed")
        if relative in seen:
            raise RuntimeError(f"phase receipt repeats artifact {relative}")
        seen.add(relative)
        artifact = study_root / relative
        _, _ = _relative_file(study_root, artifact)
        actual = _sha256_file(artifact)
        if actual != expected:
            raise RuntimeError(
                f"phase artifact drifted after receipt freeze: {relative}; "
                f"expected {expected}, got {actual}"
            )

    previous = payload.get("previous_receipt")
    if phase_index == 0:
        if previous is not None:
            raise RuntimeError("development_complete receipt must not have a predecessor")
    else:
        if not isinstance(previous, dict):
            raise RuntimeError(f"{phase} receipt is missing its predecessor")
        previous_path = previous.get("path")
        previous_digest = previous.get("sha256")
        if not isinstance(previous_path, str) or not isinstance(previous_digest, str):
            raise RuntimeError("phase predecessor record is malformed")
        predecessor = study_root / previous_path
        predecessor_resolved, _ = _relative_file(study_root, predecessor)
        actual_previous_digest = _sha256_file(predecessor_resolved)
        if actual_previous_digest != previous_digest:
            raise RuntimeError("predecessor phase receipt drifted after it was bound")
        previous_payload = _verify_phase_receipt(
            predecessor_resolved,
            study_root=study_root,
            visited=visited,
        )
        expected_phase = PHASE_ORDER[phase_index - 1]
        if previous_payload["phase"] != expected_phase:
            raise RuntimeError(
                f"{phase} requires predecessor {expected_phase}, got {previous_payload['phase']}"
            )

    visited.remove(resolved)
    result: dict[str, Any] = payload
    return result


__all__ = [
    "PHASE_ORDER",
    "build_phase_receipt",
    "freeze_phase_receipt",
    "verify_phase_receipt",
]
