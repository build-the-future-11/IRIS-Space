from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from siderea.clients.tns import TNS_SEARCH_URL
from siderea.operations.fixtures import ServiceFixture
from siderea.operations.qualification import qualify_tns_fixtures

QUERY = {"internal_name": "synthetic", "ra": 1, "dec": 2, "radius_arcsec": 3}


def fixture(query, body, status=200):
    return ServiceFixture.create(
        service="tns",
        service_version="synthetic-http-fixture",
        capture_mode="synthetic",
        scenario="success" if status == 200 else "failure",
        request={"endpoint": TNS_SEARCH_URL, "query": query},
        status_code=status,
        response_headers={},
        response_body=body,
    )


def test_actual_tns_two_stage_parser_replays_without_network():
    fixtures = [
        fixture({"internal_name": "synthetic"}, b'{"id_code":200,"data":[]}'),
        fixture(
            {"ra": 1.0, "dec": 2.0, "radius": 3.0, "units": "arcsec"}, b'{"id_code":200,"data":[]}'
        ),
    ]
    with patch("siderea.clients.tns.urlopen", side_effect=AssertionError("network forbidden")):
        result = qualify_tns_fixtures(fixtures, query=QUERY, expected_status="clear")
    assert result["passed"] and len(result["consumed_fixture_ids"]) == 2
    missing = qualify_tns_fixtures(fixtures[:1], query=QUERY, expected_status="error")
    assert missing["observed_status"] == "error" and not missing["passed"]
    assert missing["unmatched_request_digests"]


@pytest.mark.parametrize(
    "body,status",
    [
        (b'{"id_code":200}', 200),
        (b'{"id_code":200,"data":[1]}', 200),
        (b"not-json", 200),
        (b"", 429),
        (b"", 503),
    ],
)
def test_malformed_and_failure_responses_never_become_clear(body, status):
    result = qualify_tns_fixtures(
        [fixture({"internal_name": "synthetic"}, body, status)],
        query=QUERY,
        expected_status="error",
    )
    assert result["passed"] and result["observed_status"] == "error"


def test_match_and_cli_report_are_real_parser_results(tmp_path, capsys):
    from siderea.cli import main

    capture = fixture(
        {"internal_name": "synthetic"}, b'{"id_code":200,"data":[{"objname":"test"}]}'
    )
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(capture.to_dict()))
    query = tmp_path / "query.json"
    query.write_text(json.dumps(QUERY))
    report = tmp_path / "report.json"
    assert (
        main(
            [
                "fixture-qualify-tns",
                str(query),
                str(report),
                str(path),
                "--expected-status",
                "match",
            ]
        )
        == 0
    )
    assert json.loads(report.read_text())["observed_status"] == "match"
    assert json.loads(capsys.readouterr().out)["passed"]
