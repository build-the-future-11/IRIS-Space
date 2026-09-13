"""Transport simulations exercise qualification; they are not live TNS evidence."""

import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from siderea.clients.base import ResilientExecutor
from siderea.clients.tns import TNSClient, TNSCredentials
from siderea.operations.qualification import qualify_tns_live

QUERY = {"internal_name": "synthetic", "ra": 1, "dec": 2, "radius_arcsec": 3}


def client():
    return TNSClient(
        TNSCredentials("secret-test-key", "123", "test"), executor=ResilientExecutor(attempts=1)
    )


@contextmanager
def response(body):
    import io

    yield io.BytesIO(body)


@pytest.mark.parametrize(
    "expected,names,bodies,passed,calls",
    [
        ("clear", [], [b'{"id_code":200,"data":[]}'] * 2, True, 2),
        (
            "match",
            ["SN test"],
            [b'{"id_code":200,"data":[{"prefix":"SN","objname":"test"}]}'],
            True,
            1,
        ),
        (
            "match",
            ["SN other"],
            [b'{"id_code":200,"data":[{"prefix":"SN","objname":"test"}]}'],
            False,
            1,
        ),
        (
            "match",
            ["SN test"],
            [
                b'{"id_code":200,"data":[]}',
                b'{"id_code":200,"data":[{"prefix":"SN","objname":"test"}]}',
            ],
            True,
            2,
        ),
        ("clear", [], [b'{"id_code":200,"data":[]}', b"{}"], False, 2),
    ],
)
def test_status_identity_and_two_stage_evidence(expected, names, bodies, passed, calls):
    with patch(
        "siderea.clients.tns.urlopen", side_effect=[response(body) for body in bodies]
    ) as transport:
        report = qualify_tns_live(
            client(), query=QUERY, expected_status=expected, expected_names=names
        )
    assert report["passed"] is passed
    assert transport.call_count == calls
    assert "secret-test-key" not in json.dumps(report)
    assert report["report_digest"]
    if expected == "clear" and passed:
        assert report["evidence"]["query"]["methods"] == ["internal_name", "cone"]


def test_errors_are_redacted_and_never_pass():
    with patch("siderea.clients.tns.urlopen", side_effect=OSError("secret-test-key")):
        report = qualify_tns_live(client(), query=QUERY, expected_status="clear")
    assert not report["passed"]
    assert report["observed_status"] == "error"
    assert "secret-test-key" not in json.dumps(report)


@pytest.mark.parametrize("status,names", [("error", []), ("match", []), ("clear", ["SN test"])])
def test_invalid_expectations_make_no_requests(status, names):
    with patch("siderea.clients.tns.urlopen") as transport, pytest.raises(ValueError):
        qualify_tns_live(client(), query=QUERY, expected_status=status, expected_names=names)
    transport.assert_not_called()


def test_offline_loader_cannot_be_labelled_live():
    instance = client()
    instance.response_loader = lambda request, timeout: b"{}"
    with pytest.raises(ValueError, match="offline"):
        qualify_tns_live(instance, query=QUERY, expected_status="clear")


def test_cli_credentials_report_and_immutable_output(tmp_path, monkeypatch):
    from siderea.cli import main

    query = tmp_path / "query.json"
    query.write_text(json.dumps(QUERY))
    output = tmp_path / "result.json"
    args = ["tns-qualify", str(query), str(output), "--expected-status", "clear"]
    for key in ("TNS_API_KEY", "TNS_BOT_ID", "TNS_BOT_NAME"):
        monkeypatch.delenv(key, raising=False)
    with patch("siderea.clients.tns.urlopen") as transport:
        assert main(args) == 2
        transport.assert_not_called()
    assert not output.exists()
    for key in ("TNS_API_KEY", "TNS_BOT_ID", "TNS_BOT_NAME"):
        monkeypatch.setenv(key, "synthetic")
    with patch(
        "siderea.clients.tns.urlopen",
        side_effect=[response(b'{"id_code":200,"data":[]}') for _ in range(2)],
    ):
        assert main(args) == 0
    saved = output.read_bytes()
    assert json.loads(saved)["passed"]
    with patch("siderea.clients.tns.urlopen") as transport:
        assert main(args) == 2
        transport.assert_not_called()
    assert output.read_bytes() == saved
