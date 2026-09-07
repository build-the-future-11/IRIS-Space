"""Hashed dataset snapshots for reproducible training and backtests."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from iris.atomic import atomic_write_text
from iris.provenance import digest_file, digest_value


@dataclass(frozen=True)
class SnapshotFile:
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class DatasetSnapshot:
    name: str
    created_at: str
    files: tuple[SnapshotFile, ...]
    label_policy: str
    split_policy: str
    digest: str

    def write(self, path: Path) -> None:
        atomic_write_text(path, json.dumps(asdict(self), indent=2, sort_keys=True) + "\n")


def create_snapshot(
    name: str,
    paths: Iterable[Path],
    *,
    label_policy: str,
    split_policy: str = "chronological-by-object",
) -> DatasetSnapshot:
    files = tuple(
        SnapshotFile(str(path.resolve()), digest_file(path), path.stat().st_size)
        for path in sorted(paths, key=lambda item: str(item))
    )
    if not files:
        raise ValueError("snapshot requires at least one file")
    content = {
        "name": name,
        "files": [
            {
                "name": Path(item.path).name,
                "sha256": item.sha256,
                "size_bytes": item.size_bytes,
            }
            for item in files
        ],
        "label_policy": label_policy,
        "split_policy": split_policy,
    }
    return DatasetSnapshot(
        name=name,
        created_at=datetime.now(UTC).isoformat(),
        files=files,
        label_policy=label_policy,
        split_policy=split_policy,
        digest=digest_value(content),
    )
