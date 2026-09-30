"""Read-only document-integrity check; never a scientific/submission approval gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "siderea.iris_document_binding.v1"
MAX_BYTES = 16 * 1024 * 1024
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
GUARDS = ("scientific_execution_authorized", "submission_authorized")


def git_blob_sha(data: bytes) -> str:
    """Compute the Git blob identifier, including Git's length/type header."""
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant: {value}")


def read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Manifest exceeds size limit")
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("Manifest must be a JSON object")
    return value


def source_bytes(root: Path, relative: str) -> bytes:
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Invalid source path")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in relative.split("/")):
        raise ValueError("Source path must be canonical and repository-relative")
    current = root.resolve(strict=True)
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlink evidence is not accepted")
    if not current.is_file() or current.stat().st_size > MAX_BYTES:
        raise ValueError("Source is missing, not a file, or oversized")
    return current.read_bytes()


def ledger_rows(data: bytes) -> list[tuple[str, str]]:
    rows = []
    for line in data.decode("utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == "Claim" or all(re.fullmatch(r"[-: ]+", cell) for cell in cells):
            continue
        if len(cells) != 5:
            raise ValueError("Unexpected ledger table shape")
        rows.append((cells[0], cells[3]))
    if not rows:
        raise ValueError("No claim rows found")
    return rows


def audit(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    verified: dict[str, bytes] = {}
    receipts: list[dict[str, Any]] = []
    if manifest.get("schema") != SCHEMA:
        errors.append("Unsupported manifest schema")
    revision = manifest.get("source_snapshot_revision")
    if not isinstance(revision, str) or not HEX40.fullmatch(revision):
        errors.append("Source snapshot must be a full lowercase commit SHA")
    if manifest.get("scope") != "retained_documentation_only":
        errors.append("Scope must remain retained_documentation_only")
    for guard in GUARDS:
        if manifest.get(guard) is not False:
            errors.append(f"{guard} must be literal false")
    blockers = manifest.get("unresolved_gates")
    if not isinstance(blockers, list) or not blockers or any(
        not isinstance(item, str) or not item.strip() for item in blockers
    ):
        errors.append("Nonempty unresolved human/evidence gates are required")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        artifacts = []
        errors.append("Nonempty artifacts list is required")
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for artifact in artifacts:
        try:
            if not isinstance(artifact, dict):
                raise ValueError("Artifact must be an object")
            aid = artifact.get("id")
            path = artifact.get("path")
            expected = artifact.get("git_blob_sha")
            if not isinstance(aid, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", aid):
                raise ValueError("Invalid artifact identifier")
            if aid in seen_ids:
                raise ValueError(f"Duplicate artifact identifier: {aid}")
            seen_ids.add(aid)
            if not isinstance(path, str) or path in seen_paths:
                raise ValueError("Missing or duplicate artifact path")
            seen_paths.add(path)
            if not isinstance(expected, str) or not HEX40.fullmatch(expected):
                raise ValueError("Invalid Git blob SHA")
            data = source_bytes(root, path)
            actual = git_blob_sha(data)
            receipts.append(
                {
                    "id": aid,
                    "path": path,
                    "git_blob_sha": actual,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "matches_recorded_blob": actual == expected,
                }
            )
            if actual != expected:
                raise ValueError(f"Source bytes changed: {path}")
            verified[aid] = data
        except (OSError, ValueError, TypeError) as exc:
            errors.append(str(exc))
    claims = manifest.get("claims")
    if not isinstance(claims, list) or not claims:
        claims = []
        errors.append("Nonempty claims list is required")
    seen_claims: set[str] = set()
    mapped_rows: list[tuple[str, str]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append("Claim must be an object")
            continue
        cid = claim.get("id")
        if not isinstance(cid, str) or not re.fullmatch(r"C[0-9]{2}", cid):
            errors.append("Invalid claim identifier")
        elif cid in seen_claims:
            errors.append(f"Duplicate claim identifier: {cid}")
        else:
            seen_claims.add(cid)
        text, status = claim.get("claim"), claim.get("ledger_status")
        if not isinstance(text, str) or not isinstance(status, str):
            errors.append("Claim text and original status must be strings")
        else:
            mapped_rows.append((text, status))
        refs = claim.get("document_refs")
        if not isinstance(refs, list) or not refs or any(
            not isinstance(ref, str) or ref not in verified for ref in refs
        ):
            errors.append(f"Unverified document reference: {cid}")
        if claim.get("independently_approved") is not False:
            errors.append(f"{cid}: documentation is not independent approval")
        boundary = claim.get("remaining_evidence_boundary")
        if not isinstance(boundary, str) or not boundary.strip():
            errors.append(f"{cid}: missing evidence boundary")
    try:
        if "ledger" not in verified:
            raise ValueError("A verified ledger artifact is required")
        if mapped_rows != ledger_rows(verified["ledger"]):
            raise ValueError("Manifest must preserve every ledger claim and status in order")
    except (UnicodeError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "schema": "siderea.iris_document_binding_report.v1",
        "source_snapshot_revision": revision,
        "source_integrity": "FAIL" if errors else "PASS",
        "submission_readiness": "BLOCKED",
        "scientific_execution_authorized": False,
        "submission_authorized": False,
        "claim_count": len(claims),
        "verified_document_count": len(verified),
        "artifacts": receipts,
        "errors": errors,
        "unresolved_gates": blockers,
        "boundary": (
            "PASS checks local document bytes against recorded Git blob identifiers. "
            "It does not re-fetch commit history, validate science, run experiments, "
            "review primary records, certify a PDF, or authorize submission."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = audit(args.root, read_json(args.manifest))
    except (OSError, ValueError, UnicodeError) as exc:
        print(
            json.dumps(
                {
                    "source_integrity": "FAIL",
                    "submission_readiness": "BLOCKED",
                    "scientific_execution_authorized": False,
                    "submission_authorized": False,
                    "error": str(exc),
                }
            )
        )
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    if report["source_integrity"] != "PASS":
        return 1
    return 2 if args.require_ready else 0


if __name__ == "__main__":
    sys.exit(main())
