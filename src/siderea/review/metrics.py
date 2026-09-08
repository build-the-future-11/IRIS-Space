"""Operational review/outcome measurements with explicit current-version denominators."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from html import escape
from statistics import median
from typing import Any

from siderea.ledger import OutcomeLedger
from siderea.provenance import digest_value


def outcome_summary(ledger: OutcomeLedger) -> dict[str, Any]:
    """Summarize current evidence versions using latest exact-version outcomes.

    Yield is conditional on reviewed, explicitly binary-labeled records. It is
    not population precision and missing outcomes are never counted negative.
    """
    with ledger.connect() as db:
        rows = db.execute(
            """
            WITH review_totals AS (
                SELECT candidate_id, candidate_version, COUNT(*) AS events,
                       MIN(created_at) AS first_review
                FROM reviews GROUP BY candidate_id, candidate_version
            ), active_reviews AS (
                SELECT candidate_id, candidate_version,
                       MAX(verdict='approve') AS has_approval,
                       MAX(verdict='reject') AS has_rejection
                FROM reviews WHERE id IN (
                    SELECT MAX(id) FROM reviews
                    GROUP BY candidate_id, candidate_version, reviewer, role
                ) GROUP BY candidate_id, candidate_version
            )
            SELECT c.campaign, c.candidate_id, v.recorded_at,
                   COALESCE(r.events, 0) AS review_events, r.first_review,
                   COALESCE(a.has_approval, 0) * COALESCE(a.has_rejection, 0) AS disagreement,
                   o.id AS outcome_id, o.evidence_json
            FROM candidates c
            JOIN candidate_versions v ON v.candidate_id=c.candidate_id
                AND v.version_digest=c.version_digest
            LEFT JOIN review_totals r ON r.candidate_id=c.candidate_id
                AND r.candidate_version=c.version_digest
            LEFT JOIN active_reviews a ON a.candidate_id=c.candidate_id
                AND a.candidate_version=c.version_digest
            LEFT JOIN outcomes o ON o.id=(
                SELECT MAX(id) FROM outcomes
                WHERE candidate_id=c.candidate_id AND candidate_version=c.version_digest
            ) ORDER BY c.campaign, c.candidate_id
            """
        ).fetchall()
    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[str(row["campaign"])].append(row)
    campaigns: list[dict[str, Any]] = []
    for campaign, candidates in grouped.items():
        result: dict[str, Any] = {
            "campaign": campaign,
            "candidates": len(candidates),
            "review_events": 0,
            "reviewed_candidates": 0,
            "outcomes_observed": 0,
            "outcomes_missing": 0,
            "binary_labeled": 0,
            "positive_outcomes": 0,
            "reviewed_labeled": 0,
            "reviewed_positive": 0,
            "disagreements": 0,
            "invalid_latency_records": 0,
        }
        latencies: list[float] = []
        for row in candidates:
            reviewed = row["review_events"] > 0
            result["review_events"] += row["review_events"]
            result["reviewed_candidates"] += int(reviewed)
            result["disagreements"] += row["disagreement"]
            observed = row["outcome_id"] is not None
            result["outcomes_observed"] += int(observed)
            result["outcomes_missing"] += int(not observed)
            evidence = json.loads(row["evidence_json"]) if observed else {}
            label = evidence.get("binary_label") if isinstance(evidence, dict) else None
            if type(label) is int and label in {0, 1}:
                result["binary_labeled"] += 1
                result["positive_outcomes"] += label
                if reviewed:
                    result["reviewed_labeled"] += 1
                    result["reviewed_positive"] += label
            if reviewed:
                try:
                    reviewed_at = datetime.fromisoformat(row["first_review"])
                    recorded_at = datetime.fromisoformat(row["recorded_at"])
                    if reviewed_at.utcoffset() is None or recorded_at.utcoffset() is None:
                        raise ValueError("naive latency timestamps")
                    hours = (reviewed_at - recorded_at).total_seconds() / 3600
                    if hours < 0:
                        raise ValueError("negative review latency")
                    latencies.append(hours)
                except (TypeError, ValueError):
                    result["invalid_latency_records"] += 1
        result["median_first_review_hours"] = median(latencies) if latencies else None
        result["review_yield"] = (
            result["reviewed_positive"] / result["reviewed_labeled"]
            if result["reviewed_labeled"]
            else None
        )
        campaigns.append(result)
    report = {
        "schema": "siderea.outcome_summary.v1",
        "scope": "current_evidence_versions_in_this_ledger_not_complete_population",
        "yield_definition": "positive / explicitly_binary_labeled_among_reviewed_current_versions",
        "campaigns": campaigns,
    }
    report["report_digest"] = digest_value(report)
    return report


def outcome_summary_html(report: dict[str, Any]) -> str:
    body = (
        '<p><a href="/">← queue</a></p><p>Current evidence versions in this ledger only. '
        "Yield is conditional on reviewed records with explicit binary labels. "
        "Missing outcomes are not negatives; this is not population precision.</p>"
    )
    if not report["campaigns"]:
        return body + "<p>No candidates have been recorded yet.</p>"
    for campaign in report["campaigns"]:
        fields = [
            ("Candidates", campaign["candidates"]),
            ("Reviewed", campaign["reviewed_candidates"]),
            ("Review events", campaign["review_events"]),
            ("Unresolved disagreements", campaign["disagreements"]),
            ("Observed outcomes", campaign["outcomes_observed"]),
            ("Missing outcomes", campaign["outcomes_missing"]),
            ("Binary-labeled reviewed records", campaign["reviewed_labeled"]),
            ("Positive reviewed outcomes", campaign["reviewed_positive"]),
            (
                "Conditional review yield",
                "unavailable"
                if campaign["review_yield"] is None
                else f"{campaign['review_yield']:.1%}",
            ),
            (
                "Median first-review hours",
                "unavailable"
                if campaign["median_first_review_hours"] is None
                else f"{campaign['median_first_review_hours']:.2f}",
            ),
        ]
        body += f"<section><h2>{escape(campaign['campaign'])}</h2><dl>"
        body += "".join(
            f"<dt>{escape(name)}</dt><dd>{escape(str(value))}</dd>" for name, value in fields
        )
        body += "</dl></section>"
    return body
