from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from test_archive_cohort_assets import snapshot
from test_authenticated_workflow import principal
from test_research_qualification import rehash, study_data

from siderea.ledger import OutcomeLedger
from siderea.operations.broker_store import BrokerArchive
from siderea.operations.observability import OperationsLedger
from siderea.operations.recovery import check_sqlite_recovery
from siderea.promotion import PromotionSignoffRegistry, evaluate_promotion
from siderea.research.injection import run_injection_recovery
from siderea.research.qualification import bind_benchmark


def test_promotion_recomputes_evidence_and_rejects_retrospective_or_unrelated_results(tmp_path):
    # All data are synthetic contract fixtures. No live qualification is claimed.
    study, benchmark, cohort = study_data()
    ledger = OutcomeLedger(tmp_path / "outcomes.sqlite")
    cohort["capture_mode"] = "prospective"
    for row in cohort["records"]:
        row["capture_mode"] = "prospective"
        row["recorded_at"] = row["enrolled_at"]
        ledger.upsert_candidate(
            row["candidate_id"],
            campaign="test",
            state="review",
            version_digest=row["candidate_version"],
            payload={"review_policy": {"required_reviewers": 1}},
        )
        outcome = ledger.record_outcome(
            row["candidate_id"],
            candidate_version=row["candidate_version"],
            outcome="synthetic",
            evidence=row["outcomes"][0]["evidence"],
        )
        row["outcomes"] = [asdict(outcome)]
    cohort["as_of"] = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
    cohort["records"][0]["selected"] = True
    cohort["selected_count"] = 1
    for name, role in (("screen", "screener"), ("review", "reviewer")):
        person = principal(tmp_path, name, [role])
        ledger.add_review(
            "a",
            candidate_version="a" * 64,
            reviewer=person.principal_id,
            principal=person,
            role=role,
            verdict="approve",
            reason="Synthetic contract test",
        )
    rehash(cohort, "cohort_digest")
    bound = bind_benchmark(benchmark, cohort, study)
    injected = run_injection_recovery(
        pd.DataFrame(
            {
                "source_id": ["test"] * 50,
                "time": [i / 10 for i in range(50)],
                "flux": [0] * 50,
                "flux_error": [1] * 50,
            }
        ),
        amplitudes_sigma=[5],
        trials_per_amplitude=100,
    )
    injected.update(protocol_digest=study.protocol_digest, study_id=study.study_id)
    rehash(injected, "result_digest")
    broker = BrokerArchive(tmp_path / "broker.sqlite")
    broker.archive_snapshot(snapshot(tmp_path, 1), stream="test", cursor="1", watermark_mjd=1)
    ops = OperationsLedger(tmp_path / "ops.sqlite")
    recovery = check_sqlite_recovery(ledger.path)
    ops.record_recovery_drill("sqlite-backup", passed=recovery.pop("passed"), evidence=recovery)
    paths = {name: tmp_path / f"{name}.json" for name in ("cohort", "benchmark", "injection")}

    def evaluate():
        for name, value in (("cohort", cohort), ("benchmark", bound), ("injection", injected)):
            paths[name].write_text(json.dumps(value))
        return evaluate_promotion(
            study,
            cohort_export=paths["cohort"],
            outcome_ledger=ledger,
            benchmark=paths["benchmark"],
            injection=paths["injection"],
            fixture_directory=tmp_path / "absent-fixtures",
            broker_archive=broker,
            asset_directory=tmp_path / "absent-assets",
            operations_ledger=ops,
            signoff_registry=PromotionSignoffRegistry(tmp_path / "signoffs.sqlite"),
        )

    report = evaluate()
    gates = {item["gate"]: item["passed"] for item in report["gates"]}
    assert gates["prospective_matured_cohort"]
    # Two test entities cannot establish the preregistered useful-effect bound.
    assert not gates["rolling_origin_effect"]
    effect = next(item for item in report["gates"] if item["gate"] == "rolling_origin_effect")
    assert "lower confidence bound" in effect["detail"]
    assert gates["matched_filter_diagnostic"]
    assert gates["authenticated_exact_version_reviews"] and gates["verified_broker_replay"]
    assert gates["observability_and_recovery"]
    assert not gates["recorded_service_fixture_coverage"]
    assert not gates["asset_integrity_and_completeness"]
    assert report["ready"] is False and report["status"] == "blocked"
    assert report["schema"] == "siderea.promotion_report.v2"
    assert report["readiness_scope"] == "local_evidence_review_not_scientific_or_production_release"
    cohort["capture_mode"] = "retrospective_reconstruction"
    rehash(cohort, "cohort_digest")
    rejected = evaluate()
    assert not next(g for g in rejected["gates"] if g["gate"] == "prospective_matured_cohort")[
        "passed"
    ]
    assert not next(g for g in rejected["gates"] if g["gate"] == "rolling_origin_effect")["passed"]
    injected["protocol_digest"] = "wrong-study"
    rehash(injected, "result_digest")
    assert not next(g for g in evaluate()["gates"] if g["gate"] == "matched_filter_diagnostic")[
        "passed"
    ]


def test_signoff_rejects_untrusted_principal(tmp_path):
    study, _, _ = study_data()
    person = principal(tmp_path, "signer", ["science_signoff"])
    with pytest.raises(ValueError, match="not trusted"):
        PromotionSignoffRegistry(tmp_path / "signoffs.sqlite").add(
            study,
            evidence_digest="a" * 64,
            area="science",
            verdict="approve",
            rationale="Synthetic test",
            principal=person,
        )
