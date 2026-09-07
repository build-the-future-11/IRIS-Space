"""Small, local-only candidate review service backed by the IRIS ledger.

The server records human decisions; it deliberately has no endpoint that can
submit a discovery report or trigger follow-up observations. A per-process
anti-CSRF token is required for every state-changing request.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from urllib.parse import parse_qs, quote, unquote, urlparse, urlsplit

from iris.ledger import (
    ADJUDICATION_VERDICTS,
    REVIEW_ROLES,
    REVIEW_VERDICTS,
    AdjudicationRecord,
    OutcomeLedger,
    ReviewRecord,
)

MAX_FORM_BYTES = 64 * 1024
MAX_FORM_FIELDS = 16
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "frame-ancestors 'none'; base-uri 'none'"
)


def _response_security_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": CONTENT_SECURITY_POLICY,
        "Cross-Origin-Resource-Policy": "same-origin",
        "Referrer-Policy": "no-referrer",
    }


def _parse_form(body: bytes) -> dict[str, list[str]]:
    try:
        return parse_qs(
            body.decode("utf-8"),
            keep_blank_values=True,
            max_num_fields=MAX_FORM_FIELDS,
            strict_parsing=True,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("malformed review form") from exc


def _loopback_host_header(host_header: str | None, *, expected_port: int) -> bool:
    """Reject DNS-rebinding Host headers before disclosing the CSRF token."""

    if not isinstance(host_header, str) or not host_header.strip():
        return False
    try:
        parsed = urlsplit(f"//{host_header.strip()}")
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return False
    hostname = parsed.hostname.casefold()
    if hostname != "localhost":
        try:
            if not ip_address(hostname).is_loopback:
                return False
        except ValueError:
            return False
    return port is None or port == expected_port


def _require_exact_form_fields(
    form: dict[str, list[str]],
    expected: frozenset[str],
) -> None:
    if set(form) != expected or any(len(values) != 1 for values in form.values()):
        raise ValueError("review form fields are missing, duplicated, or unknown")


@dataclass(frozen=True, slots=True)
class ReviewService:
    server: ThreadingHTTPServer
    csrf_token: str


def _page(title: str, body: str) -> bytes:
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'">
<title>{escape(title)}</title>
<style>
body{{font:16px system-ui;max-width:1050px;margin:2rem auto;padding:0 1rem;color:#172033}}
a{{color:#1756a9}}table{{border-collapse:collapse;width:100%}}
th,td{{text-align:left;border-bottom:1px solid #d8deea;padding:.55rem;vertical-align:top}}
label{{display:block;margin:.8rem 0}}
input,select,textarea{{font:inherit;width:100%;max-width:45rem}}
textarea{{min-height:7rem}}.notice{{background:#fff4cf;padding:1rem;border-left:5px solid #d89b00}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6fa;padding:1rem}}
</style></head><body><h1>{escape(title)}</h1>{body}</body></html>"""
    return document.encode("utf-8")


