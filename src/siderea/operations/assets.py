"""Content-bound image-triplet and forced-photometry evidence bundles."""

from __future__ import annotations

import hmac
import json
import math
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from siderea.atomic import atomic_create_binary, atomic_write_text, fsync_directory
from siderea.host import angular_separation_arcsec
from siderea.integrity import verify_candidate_record
from siderea.provenance import digest_value, stable_json

EVIDENCE_ASSET_BUNDLE_SCHEMA = "siderea.evidence_asset_bundle.v1"
REQUIRED_ASSET_ROLES = frozenset(
    {"science_image", "reference_image", "difference_image", "forced_photometry"}
)
_FORCED_CALIBRATION_FIELDS = frozenset(
    {
        "flux_unit",
        "calibration_reference",
        "extraction_method",
        "position_ra_deg",
        "position_dec_deg",
    }
)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _timestamp(value: Any, name: str) -> str:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")
    return parsed.isoformat()


@dataclass(frozen=True, slots=True)
class EvidenceAssetSpec:
    role: str
    path: Path
    media_type: str
    survey: str
    instrument: str
    observation_time: str
    calibration: Mapping[str, Any]

    def validated(self) -> EvidenceAssetSpec:
        role = _text(self.role, "asset role").casefold()
        if role not in REQUIRED_ASSET_ROLES:
            raise ValueError(f"unsupported evidence asset role: {role}")
        source = Path(self.path).expanduser().resolve()
        if not source.is_file():
            raise ValueError(f"evidence asset does not exist: {source}")
        if not isinstance(self.calibration, Mapping):
            raise ValueError("asset calibration must be a JSON object")
        calibration = dict(self.calibration)
        stable_json(calibration)
        if role == "forced_photometry" and set(calibration) != _FORCED_CALIBRATION_FIELDS:
            raise ValueError(
                "forced-photometry calibration must contain exactly "
                f"{sorted(_FORCED_CALIBRATION_FIELDS)}"
            )
        if role == "forced_photometry":
            for name in ("flux_unit", "calibration_reference", "extraction_method"):
                _text(calibration[name], name)
            for name, lower, upper in (("position_ra_deg", 0, 360), ("position_dec_deg", -90, 90)):
                value = calibration[name]
                if (
                    type(value) not in {int, float}
                    or not math.isfinite(value)
                    or not lower <= value <= upper
                    or name == "position_ra_deg"
                    and value == 360
                ):
                    raise ValueError(f"{name} is outside its coordinate range")
        return EvidenceAssetSpec(
            role=role,
            path=source,
            media_type=_text(self.media_type, "asset media_type").casefold(),
            survey=_text(self.survey, "asset survey").casefold(),
            instrument=_text(self.instrument, "asset instrument"),
            observation_time=_timestamp(self.observation_time, "asset observation_time"),
            calibration=calibration,
        )


def _copy_exclusive(source: Path, destination: Path) -> None:
    def writer(handle: Any) -> None:
        with source.open("rb") as source_handle:
            shutil.copyfileobj(source_handle, handle, length=1024 * 1024)

    atomic_create_binary(destination, writer)


def create_evidence_asset_bundle(
    destination: str | Path,
    *,
    candidate: Mapping[str, Any],
    assets: Sequence[EvidenceAssetSpec],
) -> dict[str, Any]:
    """Archive a complete image triplet and forced-photometry product."""

    pipeline_version = _text(candidate.get("pipeline_version"), "candidate pipeline_version")
    candidate_record_digest = verify_candidate_record(candidate, pipeline_version=pipeline_version)
    if isinstance(assets, (str, bytes)) or not isinstance(assets, Sequence):
        raise TypeError("assets must be a sequence of EvidenceAssetSpec values")
    validated = [asset.validated() for asset in assets]
    position = candidate.get("position")
    if not isinstance(position, Mapping):
        raise ValueError("candidate position is required for asset association")
    for asset in validated:
        if (
            asset.role == "forced_photometry"
            and angular_separation_arcsec(
                position["ra_deg"],
                position["dec_deg"],
                asset.calibration["position_ra_deg"],
                asset.calibration["position_dec_deg"],
            )
            > 2.0
        ):
            raise ValueError(
                "forced-photometry position differs from candidate by more than 2 arcsec"
            )
    roles = [asset.role for asset in validated]
    if set(roles) != REQUIRED_ASSET_ROLES or len(roles) != len(REQUIRED_ASSET_ROLES):
        raise ValueError(
            "evidence bundle requires exactly one science, reference, difference, "
            "and forced-photometry asset"
        )
    target = Path(destination).expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"evidence bundle destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.{uuid4().hex}.tmp"
    staging.mkdir(mode=0o700)
    try:
        assets_dir = staging / "assets"
        assets_dir.mkdir()
        records: list[dict[str, Any]] = []
        for asset in sorted(validated, key=lambda item: item.role):
            suffix = asset.path.suffix.casefold()
            stored_name = f"{asset.role}{suffix if suffix else '.bin'}"
            stored_path = assets_dir / stored_name
            _copy_exclusive(asset.path, stored_path)
            records.append(
                {
                    "role": asset.role,
                    "path": f"assets/{stored_name}",
                    "media_type": asset.media_type,
                    "survey": asset.survey,
                    "instrument": asset.instrument,
                    "observation_time": asset.observation_time,
                    "calibration": dict(asset.calibration),
                    "sha256": sha256(stored_path.read_bytes()).hexdigest(),
                    "size_bytes": stored_path.stat().st_size,
                }
            )
        basis = {
            "schema": EVIDENCE_ASSET_BUNDLE_SCHEMA,
            "candidate_id": _text(candidate.get("candidate_id"), "candidate_id"),
            "candidate_version": _text(candidate.get("candidate_version"), "candidate_version"),
            "candidate_record_digest": candidate_record_digest,
            "candidate_run_binding_digest": _text(
                candidate.get("candidate_run_binding_digest"),
                "candidate_run_binding_digest",
            ),
            "observations_digest": _text(
                candidate.get("observations_digest"), "observations_digest"
            ),
            "assets": records,
        }
        payload = {**basis, "bundle_digest": digest_value(basis)}
        atomic_write_text(staging / "manifest.json", stable_json(payload) + "\n")
        staging.replace(target)
        fsync_directory(target.parent)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return payload


