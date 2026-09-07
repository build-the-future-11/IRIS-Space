from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from iris.ledger import OutcomeLedger
from iris.review.dossier import write_candidate_dossier
from iris.review.server import (
    _candidate_page,
    _loopback_host_header,
    _parse_form,
    _require_exact_form_fields,
    _response_security_headers,
    build_review_service,
)


class ReviewServerTests(unittest.TestCase):
    def test_review_form_binds_the_version_that_was_rendered(self) -> None:
        page = _candidate_page(
            {
                "candidate_id": "ZTF-review",
                "campaign": "ispy",
                "state": "needs_review",
                "version_digest": "evidence-v1",
                "payload": {},
            },
            [],
            "csrf-token-long-enough",
        )

        self.assertIn('name="candidate_version" value="evidence-v1"', page)
        self.assertIn("Current version", page)
        self.assertIn("<code>evidence-v1</code>", page)
        self.assertIn('action="/adjudication"', page)

    def test_service_defaults_to_loopback_and_uses_long_token(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            service = build_review_service(ledger, port=0, bind_and_activate=False)
            try:
                self.assertEqual(service.server.server_address[0], "127.0.0.1")
                self.assertGreaterEqual(len(service.csrf_token), 16)
            finally:
                service.server.server_close()

    def test_remote_binding_requires_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            with self.assertRaisesRegex(ValueError, "non-loopback"):
                build_review_service(ledger, host="0.0.0.0", port=0)

    def test_review_pages_cannot_be_cross_origin_framed(self) -> None:
        headers = _response_security_headers()
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIn("base-uri 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")

    def test_malformed_utf8_form_is_rejected_without_handler_crash(self) -> None:
        with self.assertRaisesRegex(ValueError, "malformed"):
            _parse_form(b"\xff")

    def test_loopback_host_validation_rejects_dns_rebinding_and_wrong_ports(self) -> None:
        for value in ("localhost", "127.0.0.1:8765", "[::1]:8765", "127.0.0.2"):
            with self.subTest(value=value):
                self.assertTrue(_loopback_host_header(value, expected_port=8765))
        for value in (
            None,
            "",
            "review.attacker.test:8765",
            "localhost.attacker.test:8765",
            "127.0.0.1:9000",
            "user@localhost:8765",
            "[::1",
        ):
            with self.subTest(value=value):
                self.assertFalse(_loopback_host_header(value, expected_port=8765))

    def test_review_form_rejects_duplicate_missing_and_unknown_fields(self) -> None:
        expected = frozenset({"csrf_token", "candidate_id"})
        _require_exact_form_fields(
            {"csrf_token": ["token"], "candidate_id": ["ZTF-test"]},
            expected,
        )
        for form in (
            {"csrf_token": ["token"]},
            {"csrf_token": ["token", "other"], "candidate_id": ["ZTF-test"]},
            {"csrf_token": ["token"], "candidate_id": ["ZTF-test"], "extra": ["x"]},
        ):
            with self.subTest(form=form), self.assertRaisesRegex(ValueError, "fields"):
                _require_exact_form_fields(form, expected)

    def test_untrusted_host_cannot_read_the_csrf_token(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            service = build_review_service(ledger, port=8765, bind_and_activate=False)
            try:
                handler_class = service.server.RequestHandlerClass
                handler = handler_class.__new__(handler_class)
                handler.server = service.server
                handler.headers = {"Host": "review.attacker.test"}
                handler.close_connection = False
                observed: dict[str, object] = {}
                handler._send = lambda status, content: observed.update(  # type: ignore[method-assign]
                    status=status,
                    content=content,
                )

                self.assertTrue(handler._reject_untrusted_host())
                self.assertEqual(observed["status"], 421)
                self.assertNotIn(service.csrf_token.encode(), observed["content"])
                self.assertTrue(handler.close_connection)
            finally:
                service.server.server_close()

    def test_latest_rejection_blocks_old_approval(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            candidate_version = "review-evidence-v1"
            ledger.upsert_candidate(
                "ZTF-review",
                campaign="ispy",
                state="review",
                payload={},
                version_digest=candidate_version,
            )
            ledger.add_review(
                "ZTF-review",
                candidate_version=candidate_version,
                reviewer="screen-a",
                role="screener",
                verdict="approve",
                reason="initial screen",
            )
            ledger.add_review(
                "ZTF-review",
                candidate_version=candidate_version,
                reviewer="review-b",
                role="reviewer",
                verdict="approve",
                reason="initial review",
            )
            self.assertTrue(ledger.independent_approval("ZTF-review")[0])
            ledger.add_review(
                "ZTF-review",
                candidate_version=candidate_version,
                reviewer="review-b",
                role="reviewer",
                verdict="reject",
                reason="new image shows an artifact",
            )
            approved, reason = ledger.independent_approval("ZTF-review")
            self.assertFalse(approved)
            self.assertIn("unresolved rejection", reason)

    def test_dossier_candidate_id_cannot_escape_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = write_candidate_dossier(
                root / "dossiers",
                candidate={"candidate_id": "../../outside"},
                features={},
                checks=[],
            )
            self.assertTrue(path.resolve().is_relative_to((root / "dossiers").resolve()))
            self.assertFalse((root / "outside").exists())

    def test_dossier_is_immutable_and_bound_to_candidate_version(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "dossiers"
            candidate = {"candidate_id": "ZTF-versioned", "candidate_version": "a" * 64}

            first = write_candidate_dossier(
                root,
                candidate=candidate,
                features={"n_detections": 3},
                checks=[],
            )
            payload = json.loads((first.parent / "dossier.json").read_text(encoding="utf-8"))

            self.assertEqual(payload["schema"], "iris.review_dossier.v2")
            self.assertEqual(payload["candidate_version"], "a" * 64)
            self.assertEqual(len(payload["dossier_digest"]), 64)
            with self.assertRaisesRegex(FileExistsError, "will not be overwritten"):
                write_candidate_dossier(
                    root,
                    candidate=candidate,
                    features={"n_detections": 4},
                    checks=[],
                )

            second = write_candidate_dossier(
                root,
                candidate={**candidate, "candidate_version": "b" * 64},
                features={"n_detections": 4},
                checks=[],
            )
            self.assertNotEqual(first.parent, second.parent)


if __name__ == "__main__":
    unittest.main()