def _candidate_rows(candidates: list[dict[str, object]]) -> str:
    if not candidates:
        return "<p>No candidates are currently in the ledger.</p>"
    rows = "".join(
        "<tr>"
        f'<td><a href="/candidate/{quote(str(item["candidate_id"]), safe="")}">'
        f"{escape(str(item['candidate_id']))}</a></td>"
        f"<td>{escape(str(item['campaign']))}</td>"
        f"<td>{escape(str(item['state']))}</td>"
        f"<td>{escape(str(item['last_seen']))}</td>"
        "</tr>"
        for item in candidates
    )
    return (
        '<p class="notice">Review support only. This service cannot submit reports.</p>'
        "<table><thead><tr><th>Candidate</th><th>Campaign</th><th>State</th>"
        f"<th>Last seen</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _candidate_page(
    candidate: dict[str, object],
    reviews: Sequence[ReviewRecord],
    token: str,
    adjudications: Sequence[AdjudicationRecord] = (),
) -> str:
    candidate_id = str(candidate["candidate_id"])
    candidate_version = str(candidate.get("version_digest", ""))
    payload = json.dumps(
        candidate.get("payload", {}),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    review_rows = (
        "".join(
            "<tr>"
            f"<td>{escape(str(review.created_at))}</td>"
            f"<td><code>{escape(str(review.candidate_version) or 'legacy/unbound')}</code></td>"
            f"<td>{escape(str(review.reviewer))}</td>"
            f"<td>{escape(str(review.role))}</td>"
            f"<td>{escape(str(review.verdict))}</td>"
            f"<td>{escape(str(review.reason))}</td>"
            "</tr>"
            for review in reviews
        )
        or '<tr><td colspan="6">No reviews recorded.</td></tr>'
    )
    role_options = "".join(
        f'<option value="{escape(role)}">{escape(role)}</option>' for role in sorted(REVIEW_ROLES)
    )
    verdict_options = "".join(
        f'<option value="{escape(verdict)}">{escape(verdict)}</option>'
        for verdict in sorted(REVIEW_VERDICTS)
    )
    adjudication_rows = (
        "".join(
            "<tr>"
            f"<td>{escape(str(record.created_at))}</td>"
            f"<td><code>{escape(str(record.candidate_version))}</code></td>"
            f"<td>{escape(str(record.adjudicator))}</td>"
            f"<td>{escape(str(record.verdict))}</td>"
            f"<td>{escape(str(record.reason))}</td>"
            "</tr>"
            for record in adjudications
        )
        or '<tr><td colspan="5">No scientific adjudications recorded.</td></tr>'
    )
    adjudication_options = "".join(
        f'<option value="{escape(verdict)}">{escape(verdict)}</option>'
        for verdict in sorted(ADJUDICATION_VERDICTS)
    )
    return f"""
<p><a href="/">← queue</a></p>
<p class="notice">Every decision needs a named reviewer and a reason. A separate
screener and reviewer are required before reporting preflight can pass.</p>
    <dl><dt>Campaign</dt><dd>{escape(str(candidate["campaign"]))}</dd>
    <dt>State</dt><dd>{escape(str(candidate["state"]))}</dd>
    <dt>Current version</dt><dd><code>{escape(candidate_version)}</code></dd></dl>
<h2>Candidate payload</h2><pre>{escape(payload)}</pre>
<h2>Review history</h2>
<table><thead><tr><th>Time</th><th>Candidate version</th><th>Person</th><th>Role</th>
<th>Verdict</th>
<th>Reason</th></tr></thead><tbody>{review_rows}</tbody></table>
<h2>Record a decision</h2>
<form method="post" action="/review">
<input type="hidden" name="csrf_token" value="{escape(token)}">
<input type="hidden" name="candidate_id" value="{escape(candidate_id)}">
<input type="hidden" name="candidate_version" value="{escape(candidate_version)}">
<label>Reviewer identity <input name="reviewer" required maxlength="120"></label>
<label>Role <select name="role">{role_options}</select></label>
<label>Verdict <select name="verdict">{verdict_options}</select></label>
<label>Scientific rationale <textarea name="reason" required maxlength="8000"></textarea></label>
<button type="submit">Record immutable review event</button>
</form>
<h2>Catalogue-context adjudication</h2>
<table><thead><tr><th>Time</th><th>Candidate version</th><th>Adjudicator</th>
<th>Verdict</th><th>Reason</th></tr></thead><tbody>{adjudication_rows}</tbody></table>
<form method="post" action="/adjudication">
<input type="hidden" name="csrf_token" value="{escape(token)}">
<input type="hidden" name="candidate_id" value="{escape(candidate_id)}">
<input type="hidden" name="candidate_version" value="{escape(candidate_version)}">
<label>Adjudicator identity <input name="adjudicator" required maxlength="120"></label>
<label>Verdict <select name="verdict">{adjudication_options}</select></label>
<label>Scientific rationale <textarea name="reason" required maxlength="8000"></textarea></label>
<button type="submit">Record version-bound scientific adjudication</button>
</form>"""


def build_review_service(
    ledger: OutcomeLedger,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    csrf_token: str | None = None,
    allow_remote: bool = False,
    bind_and_activate: bool = True,
) -> ReviewService:
    """Construct, but do not start, a review server.

    Remote binding is rejected unless explicitly opted in. IRIS does not add
    transport authentication, so production deployments should put a real
    authenticated gateway in front rather than using ``allow_remote`` alone.
    """

    if host not in LOOPBACK_HOSTS and not allow_remote:
        raise ValueError("non-loopback review binding requires allow_remote=True")
    if not 0 <= port <= 65_535:
        raise ValueError("port must be within [0, 65535]")
    token = csrf_token or secrets.token_urlsafe(32)
    if len(token) < 16:
        raise ValueError("csrf_token must contain at least 16 characters")

    class Handler(BaseHTTPRequestHandler):
        server_version = "IRISReview/0.1"

        def _trusted_host(self) -> bool:
            if allow_remote:
                return True
            bound_port = getattr(self.server, "server_port", None)
            if isinstance(bound_port, bool) or not isinstance(bound_port, int):
                return False
            return _loopback_host_header(
                self.headers.get("Host"),
                expected_port=bound_port,
            )

        def _reject_untrusted_host(self) -> bool:
            if self._trusted_host():
                return False
            self.close_connection = True
            self._send(
                HTTPStatus.MISDIRECTED_REQUEST,
                _page("Invalid host", "<p>The request Host is not the local review service.</p>"),
            )
            return True

        def _send(self, status: HTTPStatus, content: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            for name, value in _response_security_headers().items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if self._reject_untrusted_host():
                return
            path = urlparse(self.path).path
            if path == "/":
                candidates = ledger.list_candidates(limit=500)
                content = _page("IRIS review queue", _candidate_rows(candidates))
                self._send(HTTPStatus.OK, content)
                return
            prefix = "/candidate/"
            if path.startswith(prefix):
                candidate_id = unquote(path[len(prefix) :])
                candidate = ledger.candidate(candidate_id)
                if candidate is None:
                    content = _page("Not found", "<p>Unknown candidate.</p>")
                    self._send(HTTPStatus.NOT_FOUND, content)
                    return
                body = _candidate_page(
                    candidate,
                    ledger.reviews_for(candidate_id),
                    token,
                    ledger.adjudications_for(candidate_id),
                )
                self._send(HTTPStatus.OK, _page(f"IRIS candidate {candidate_id}", body))
                return
            self._send(HTTPStatus.NOT_FOUND, _page("Not found", "<p>Unknown route.</p>"))

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            if self._reject_untrusted_host():
                return
            request_path = urlparse(self.path).path
            if request_path not in {"/review", "/adjudication"}:
                self._send(HTTPStatus.NOT_FOUND, _page("Not found", "<p>Unknown route.</p>"))
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if not 0 < length <= MAX_FORM_BYTES:
                content = _page("Invalid request", "<p>Review form is empty or too large.</p>")
                self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, content)
                return
            content_type = self.headers.get_content_type()
            if content_type != "application/x-www-form-urlencoded":
                content = _page("Invalid request", "<p>Unsupported review form encoding.</p>")
                self._send(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, content)
                return
            try:
                form = _parse_form(self.rfile.read(length))
                shared_fields = {
                    "csrf_token",
                    "candidate_id",
                    "candidate_version",
                    "verdict",
                    "reason",
                }
                actor_field = "reviewer" if request_path == "/review" else "adjudicator"
                route_fields = {"role"} if request_path == "/review" else set()
                _require_exact_form_fields(
                    form,
                    frozenset({*shared_fields, actor_field, *route_fields}),
                )
            except ValueError:
                content = _page("Invalid request", "<p>Malformed review form.</p>")
                self._send(HTTPStatus.BAD_REQUEST, content)
                return

            def value(name: str) -> str:
                return form.get(name, [""])[0]

            if not secrets.compare_digest(value("csrf_token"), token):
                self._send(HTTPStatus.FORBIDDEN, _page("Forbidden", "<p>Invalid form token.</p>"))
                return
            candidate_id = value("candidate_id")
            if ledger.candidate(candidate_id) is None:
                self._send(HTTPStatus.NOT_FOUND, _page("Not found", "<p>Unknown candidate.</p>"))
                return
            try:
                if request_path == "/review":
                    ledger.add_review(
                        candidate_id,
                        reviewer=value("reviewer"),
                        role=value("role"),
                        verdict=value("verdict"),
                        reason=value("reason"),
                        candidate_version=value("candidate_version"),
                    )
                else:
                    ledger.add_adjudication(
                        candidate_id,
                        adjudicator=value("adjudicator"),
                        verdict=value("verdict"),
                        reason=value("reason"),
                        candidate_version=value("candidate_version"),
                    )
            except ValueError as exc:
                content = _page("Invalid review", f"<p>{escape(str(exc))}</p>")
                self._send(HTTPStatus.BAD_REQUEST, content)
                return
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/candidate/{quote(candidate_id, safe='')}")
            for name, header_value in _response_security_headers().items():
                self.send_header(name, header_value)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            print(f"IRIS review {self.client_address[0]} - {format % args}")

    server = ThreadingHTTPServer(
        (host, port),
        Handler,
        bind_and_activate=bind_and_activate,
    )
    return ReviewService(server=server, csrf_token=token)


def serve_review(
    ledger: OutcomeLedger,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """Serve the local review queue until interrupted."""

    service = build_review_service(ledger, host=host, port=port)
    raw_address, bound_port = service.server.server_address[:2]
    address = (
        raw_address.decode("ascii", errors="backslashreplace")
        if isinstance(raw_address, bytes)
        else raw_address
    )
    print(f"IRIS review server: http://{address}:{bound_port}/")
    try:
        service.server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.server.server_close()


__all__ = [
    "CONTENT_SECURITY_POLICY",
    "ReviewService",
    "_loopback_host_header",
    "_require_exact_form_fields",
    "build_review_service",
    "serve_review",
]