def verify_evidence_asset_bundle(path: str | Path) -> dict[str, Any]:
    """Verify the manifest, bundle digest, role set, and every archived byte."""

    root = Path(path).expanduser().resolve()
    manifest_path = root / "manifest.json"
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read evidence bundle manifest {manifest_path}: {exc}") from exc
    if not isinstance(raw, Mapping) or raw.get("schema") != EVIDENCE_ASSET_BUNDLE_SCHEMA:
        raise ValueError("evidence bundle has an unsupported schema")
    expected_fields = {
        "schema",
        "candidate_id",
        "candidate_version",
        "candidate_record_digest",
        "candidate_run_binding_digest",
        "observations_digest",
        "assets",
        "bundle_digest",
    }
    if set(raw) != expected_fields:
        raise ValueError("evidence bundle manifest has missing or unknown fields")
    raw_assets = raw.get("assets")
    if isinstance(raw_assets, (str, bytes)) or not isinstance(raw_assets, Sequence):
        raise ValueError("evidence bundle assets must be an array")
    if any(not isinstance(item, Mapping) for item in raw_assets):
        raise ValueError("evidence bundle asset records must be objects")
    roles: set[str] = set()
    for item in raw_assets:
        role = _text(item.get("role"), "asset role").casefold()
        if role in roles:
            raise ValueError("evidence bundle contains a duplicate asset role")
        roles.add(role)
        relative = Path(_text(item.get("path"), "asset path"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("evidence bundle asset path must remain inside the bundle")
        asset_path = root / relative
        if not asset_path.resolve().is_relative_to(root):
            raise ValueError("evidence bundle asset symlink escapes the bundle")
        if not asset_path.is_file():
            raise ValueError(f"evidence bundle asset is missing: {relative}")
        EvidenceAssetSpec(
            role=role,
            path=asset_path,
            media_type=item.get("media_type"),
            survey=item.get("survey"),
            instrument=item.get("instrument"),
            observation_time=item.get("observation_time"),
            calibration=item.get("calibration"),
        ).validated()
        size = item.get("size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size != asset_path.stat().st_size:
            raise ValueError(f"evidence bundle asset size differs: {relative}")
        actual_digest = sha256(asset_path.read_bytes()).hexdigest()
        expected_digest = _text(item.get("sha256"), "asset sha256").casefold()
        if not hmac.compare_digest(actual_digest, expected_digest):
            raise ValueError(f"evidence bundle asset digest differs: {relative}")
    if roles != REQUIRED_ASSET_ROLES:
        raise ValueError("evidence bundle is missing one or more required asset roles")
    basis = dict(raw)
    stored_digest = _text(basis.pop("bundle_digest"), "bundle_digest").casefold()
    computed_digest = digest_value(basis)
    if not hmac.compare_digest(stored_digest, computed_digest):
        raise ValueError("evidence bundle digest does not match its manifest")
    return dict(raw)


__all__ = [
    "EVIDENCE_ASSET_BUNDLE_SCHEMA",
    "REQUIRED_ASSET_ROLES",
    "EvidenceAssetSpec",
    "create_evidence_asset_bundle",
    "verify_evidence_asset_bundle",
]
