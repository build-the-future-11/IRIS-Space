from __future__ import annotations

import json

import pytest

from siderea.clients.base import ResilientExecutor
from siderea.clients.tns import TNSCredentials
from siderea.clients.tns_object import TNSObjectClient
from siderea.provenance import CheckStatus, digest_value


def test_tns_object_client_is_read_only_and_returns_reply() -> None:
    response = {
        "id_code": 200,
        "id_message": "OK",
        "data": {"reply": {"objname": "2026abc", "photometry": [{"flux": 1.0}]}},
    }
    client = TNSObjectClient(
        TNSCredentials("secret", "1", "bot"),
        response_loader=lambda request, timeout: json.dumps(response).encode(),
    )
    result = client.get_object("2026abc")
    assert result.provenance.status is CheckStatus.MATCH
    assert result.value is not None
    assert result.value["objname"] == "2026abc"
    assert "secret" not in repr(client.credentials)


@pytest.mark.parametrize(
    "reply",
    [
        {"objname": "2026other"},
        {"photometry": [{"flux": 1.0}]},
        {},
        {"objname": None},
        {"objname": ""},
        {"objname": 2026},
        {"objname": ["2026abc"]},
    ],
)
def test_object_reply_without_requested_identity_is_an_error(reply: dict) -> None:
    requests = []

    def loader(request, timeout):
        requests.append(request)
        return json.dumps({"id_code": 200, "data": {"reply": reply}}).encode()

    client = TNSObjectClient(
        TNSCredentials("fixture-key", "1", "fixture-bot"),
        executor=ResilientExecutor(sleeper=lambda delay: None),
        response_loader=loader,
    )
    result = client.get_object("2026abc")

    assert result.provenance.status is CheckStatus.ERROR
    assert result.provenance.matches == ()
    assert result.value is None
    assert result.safe_clear is False
    assert result.provenance.attempts == 1
    assert len(requests) == 1


def test_identity_verified_reply_records_version_and_unchanged_digest() -> None:
    reply = {"objname": "2026abc", "photometry": [], "name_prefix": "AT"}
    client = TNSObjectClient(
        TNSCredentials("fixture-key", "1", "fixture-bot"),
        response_loader=lambda request, timeout: json.dumps(
            {"id_code": "200", "data": {"reply": reply}}
        ).encode(),
    )

    result = client.get_object(" 2026abc ")

    assert result.provenance.status is CheckStatus.MATCH
    assert result.provenance.matches == ("2026abc",)
    assert result.provenance.query["object_name"] == "2026abc"
    assert result.provenance.service_version == "tns-get-object.v2"
    assert result.provenance.response_digest == digest_value(reply)
    assert result.value == reply
