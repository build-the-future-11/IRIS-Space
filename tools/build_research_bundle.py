from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path
from typing import Iterable

ROOT_FILES = (
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "PROJECT_FINISH_CHECKLIST.md",
    "FINAL_TODO.md",
    "Makefile",
    "pyproject.toml",
    "requirements.txt",
)
ROOT_DIRS = ("configs", "docs", "examples", "src", "tests", "paper", "tools")
EXCLUDED_NAMES = {".DS_Store", ".coverage"}
EXCLUDED_PARTS = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
MANIFEST_NAME = "RESEARCH_BUNDLE_MANIFEST.json"
COMMIT_SHA_RE = re.compile(r"[0-9a-f]{40}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_allowed(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return False
    if path.name in EXCLUDED_NAMES:
        return False
    return path.is_file() and not path.is_symlink()


def iter_bundle_files(root: Path) -> list[Path]:
    root = root.resolve()
    paths: list[Path] = []

    for rel in ROOT_FILES:
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f"required bundle file missing: {rel}")
        paths.append(path)

    for rel in ROOT_DIRS:
        base = root / rel
        if not base.is_dir():
            raise FileNotFoundError(f"required bundle directory missing: {rel}")
        paths.extend(path for path in base.rglob("*") if _is_allowed(path, root))

    unique = {path.relative_to(root).as_posix(): path for path in paths}
    return [unique[name] for name in sorted(unique)]


def build_manifest(root: Path, source_revision: str, files: Iterable[Path]) -> dict[str, object]:
    root = root.resolve()
    entries = []
    for path in files:
        data = path.read_bytes()
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": len(data),
                "sha256": _sha256(data),
            }
        )

    return {
        "schema_version": 1,
        "source_revision": source_revision,
        "bundle_scope": "SIDEREA public research-alpha source/research bundle candidate",
        "license_status": "LicenseRef-Proprietary",
        "redistribution_status": "blocked_pending_explicit_copyright_owner_license_decision",
        "redistribution_notice": (
            "This archive is a reproducibility/package candidate only. Its creation does not "
            "grant open-source or redistribution rights."
        ),
        "files": entries,
    }


def _tar_bytes(root: Path, files: Iterable[Path], manifest_bytes: bytes) -> bytes:
    root = root.resolve()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in files:
            rel = path.relative_to(root).as_posix()
            data = path.read_bytes()
            info = tarfile.TarInfo(rel)
            info.size = len(data)
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))

        info = tarfile.TarInfo(MANIFEST_NAME)
        info.size = len(manifest_bytes)
        info.mode = 0o644
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        info.mtime = 0
        archive.addfile(info, io.BytesIO(manifest_bytes))
    return buffer.getvalue()


def build_bundle(root: Path, output: Path, source_revision: str) -> dict[str, object]:
    if COMMIT_SHA_RE.fullmatch(source_revision) is None:
        raise ValueError("source_revision must be an exact lowercase 40-hex Git commit SHA")

    files = iter_bundle_files(root)
    manifest = build_manifest(root, source_revision, files)
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True).encode("utf-8") + b"\n"
    )
    tar_bytes = _tar_bytes(root, files, manifest_bytes)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            compressed.write(tar_bytes)

    manifest["archive_sha256"] = _sha256(output.read_bytes())
    manifest["archive_size_bytes"] = output.stat().st_size
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic SIDEREA research-alpha source bundle."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()

    manifest = build_bundle(args.root, args.output, args.source_revision)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
