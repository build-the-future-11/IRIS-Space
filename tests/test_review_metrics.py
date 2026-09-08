from __future__ import annotations

from siderea.ledger import OutcomeLedger
from siderea.review.metrics import outcome_summary, outcome_summary_html


def test_current_version_denominator_labels_and_disagreement(tmp_path):
    ledger = OutcomeLedger(tmp_path / "ledger.sqlite")
    assert outcome_summary(ledger)["campaigns"] == []
    for name in ("a", "b", "c"):
        ledger.upsert_candidate(
            name, campaign="<test>", state="review", version_digest="v1", payload={}
        )
    for reviewer, verdict in (("alice", "approve"), ("bob", "reject")):
        ledger.add_review(
            "a",
            candidate_version="v1",
            reviewer=reviewer,
            role="reviewer",
            verdict=verdict,
            reason="test",
        )
    ledger.record_outcome("a", candidate_version="v1", outcome="test", evidence={"binary_label": 1})
    ledger.record_outcome(
        "b", candidate_version="v1", outcome="uncertain", evidence={"binary_label": True}
    )
    report = outcome_summary(ledger)
    stats = report["campaigns"][0]
    assert stats["candidates"] == 3 and stats["outcomes_observed"] == 2
    assert stats["outcomes_missing"] == 1 and stats["binary_labeled"] == 1
    assert stats["review_yield"] == 1 and stats["reviewed_labeled"] == 1
    assert stats["disagreements"] == 1 and stats["median_first_review_hours"] >= 0
    assert "&lt;test&gt;" in outcome_summary_html(report)
    ledger.add_review(
        "a",
        candidate_version="v1",
        reviewer="bob",
        role="reviewer",
        verdict="approve",
        reason="resolved",
    )
    assert outcome_summary(ledger)["campaigns"][0]["disagreements"] == 0
    ledger.upsert_candidate("a", campaign="<test>", state="review", version_digest="v2", payload={})
    current = outcome_summary(ledger)["campaigns"][0]
    assert current["review_events"] == 0 and current["outcomes_missing"] == 2
    assert current["review_yield"] is None
