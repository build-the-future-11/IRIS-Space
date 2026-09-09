"""Shared retry and result handling for remote astronomy services."""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from siderea.provenance import CheckProvenance, CheckStatus, digest_value

T = TypeVar("T")


@dataclass(frozen=True)
class ServiceResult(Generic[T]):
    provenance: CheckProvenance
    value: T | None = None
    records: Sequence[Mapping[str, object]] = field(default_factory=tuple)

    @property
    def safe_clear(self) -> bool:
        return self.provenance.safe_clear


class ResilientExecutor:
    def __init__(
        self,
        *,
        attempts: int = 3,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 8.0,
        jitter_fraction: float = 0.15,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
            raise ValueError("attempts must be a positive integer")
        delays = (base_delay_seconds, max_delay_seconds, jitter_fraction)
        if any(not math.isfinite(value) or value < 0 for value in delays):
            raise ValueError("retry delays and jitter_fraction must be finite and non-negative")
        if not callable(sleeper):
            raise TypeError("sleeper must be callable")
        self.attempts = attempts
        self.base_delay_seconds = float(base_delay_seconds)
        self.max_delay_seconds = float(max_delay_seconds)
        self.jitter_fraction = float(jitter_fraction)
        self.sleeper = sleeper

    def run(
        self,
        *,
        service: str,
        query: Mapping[str, object],
        operation: Callable[[], T],
        has_match: Callable[[T], bool],
        match_names: Callable[[T], Sequence[str]] | None = None,
        retry_if: Callable[[Exception], bool] | None = None,
    ) -> ServiceResult[T]:
        if not service.strip():
            raise ValueError("service must not be empty")
        started = time.monotonic()
        last_error: Exception | None = None
        used_attempts = 0
        delay = min(self.base_delay_seconds, self.max_delay_seconds)
        for attempt in range(1, self.attempts + 1):
            used_attempts = attempt
            try:
                value = operation()
                matched = has_match(value)
                names = tuple(match_names(value)) if matched and match_names else ()
                elapsed = (time.monotonic() - started) * 1000.0
                provenance = CheckProvenance(
                    service=service,
                    status=CheckStatus.MATCH if matched else CheckStatus.CLEAR,
                    query=dict(query),
                    matches=names,
                    attempts=attempt,
                    latency_ms=elapsed,
                    response_digest=digest_value(value),
                )
                return ServiceResult(provenance=provenance, value=value)
            except Exception as exc:
                last_error = exc
                should_retry = retry_if(exc) if retry_if else True
                if attempt >= self.attempts or not should_retry:
                    break
                jitter = delay * self.jitter_fraction * random.random()
                self.sleeper(min(self.max_delay_seconds, delay + jitter))
                delay = min(self.max_delay_seconds, delay * 2)

        elapsed = (time.monotonic() - started) * 1000.0
        provenance = CheckProvenance(
            service=service,
            status=CheckStatus.ERROR,
            query=dict(query),
            error=str(last_error) if last_error else "unknown service failure",
            attempts=used_attempts,
            latency_ms=elapsed,
        )
        return ServiceResult(provenance=provenance)
