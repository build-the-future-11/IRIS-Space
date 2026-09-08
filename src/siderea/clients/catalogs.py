"""Lazy, fail-closed adapters for SkyBoT, SIMBAD, and VSX."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from functools import partial
from typing import Any

from siderea.provenance import CheckProvenance, CheckStatus

from .base import ResilientExecutor, ServiceResult

DEFAULT_CATALOG_TIMEOUT_SECONDS = 30.0
DEFAULT_CATALOG_USER_AGENT = "siderea-astronomy/0.3"


def _validate_network_policy(timeout_seconds: float, user_agent: str) -> tuple[float, str]:
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise TypeError("timeout_seconds must be a number")
    timeout = float(timeout_seconds)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout_seconds must be finite and positive")
    if not isinstance(user_agent, str):
        raise TypeError("user_agent must be a string")
    agent = user_agent.strip()
    if not agent:
        raise ValueError("user_agent must not be empty")
    if "\r" in agent or "\n" in agent:
        raise ValueError("user_agent must not contain line breaks")
    return timeout, agent


def _configure_astroquery_client(
    client: Any,
    *,
    timeout_seconds: float,
    user_agent: str,
) -> Any:
    """Apply one bounded HTTP policy to a fresh astroquery query object.

    SkyBoT and VizieR expose ``TIMEOUT`` while recent SIMBAD releases expose
    ``timeout``.  The per-instance session wrapper is intentional as well:
    SIMBAD's synchronous TAP path and capability discovery have not always
    forwarded that service setting to every HTTP request.  Supplying a default
    at the session boundary closes that gap without mutating astroquery globals.
    """

    session = getattr(client, "_session", None)
    headers = getattr(session, "headers", None)
    request = getattr(session, "request", None)
    if session is None or headers is None or not callable(request):
        raise RuntimeError("astroquery client does not expose a configurable HTTP session")

    existing_agent = str(headers.get("User-Agent", "")).strip()
    if user_agent not in existing_agent:
        headers["User-Agent"] = f"{existing_agent} {user_agent}".strip()
    # functools.partial keywords can still be overridden by an explicit
    # per-request value.  All three clients also receive their public service
    # timeout below, so astroquery's own value and this safety net agree.
    session.request = partial(request, timeout=timeout_seconds)

    for attribute in ("timeout", "TIMEOUT"):
        if hasattr(client, attribute):
            setattr(client, attribute, timeout_seconds)
            break
    else:
        raise RuntimeError("astroquery client does not expose a supported timeout setting")
    return client


class _CatalogClientPolicy:
    def __init__(
        self,
        executor: ResilientExecutor | None,
        *,
        enabled: bool,
        timeout_seconds: float,
        user_agent: str,
    ) -> None:
        timeout, agent = _validate_network_policy(timeout_seconds, user_agent)
        self.executor = executor or ResilientExecutor()
        self.enabled = enabled
        self.timeout_seconds = timeout
        self.user_agent = agent

    def query_policy(self) -> dict[str, object]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "user_agent": self.user_agent,
        }


def disabled_result(service: str, query: Mapping[str, object]) -> ServiceResult[object]:
    return ServiceResult(
        provenance=CheckProvenance(
            service=service,
            status=CheckStatus.DISABLED,
            query=dict(query),
            error="disabled by configuration",
            attempts=0,
        )
    )


def _table_records(table: Any) -> list[dict[str, object]]:
    if table is None:
        return []
    columns = list(getattr(table, "colnames", []))
    records: list[dict[str, object]] = []
    for row in table:
        records.append({name: str(row[name]) for name in columns})
    return records


def _first_names(
    records: Sequence[Mapping[str, object]], columns: Sequence[str]
) -> tuple[str, ...]:
    names: list[str] = []
    for record in records:
        for column in columns:
            value = str(record.get(column, "")).strip()
            if value and value.lower() not in {"nan", "--", "none"}:
                names.append(value)
                break
    return tuple(names[:10])


class SkyBotClient(_CatalogClientPolicy):
    def __init__(
        self,
        executor: ResilientExecutor | None = None,
        *,
        enabled: bool = True,
        timeout_seconds: float = DEFAULT_CATALOG_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_CATALOG_USER_AGENT,
    ) -> None:
        super().__init__(
            executor,
            enabled=enabled,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
        )

    def check(
        self, *, ra: float, dec: float, mjd: float, radius_arcsec: float = 10.0
    ) -> ServiceResult[list[dict[str, object]]]:
        query = {
            "ra": ra,
            "dec": dec,
            "mjd": mjd,
            "radius_arcsec": radius_arcsec,
            "network_policy": self.query_policy(),
        }
        if not self.enabled:
            return disabled_result("skybot", query)  # type: ignore[return-value]

        def operation() -> list[dict[str, object]]:
            import astropy.units as u
            from astropy.coordinates import SkyCoord
            from astropy.time import Time
            from astroquery.imcce import Skybot

            client = _configure_astroquery_client(
                Skybot(),
                timeout_seconds=self.timeout_seconds,
                user_agent=self.user_agent,
            )
            coordinate = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
            result = client.cone_search(
                coordinate, radius_arcsec * u.arcsec, Time(mjd, format="mjd")
            )
            return _table_records(result)

        return self.executor.run(
            service="skybot",
            query=query,
            operation=operation,
            has_match=bool,
            match_names=lambda rows: _first_names(rows, ("Name", "name", "Num", "number")),
            retry_if=lambda exc: not isinstance(exc, (ImportError, ValueError)),
        )


class SimbadClient(_CatalogClientPolicy):
    def __init__(
        self,
        executor: ResilientExecutor | None = None,
        *,
        enabled: bool = True,
        timeout_seconds: float = DEFAULT_CATALOG_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_CATALOG_USER_AGENT,
    ) -> None:
        super().__init__(
            executor,
            enabled=enabled,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
        )

    def check(
        self, *, ra: float, dec: float, radius_arcsec: float = 3.0
    ) -> ServiceResult[list[dict[str, object]]]:
        query = {
            "ra": ra,
            "dec": dec,
            "radius_arcsec": radius_arcsec,
            "network_policy": self.query_policy(),
        }
        if not self.enabled:
            return disabled_result("simbad", query)  # type: ignore[return-value]

        def operation() -> list[dict[str, object]]:
            import astropy.units as u
            from astropy.coordinates import SkyCoord
            from astroquery.simbad import Simbad

            client = _configure_astroquery_client(
                Simbad(),
                timeout_seconds=self.timeout_seconds,
                user_agent=self.user_agent,
            )
            # Failure to request the object-type field is scientifically
            # material: without it a counterpart cannot be classified safely.
            # Let the resilient executor record an explicit ERROR instead of
            # silently continuing with incomplete catalogue context.
            client.add_votable_fields("otype")
            coordinate = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
            return _table_records(client.query_region(coordinate, radius=radius_arcsec * u.arcsec))

        return self.executor.run(
            service="simbad",
            query=query,
            operation=operation,
            has_match=bool,
            match_names=lambda rows: _first_names(rows, ("MAIN_ID", "main_id")),
            retry_if=lambda exc: not isinstance(exc, (ImportError, ValueError)),
        )


class VSXClient(_CatalogClientPolicy):
    def __init__(
        self,
        executor: ResilientExecutor | None = None,
        *,
        enabled: bool = True,
        timeout_seconds: float = DEFAULT_CATALOG_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_CATALOG_USER_AGENT,
    ) -> None:
        super().__init__(
            executor,
            enabled=enabled,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
        )

    def check(
        self, *, ra: float, dec: float, radius_arcsec: float = 3.0
    ) -> ServiceResult[list[dict[str, object]]]:
        query = {
            "ra": ra,
            "dec": dec,
            "radius_arcsec": radius_arcsec,
            "network_policy": self.query_policy(),
        }
        if not self.enabled:
            return disabled_result("vsx", query)  # type: ignore[return-value]

        def operation() -> list[dict[str, object]]:
            import astropy.units as u
            from astropy.coordinates import SkyCoord
            from astroquery.vizier import Vizier

            client = _configure_astroquery_client(
                Vizier(columns=["*", "+_r"], row_limit=10),
                timeout_seconds=self.timeout_seconds,
                user_agent=self.user_agent,
            )
            coordinate = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
            tables = client.query_region(
                coordinate,
                radius=radius_arcsec * u.arcsec,
                catalog="B/vsx/vsx",
            )
            return _table_records(tables[0]) if tables else []

        return self.executor.run(
            service="vsx",
            query=query,
            operation=operation,
            has_match=bool,
            match_names=lambda rows: _first_names(rows, ("Name", "name", "OID", "oid")),
            retry_if=lambda exc: not isinstance(exc, (ImportError, ValueError)),
        )
