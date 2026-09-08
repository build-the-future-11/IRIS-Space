from __future__ import annotations

import socket
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

from test_authenticated_workflow import candidate, principal

from siderea.review.server import build_review_service


def test_real_http_review_validation_persistence_and_session_expiry(tmp_path):
    ledger, record = candidate(tmp_path)
    reviewer = principal(tmp_path, "http-reviewer", ["reviewer", "adjudicator"])
    session = [reviewer]

    def load_principal():
        if not session:
            raise OSError("assertion file became unreadable")
        return session[0]

    service = build_review_service(ledger, port=0, principal_loader=load_principal)
    thread = Thread(target=service.server.serve_forever, daemon=True)
    thread.start()
    port = service.server.server_port

    def request(method, path, fields=None, host=None):
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            if host:
                headers["Host"] = host
            connection.request(method, path, urlencode(fields) if fields else None, headers)
            response = connection.getresponse()
            return response.status, response.read().decode(), dict(response.getheaders())
        finally:
            connection.close()

    try:
        identity, version = record["candidate_id"], record["candidate_version"]
        status, html, headers = request("GET", f"/candidate/{identity}")
        assert status == 200 and "<svg" in html and reviewer.principal_id in html
        assert headers["X-Frame-Options"] == "DENY"
        assert request("GET", "/", host="attacker.example")[0] == 421
        assert request("GET", "/?page=0")[0] == 400
        assert request("GET", "/candidate/missing")[0] == 404
        assert request("GET", f"/candidate/{identity}?start=nan")[0] == 400
        assert request("GET", f"/candidate/{identity}?band=g&band=r")[0] == 400
        filtered_status, filtered_html, _ = request("GET", f"/candidate/{identity}?end=0")
        assert filtered_status == 200 and "0 of " in filtered_html
        inbox_status, inbox_body, _ = request("GET", "/inbox")
        assert inbox_status == 200 and identity in inbox_body
        assert request("GET", "/inbox?page=0")[0] == 400
        assert request("POST", "/inbox", {"dismiss": identity})[0] == 404
        dashboard_status, dashboard_html, _ = request("GET", "/outcomes")
        assert dashboard_status == 200 and "Missing outcomes" in dashboard_html
        fields = {
            "csrf_token": service.csrf_token,
            "candidate_id": identity,
            "candidate_version": version,
            "reviewer": reviewer.principal_id,
            "role": "reviewer",
            "verdict": "approve",
            "reason": "Synthetic HTTP integration test",
        }
        assert request("POST", "/review", {**fields, "csrf_token": "wrong"})[0] == 403
        assert request("POST", "/review", {**fields, "reviewer": "forged-name"})[0] == 400
        stale_status, stale_html, _ = request(
            "POST", "/review", {**fields, "candidate_version": "stale"}
        )
        assert stale_status == 400
        assert fields["reason"] in stale_html and "Unsubmitted rationale" in stale_html
        assert "Open current evidence" in stale_html
        assert not ledger.reviews_for(identity)
        status, _, headers = request("POST", "/review", fields)
        assert status == 303 and headers["Location"] == f"/candidate/{identity}"
        assert ledger.reviews_for(identity)[0].reviewer == reviewer.principal_id
        adjudication = {
            key: value for key, value in fields.items() if key not in {"reviewer", "role"}
        }
        adjudication.update(adjudicator=reviewer.principal_id, verdict="clear_context")
        assert request("POST", "/adjudication", adjudication)[0] == 303
        assert ledger.manual_adjudication(identity, candidate_version=version)[0]
        lines = Path("examples/photometry.csv").read_text().splitlines(keepends=True)
        assert lines[1].startswith(identity + ",")
        corrected = tmp_path / "corrected.csv"
        corrected.write_text("".join([lines[0], *lines[2:]]))
        candidate(tmp_path, input_path=corrected)
        rejected, comparison, _ = request("POST", "/review", fields)
        assert rejected == 400 and "Removed or replaced observations: 1" in comparison
        assert fields["reason"] in comparison and "Download submitted evidence" in comparison
        assert len(ledger.reviews_for(identity)) == 1
        session.clear()
        assert request("GET", "/")[0] == 401
        assert request("GET", "/inbox")[0] == 401
        assert request("POST", "/review", fields)[0] == 401
        assert len(ledger.reviews_for(identity)) == 1
    finally:
        service.server.shutdown()
        service.server.server_close()
        thread.join(timeout=5)


def test_ipv6_service_uses_ipv6_socket(tmp_path):
    from siderea.ledger import OutcomeLedger

    service = build_review_service(
        OutcomeLedger(tmp_path / "ledger.sqlite"), host="::1", port=0, bind_and_activate=False
    )
    try:
        assert service.server.address_family == socket.AF_INET6
    finally:
        service.server.server_close()


def test_evidence_download_is_complete_version_bound_and_session_protected(tmp_path):
    import json

    from siderea.ledger import OutcomeLedger

    ledger = OutcomeLedger(tmp_path / "download.sqlite")
    observations = [{"mjd": 60000 + i, "flux": i} for i in range(700)]
    ledger.upsert_candidate(
        "example",
        campaign="test",
        state="review",
        version_digest="v1",
        payload={"observations": observations},
    )
    ledger.upsert_candidate(
        "example",
        campaign="test",
        state="review",
        version_digest="v2",
        payload={"observations": []},
    )
    reviewer = principal(tmp_path, "reader", ["reviewer"])
    session = [reviewer]

    def load():
        if not session:
            raise ValueError("expired")
        return session[0]

    service = build_review_service(ledger, port=0, principal_loader=load)
    thread = Thread(target=service.server.serve_forever, daemon=True)
    thread.start()

    def get(path):
        connection = HTTPConnection("127.0.0.1", service.server.server_port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    try:
        status, body, headers = get("/evidence/example?version=v1")
        assert status == 200
        assert json.loads(body)["payload"]["observations"] == observations
        assert json.loads(body)["version_digest"] == "v1"
        assert headers["Content-Type"].startswith("application/json")
        assert headers["Content-Disposition"].startswith("attachment;")
        assert get("/evidence/example")[0] == 400
        assert get("/evidence/example?version=v1&version=v2")[0] == 400
        assert get("/evidence/example?version=unknown")[0] == 404
        session.clear()
        assert get("/evidence/example?version=v1")[0] == 401
    finally:
        service.server.shutdown()
        service.server.server_close()
        thread.join(timeout=5)
