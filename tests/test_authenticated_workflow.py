from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from siderea.config import ReviewConfig, load_config
from siderea.identity import create_principal_assertion, verify_principal_assertion
from siderea.ledger import OutcomeLedger
from siderea.pipeline import analyze_csv
from siderea.review.evidence import light_curve_html
from siderea.review.server import _candidate_page

KEY = b"synthetic-test-signing-key-32-bytes!"


def principal(tmp_path, subject, roles):
    now = datetime.now(UTC)
    path = tmp_path / f"{subject}.json"
    create_principal_assertion(
        path,
        {
            "issuer": "test",
            "subject": subject,
            "display_name": subject,
            "roles": roles,
            "issued_at": (now - timedelta(minutes=1)).isoformat(),
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "audience": "siderea",
            "assurance_level": "synthetic-test",
            "nonce": subject,
        },
        signing_key=KEY,
    )
    return verify_principal_assertion(path, verification_key=KEY)


def candidate(tmp_path, *, input_path=None):
    config = replace(
        load_config(),
        review=ReviewConfig(
            require_authenticated=True,
            trusted_assertion_key_ids=(sha256(KEY).hexdigest(),),
        ),
    )
    result = analyze_csv(
        input_path if input_path is not None else Path("examples/photometry.csv"),
        config,
        output_dir=tmp_path / "runs",
        ledger_path=tmp_path / "ledger.sqlite",
    )
    record = json.loads(result.candidates_path.read_text())["candidates"][0]
    return OutcomeLedger(result.ledger_path), record


def test_strict_candidate_requires_current_trusted_independent_principals(tmp_path):
    ledger, record = candidate(tmp_path)
    identity, version = record["candidate_id"], record["candidate_version"]
    arguments = dict(candidate_version=version, verdict="approve", reason="synthetic test")
    with pytest.raises(ValueError, match="authenticated"):
        ledger.add_review(identity, reviewer="typed-name", role="screener", **arguments)
    screener = principal(tmp_path, "alice", ["screener", "reviewer", "adjudicator"])
    reviewer = principal(tmp_path, "bob", ["reviewer"])
    ledger.add_review(
        identity, reviewer=screener.principal_id, role="screener", principal=screener, **arguments
    )
    assert not ledger.independent_approval(identity)[0]
    with pytest.raises(ValueError, match="expired"):
        ledger.add_review(
            identity,
            reviewer=reviewer.principal_id,
            role="reviewer",
            principal=replace(reviewer, expires_at="2000-01-01T00:00:00+00:00"),
            **arguments,
        )
    with pytest.raises(ValueError, match="trusted"):
        ledger.add_review(
            identity,
            reviewer=reviewer.principal_id,
            role="reviewer",
            principal=replace(reviewer, key_id="f" * 64),
            **arguments,
        )
    with pytest.raises(ValueError, match="differs"):
        ledger.add_review(
            identity, reviewer="someone-else", role="reviewer", principal=reviewer, **arguments
        )
    ledger.add_review(
        identity, reviewer=reviewer.principal_id, role="reviewer", principal=reviewer, **arguments
    )
    assert ledger.independent_approval(identity)[0]
    with pytest.raises(ValueError, match="authenticated"):
        ledger.add_adjudication(
            identity,
            candidate_version=version,
            adjudicator="name",
            verdict="clear_context",
            reason="test",
        )
    ledger.add_adjudication(
        identity,
        candidate_version=version,
        adjudicator=screener.principal_id,
        principal=screener,
        verdict="clear_context",
        reason="test",
    )
    assert ledger.manual_adjudication(identity, candidate_version=version)[0]
    with ledger.connect() as db:
        stored = json.loads(
            db.execute("SELECT principal_json FROM decision_authentication LIMIT 1").fetchone()[0]
        )
    assert stored["assertion_envelope"]["signature"]


def test_expired_or_tampered_assertions_fail(tmp_path):
    person = principal(tmp_path, "person", ["reviewer"])
    envelope = json.loads((tmp_path / "person.json").read_text())
    envelope["assertion"]["roles"] = ["screener"]
    with pytest.raises(ValueError, match="digest"):
        verify_principal_assertion(envelope, verification_key=KEY)
    with pytest.raises(ValueError, match="expired"):
        verify_principal_assertion(
            tmp_path / "person.json",
            verification_key=KEY,
            now=datetime.fromisoformat(person.expires_at) + timedelta(seconds=1),
        )


def test_authenticated_review_page_has_bound_identity_and_real_observations(tmp_path):
    ledger, record = candidate(tmp_path)
    person = principal(tmp_path, "person", ["reviewer"])
    page = _candidate_page(
        ledger.candidate(record["candidate_id"]), [], "test-token", principal=person
    )
    assert 'value="test::person" readonly' in page
    assert "Authenticated session" in page
    assert "Decision evidence" in page and "<svg" in page
    assert 'value="screener"' not in page
    assert "disabled><legend>Scientific adjudication" in page
    assert "adjudicator session is required" in page
    no_session = _candidate_page(ledger.candidate(record["candidate_id"]), [], "test-token")
    assert "disabled><legend>Version-bound review" in no_session


def test_channel_plot_escapes_labels_and_shows_limits():
    rendered = light_curve_html(
        [
            {
                "mjd": 60000,
                "survey": "<script>",
                "band": "g",
                "magnitude": 19,
                "magnitude_error": 0.1,
            },
            {
                "mjd": 60001,
                "survey": "<script>",
                "band": "g",
                "is_detection": False,
                "limiting_magnitude": 21,
            },
            {"mjd": 60002, "survey": "other", "band": "g", "flux": -2, "flux_error": 1},
        ]
    )
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert rendered.count("<svg") == 2
    assert " limit" in rendered and "±" in rendered


def test_queue_pagination_search_and_state_filters(tmp_path):
    ledger = OutcomeLedger(tmp_path / "ledger.sqlite")
    for index in range(5):
        ledger.upsert_candidate(
            f"A{index}", campaign="test", state="review" if index % 2 else "blocked", payload={}
        )
    first = ledger.list_candidates(limit=2)
    second = ledger.list_candidates(limit=2, offset=2)
    assert not {row["candidate_id"] for row in first} & {row["candidate_id"] for row in second}
    assert len(ledger.list_candidates(state="review")) == 2
    assert ledger.list_candidates(search="A3")[0]["candidate_id"] == "A3"
    assert ledger.list_candidates(search="' OR 1=1 --") == []


def test_extreme_measurement_preview_has_explanatory_fallback():
    rendered = light_curve_html(
        [
            {"mjd": -1e308, "flux": -1e308, "flux_error": 1e308},
            {"mjd": 1e308, "flux": 1e308, "flux_error": 1e308},
        ]
    )
    assert "numeric range" in rendered
    assert "<svg" not in rendered
