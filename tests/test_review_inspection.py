from copy import deepcopy

import pytest

from siderea.ledger import OutcomeLedger
from siderea.review.inspection import evidence_inbox, inbox_html, plot_panel, version_comparison


def test_plot_controls_filter_without_changing_evidence():
    rows = [
        {"mjd": 1.0, "survey": "test", "band": "g", "flux": 3},
        {"mjd": 2.0, "survey": "test", "band": "r", "flux": 4},
    ]
    before = deepcopy(rows)
    html = plot_panel(rows, "a/b", {"start": "1.5", "band": "r"})
    assert "1 of 2 observations" in html and "/candidate/a%2Fb" in html
    assert "Reset plot" in html and "r — flux" in html
    assert rows == before
    assert "0 of 2 observations" in plot_panel(rows, "a", {"end": "0"})
    for values in ({"start": "nan"}, {"start": "3", "end": "1"}, {"fake": "x"}):
        with pytest.raises(ValueError):
            plot_panel(rows, "a", values)


def test_version_difference_preserves_observation_multiplicity_and_escapes(tmp_path):
    ledger = OutcomeLedger(tmp_path / "ledger.sqlite")
    a, b = {"mjd": 1, "flux": 1}, {"mjd": 2, "flux": 5}
    ledger.upsert_candidate(
        "example",
        campaign="test",
        state="review",
        version_digest="old",
        payload={"observations": [a, a], "external_checks": [{"status": "pending"}]},
    )
    ledger.upsert_candidate(
        "example",
        campaign="test",
        state="review",
        version_digest="new",
        payload={"observations": [a, b], "external_checks": [{"status": "<script>bad</script>"}]},
    )
    before = ledger.candidate("example")
    html = version_comparison(ledger, "example", "old")
    assert "Added observations: 1" in html and "Removed or replaced observations: 1" in html
    assert "Changed: external_checks" in html and "&lt;script&gt;" in html
    assert "<script>" not in html and "version=old" in html and "version=new" in html
    assert ledger.candidate("example") == before
    assert "unchanged" in version_comparison(ledger, "example", "new")
    assert "unavailable" in version_comparison(ledger, "example", "missing")


def test_inbox_uses_actual_preflight_without_mutating_evidence(tmp_path):
    from test_authenticated_workflow import candidate

    ledger, record = candidate(tmp_path)
    before = ledger.candidate(record["candidate_id"])
    report = evidence_inbox(ledger)
    item = next(row for row in report["items"] if row["candidate_id"] == record["candidate_id"])
    assert item["candidate_version"] == record["candidate_version"]
    assert item["reasons"]
    assert not any("malformed" in reason for reason in item["reasons"])
    assert "cannot dismiss" in inbox_html(report)
    assert ledger.candidate(record["candidate_id"]) == before
    assert ledger.reviews_for(record["candidate_id"]) == []
    assert evidence_inbox(ledger, page=2)["items"] == []
    with pytest.raises(ValueError):
        evidence_inbox(ledger, page=0)


def test_inbox_keeps_malformed_evidence_blocked(tmp_path):
    ledger = OutcomeLedger(tmp_path / "ledger.sqlite")
    ledger.upsert_candidate("broken", campaign="test", state="review", payload={})
    assert "malformed" in evidence_inbox(ledger)["items"][0]["reasons"][0]
