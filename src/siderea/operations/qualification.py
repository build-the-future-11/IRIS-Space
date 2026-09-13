"""Separate offline parser replay and read-only live service qualification."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from urllib.request import Request

from siderea.clients import tns
from siderea.clients.base import ResilientExecutor
from siderea.operations.fixtures import ServiceFixture
from siderea.provenance import digest_file, digest_value


def qualify_tns_fixtures(
    fixtures: Sequence[ServiceFixture], *, query: Mapping[str, Any], expected_status: str
) -> dict[str, Any]:
    """Execute the real two-stage search/parser with exact sanitized fixture queries.

    Fixture request shape is {"endpoint": HTTPS_URL, "query": TNS_QUERY_OBJECT}.
    No credentials are required or transmitted; the loader has no network branch.
    This qualifies parser behavior for these bytes, not their claimed live origin.
    """
    if not fixtures or any(fixture.service != "tns" for fixture in fixtures):
        raise ValueError("TNS qualification requires non-empty TNS fixtures")
    if expected_status not in {"clear", "match", "error"}:
        raise ValueError("expected_status must be clear, match or error")
    if set(query) != {"internal_name", "ra", "dec", "radius_arcsec"}:
        raise ValueError("TNS qualification query has missing or unknown fields")
    verified = [ServiceFixture.from_dict(fixture.to_dict()) for fixture in fixtures]
    by_request = {fixture.request_digest: fixture for fixture in verified}
    if len(by_request) != len(verified):
        raise ValueError("qualification case has duplicate request fixtures")
    consumed: set[str] = set()
    unmatched: list[str] = []

    def load(request: Request, timeout: float) -> bytes:
        if not isinstance(request.data, bytes):
            raise ValueError("offline qualification requires a byte-encoded request body")
        form = parse_qs(request.data.decode("utf-8"), strict_parsing=True)
        public_request = {"endpoint": request.full_url, "query": json.loads(form["data"][0])}
        fixture = by_request.get(digest_value(public_request))
        if fixture is None:
            unmatched.append(digest_value(public_request))
            raise ValueError("offline qualification has no matching fixture")
        status, _, body = fixture.replay(public_request)
        consumed.add(fixture.fixture_id)
        if status >= 400:
            raise OSError(f"recorded HTTP status {status}")
        if not 200 <= status < 300:
            raise ValueError("recorded non-success HTTP response")
        return body

    client = tns.TNSClient(
        # The transport is forcibly offline; these public labels are not credentials.
        tns.TNSCredentials("offline-fixture-only", "offline", "fixture-qualification"),
        executor=ResilientExecutor(attempts=1),
        response_loader=load,
    )
    result = client.search(
        internal_name=query["internal_name"],
        ra=query["ra"],
        dec=query["dec"],
        radius_arcsec=query["radius_arcsec"],
    )
    observed = result.provenance.status.value
    report = {
        "schema": "siderea.tns_fixture_qualification.v1",
        "query": dict(query),
        "expected_status": expected_status,
        "observed_status": observed,
        "passed": observed == expected_status and not unmatched and len(consumed) == len(verified),
        "fixture_ids": sorted(fixture.fixture_id for fixture in verified),
        "consumed_fixture_ids": sorted(consumed),
        "unmatched_request_digests": unmatched,
        "adapter_code_sha256": digest_file(Path(tns.__file__)),
        "scope": "executed_tns_parser_cases_not_live_origin_or_other_catalogue_qualification",
    }
    report["report_digest"] = digest_value(report)
    return report


def qualify_tns_live(
    client: tns.TNSClient,
    *,
    query: Mapping[str, Any],
    expected_status: str,
    expected_names: Sequence[str] = (),
) -> dict[str, Any]:
    """Run one bounded, read-only search case against a real TNS transport.

    Expectations must be chosen independently before execution. A service failure
    cannot pass qualification. This report never grants candidate clearance.
    """
    if client.response_loader is not None:
        raise ValueError("live qualification cannot use an offline response loader")
    if set(query) != {"internal_name", "ra", "dec", "radius_arcsec"}:
        raise ValueError("TNS qualification query has missing or unknown fields")
    if expected_status not in {"clear", "match"}:
        raise ValueError("live expected_status must be clear or match")
    if any(not isinstance(name, str) or not name.strip() for name in expected_names):
        raise ValueError("expected names must be non-empty strings")
    names = sorted(set(name.strip() for name in expected_names))
    if (expected_status == "match") != bool(names):
        raise ValueError("match requires expected names; clear must not specify names")
    result = client.search(
        internal_name=query["internal_name"],
        ra=query["ra"],
        dec=query["dec"],
        radius_arcsec=query["radius_arcsec"],
    )
    evidence = result.provenance.to_dict()
    # Upstream messages may echo request contents. Never persist them in a report.
    if result.provenance.error:
        evidence["error"] = "TNS request failed; no clearance established"
    report = {
        "schema": "siderea.tns_live_qualification.v1",
        "endpoint": client.endpoint,
        "query": dict(query),
        "expected_status": expected_status,
        "expected_names": names,
        "observed_status": result.provenance.status.value,
        "passed": result.provenance.status.value == expected_status
        and set(names).issubset(result.provenance.matches),
        "evidence": evidence,
        "adapter_code_sha256": digest_file(Path(tns.__file__)),
        "scope": "single_live_search_case_not_scientific_validation_or_submission_approval",
    }
    report["report_digest"] = digest_value(report)
    return report
