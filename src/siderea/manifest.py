"""Immutable-ish, atomic run manifests for reproducible pipeline execution."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from .atomic import atomic_write_text
from .provenance import CheckProvenance, digest_file, digest_value, utc_now

RUN_MANIFEST_SCHEMA = "siderea.run_manifest.v1"


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def _git_state(root: Path) -> tuple[str, bool | None]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        return revision.stdout.strip(), bool(status.stdout.strip())
    except Exception:
        return "unversioned", None


def _source_digest(root: Path, *, package_root: Path | None = None) -> str:
    """Hash the code actually imported by this process.

    A checkout is used only when its ``src/siderea`` directory is the supplied
    active package root. This prevents an installed process from accidentally
    attesting to an unrelated lookalike checkout in its working directory.
    """

    source_suffixes = frozenset({".py", ".toml", ".json", ".yaml", ".yml"})
    candidates: list[tuple[str, Path]] = []
    checkout_package = root / "src" / "siderea"
    active_package = package_root.resolve() if package_root is not None else None
    active_checkout = checkout_package.is_dir() and (
        active_package is None or checkout_package.resolve() == active_package
    )
    if active_checkout:
        for directory in (checkout_package, root / "configs"):
            if directory.is_dir():
                candidates.extend(
                    (path.relative_to(root).as_posix(), path)
                    for path in directory.rglob("*")
                    if path.is_file()
                    and path.suffix.casefold() in source_suffixes
                    and "__pycache__" not in path.parts
                )
        if (root / "pyproject.toml").is_file():
            candidates.append(("pyproject.toml", root / "pyproject.toml"))
    if not candidates:
        installed_root = (package_root or Path(__file__).resolve().parent).resolve()
        if installed_root.is_dir():
            candidates.extend(
                (f"siderea/{path.relative_to(installed_root).as_posix()}", path)
                for path in installed_root.rglob("*")
                if path.is_file()
                and path.suffix.casefold() in source_suffixes
                and "__pycache__" not in path.parts
            )
    if not candidates:
        raise RuntimeError("cannot identify any SIDEREA source files for the run manifest")
    digest = sha256()
    for label, path in sorted(set(candidates), key=lambda item: item[0]):
        relative = label.encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


@dataclass
class Artifact:
    path: str
    sha256: str
    size_bytes: int
    role: str


@dataclass
class RunManifest:
    schema: str
    run_id: str
    created_at: str
    command: list[str]
    configuration: dict[str, Any]
    configuration_digest: str
    code_revision: str
    code_source_digest: str
    code_worktree_dirty: bool | None
    environment: dict[str, str]
    status: str = "running"
    completed_at: str = ""
    artifacts: list[Artifact] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        configuration: Mapping[str, Any],
        *,
        command: list[str] | None = None,
        project_root: Path | None = None,
    ) -> RunManifest:
        config = dict(configuration)
        root = project_root or Path.cwd()
        now = datetime.now(UTC)
        revision, dirty = _git_state(root)
        return cls(
            schema=RUN_MANIFEST_SCHEMA,
            run_id=f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
            created_at=now.isoformat(),
            command=list(command or []),
            configuration=config,
            configuration_digest=digest_value(config),
            code_revision=revision,
            code_source_digest=_source_digest(
                root,
                package_root=Path(__file__).resolve().parent,
            ),
            code_worktree_dirty=dirty,
            environment={
                "siderea-astronomy": _package_version("siderea-astronomy"),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "numpy": _package_version("numpy"),
                "pandas": _package_version("pandas"),
                "scikit-learn": _package_version("scikit-learn"),
                "torch": _package_version("torch"),
                "astropy": _package_version("astropy"),
                "alerce": _package_version("alerce"),
            },
        )

    def add_artifact(self, path: Path, role: str) -> None:
        if self.status != "running":
            raise RuntimeError("cannot add an artifact after a run has finished")
        if not role.strip():
            raise ValueError("artifact role must not be empty")
        resolved = path.resolve()
        self.artifacts.append(
            Artifact(
                path=str(resolved),
                sha256=digest_file(resolved),
                size_bytes=resolved.stat().st_size,
                role=role.strip(),
            )
        )

    def add_check(self, check: CheckProvenance) -> None:
        if self.status != "running":
            raise RuntimeError("cannot add evidence after a run has finished")
        self.checks.append(check.to_dict())

    def finish(self, *, status: str, metrics: Mapping[str, Any] | None = None) -> None:
        if self.status != "running":
            raise RuntimeError(f"run already finished with status {self.status!r}")
        if status not in {"completed", "failed", "blocked", "interrupted"}:
            raise ValueError(f"Invalid terminal manifest status: {status}")
        self.status = status
        self.completed_at = utc_now()
        if metrics:
            self.metrics.update(dict(metrics))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: Path) -> None:
        content = (
            json.dumps(
                self.to_dict(),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
        atomic_write_text(path, content)


__all__ = ["Artifact", "RUN_MANIFEST_SCHEMA", "RunManifest"]
