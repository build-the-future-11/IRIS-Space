"""Secure, durable same-directory atomic file publication."""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO

_MAX_TEMP_ATTEMPTS = 128


def _open_unique_temporary(destination: Path) -> tuple[int, Path]:
    """Create an unpredictable temporary file without following a symlink."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    prefix = destination.name[:120]
    for _ in range(_MAX_TEMP_ATTEMPTS):
        temporary = destination.with_name(f".{prefix}.{secrets.token_hex(16)}.tmp")
        try:
            descriptor = os.open(temporary, flags, 0o600)
        except FileExistsError:
            continue
        return descriptor, temporary
    raise FileExistsError("could not allocate a unique atomic-write temporary file")


def fsync_directory(path: Path) -> None:
    """Persist a completed rename where directory fsync is supported."""

    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(path: str | Path, content: bytes) -> Path:
    """Durably replace ``path`` from an exclusive, same-directory temp file."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = _open_unique_temporary(destination)
    descriptor_open = True
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor_open = False
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        fsync_directory(destination.parent)
    except BaseException:
        if descriptor_open:
            with suppress(OSError):
                os.close(descriptor)
        with suppress(FileNotFoundError):
            temporary.unlink()
        raise
    return destination


def atomic_write_text(path: str | Path, content: str) -> Path:
    """UTF-8 encode and publish text through :func:`atomic_write_bytes`."""

    return atomic_write_bytes(path, content.encode("utf-8"))


def atomic_create_binary(path: str | Path, writer: Callable[[BinaryIO], object]) -> Path:
    """Publish a newly created binary file without overwriting an existing name."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = _open_unique_temporary(destination)
    descriptor_open = True
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor_open = False
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination)
        fsync_directory(destination.parent)
    except BaseException:
        if descriptor_open:
            with suppress(OSError):
                os.close(descriptor)
        raise
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()
    return destination


__all__ = [
    "atomic_create_binary",
    "atomic_write_bytes",
    "atomic_write_text",
    "fsync_directory",
]
