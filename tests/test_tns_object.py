from __future__ import annotations

import json

from siderea.clients.tns import TNSCredentials
from siderea.clients.tns_object import TNSObjectClient
from siderea.provenance import CheckStatus


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
