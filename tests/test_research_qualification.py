from __future__ import annotations

from copy import deepcopy

import pandas as pd
import pytest

from siderea.provenance import digest_value
from siderea.research.benchmark import run_rolling_origin_benchmark
from siderea.research.preregistration import Preregistration
from siderea.research.qualification import bind_benchmark, cohort_labels, valid_interval


def protocol():
    return Preregistration.from_protocol(
        {
            "study_id": "synthetic-test",
            "title": "Synthetic contract test",
            "scientific_question": "Does the binding reject mismatches?",
            "hypotheses": ["test"],
            "cohort": {
                "opens_at": "2026-01-01T00:00:00+00:00",
                "closes_at": "2026-02-01T00:00:00+00:00",
                "matures_at": "2026-03-01T00:00:00+00:00",
                "population": "synthetic",
                "inclusion_criteria": ["test"],
                "exclusion_criteria": [],
            },
            "selection": {
                "pipeline_version": "test",
                "configuration_digest": "a" * 64,
                "eligibility_policy": "triage",
                "review_budget": 1,
                "audit_slots": 0,
            },
            "endpoints": {"primary": "test", "secondary": []},
            "analysis": {
                "reference_score": "baseline",
                "primary_metric": "precision_at_budget",
                "comparison": "model",
                "minimum_useful_effect": 0.1,
                "confidence_level": 0.95,
                "bootstrap_repeats": 100,
                "random_seed": 0,
                "subgroup_fields": [],
                "missing_outcome_policy": "exclude_and_report",
                "minimum_injection_recovery": 0.5,
                "injection_amplitude_sigma": 5,
            },
            "operations": {
                "required_services": ["tns"],
                "minimum_broker_snapshots": 1,
                "require_image_evidence": True,
                "required_recovery_drills": 1,
                "maximum_schema_drifts": 0,
            },
            "governance": {
                "protocol_owner": "test-owner",
                "statistics_reviewer": "test-reviewer",
                "independent_signoffs_required": 2,
                "principal_policy": "authenticated_external",
                "required_signoff_areas": ["science"],
                "trusted_assertion_key_ids": ["b" * 64],
            },
        },
        frozen_at="2025-12-01T00:00:00+00:00",
    )


def rehash(payload, field):
    payload.pop(field, None)
    payload[field] = digest_value(payload)
    return payload


def study_data():
    study = protocol()
    frame = pd.DataFrame(
        {
            "entity": list("abcdef"),
            "time": [1, 1, 2, 2, 3, 3],
            "label": [0, 1, 0, 1, 0, 1],
            "baseline": [0.5] * 6,
            "model": [0, 1, 0, 1, 0, 1],
        }
    )
    result = run_rolling_origin_benchmark(
        frame,
        entity_column="entity",
        time_column="time",
        label_column="label",
        score_columns=["baseline", "model"],
        review_budget=1,
        bootstrap_repeats=100,
    )
    records = []
    for index, entity in enumerate(frame.entity):
        evidence = {"binary_label": index % 2}
        records.append(
            {
                "candidate_id": entity,
                "candidate_version": "a" * 64,
                "protocol_digest": study.protocol_digest,
                "selected": False,
                "eligible": True,
                "enrolled_at": "2026-01-02T00:00:00+00:00",
                "outcomes": [
                    {
                        "candidate_id": entity,
                        "candidate_version": "a" * 64,
                        "recorded_at": "2026-02-02T00:00:00+00:00",
                        "evidence": evidence,
                        "evidence_digest": digest_value(evidence),
                    }
                ],
            }
        )
    cohort = rehash(
        {
            "schema": "siderea.matured_cohort.v1",
            "study_id": study.study_id,
            "protocol_digest": study.protocol_digest,
            "as_of": "2026-03-02T00:00:00+00:00",
            "missing_outcome_policy": "exclude_and_report",
            "enrollment_count": 6,
            "selected_count": 0,
            "missing_outcome_count": 0,
            "records": records,
        },
        "cohort_digest",
    )
    return study, result, cohort


def test_bound_benchmark_roundtrip():
    study, result, cohort = study_data()
    bound = bind_benchmark(result, cohort, study)
    assert bound["cohort_digest"] == cohort["cohort_digest"]
    assert bind_benchmark(bound, cohort, study) == bound


def test_frozen_protocol_serialization_is_independent_and_mutation_rejected(tmp_path):
    from siderea.research.cohort import CohortRegistry

    study, _, cohort = study_data()
    exported = study.to_dict()
    exported["protocol"]["selection"]["review_budget"] = 9
    assert study.protocol["selection"]["review_budget"] == 1
    study.protocol["selection"]["review_budget"] = 9
    with pytest.raises(ValueError, match="digest"):
        cohort_labels(cohort, study)
    with pytest.raises(ValueError, match="digest"):
        CohortRegistry(tmp_path / "registry.sqlite").register(study)


@pytest.mark.parametrize(
    "mutation", ["label", "protocol", "maturity", "duplicate", "outcome_version"]
)
def test_cohort_mismatches_block(mutation):
    study, result, cohort = study_data()
    if mutation == "label":
        outcome = cohort["records"][0]["outcomes"][0]
        outcome["evidence"]["binary_label"] = 1
        outcome["evidence_digest"] = digest_value(outcome["evidence"])
    elif mutation == "protocol":
        cohort["protocol_digest"] = "wrong"
    elif mutation == "maturity":
        cohort["as_of"] = "2026-02-02T00:00:00+00:00"
    elif mutation == "duplicate":
        cohort["records"][1] = deepcopy(cohort["records"][0])
    else:
        cohort["records"][0]["outcomes"][0]["candidate_version"] = "wrong"
    rehash(cohort, "cohort_digest")
    with pytest.raises(ValueError):
        bind_benchmark(result, cohort, study)


@pytest.mark.parametrize(
    "field,value", [("review_budget", 2), ("seed", 19), ("confidence_level", 0.9)]
)
def test_policy_changes_block(field, value):
    study, result, cohort = study_data()
    result[field] = value
    rehash(result, "result_digest")
    with pytest.raises(ValueError, match="differs"):
        bind_benchmark(result, cohort, study)


def test_fabricated_derived_metric_rejected_even_with_new_digest():
    study, result, cohort = study_data()
    result["summary"]["model"]["precision_at_budget"]["delta_confidence_interval"] = [0.9, 1.0]
    rehash(result, "result_digest")
    with pytest.raises(ValueError, match="recomputed"):
        bind_benchmark(result, cohort, study)


def test_unknown_label_is_not_guessed_negative():
    study, _, cohort = study_data()
    outcome = cohort["records"][0]["outcomes"][0]
    outcome["evidence"] = {"classification": "unknown"}
    outcome["evidence_digest"] = digest_value(outcome["evidence"])
    rehash(cohort, "cohort_digest")
    with pytest.raises(ValueError, match="binary_label"):
        cohort_labels(cohort, study)


def test_singleton_blocks_rejected_and_explicit_bins_supported():
    frame = pd.DataFrame(
        {
            "id": list("abcdef"),
            "t": [1.1, 1.2, 2.1, 2.2, 3.1, 3.2],
            "label": [0, 1] * 3,
            "s": [0, 1] * 3,
        }
    )
    args = dict(
        entity_column="id",
        time_column="t",
        label_column="label",
        score_columns=["s"],
        review_budget=1,
        bootstrap_repeats=100,
    )
    with pytest.raises(ValueError, match="two entities"):
        run_rolling_origin_benchmark(frame, **args)
    result = run_rolling_origin_benchmark(frame, **args, time_block_days=1.0)
    assert result["folds"][0]["test_rows"] == 2


def test_protocol_cannot_be_frozen_after_enrollment_opens():
    with pytest.raises(ValueError, match="before"):
        Preregistration.from_protocol(protocol().protocol, frozen_at="2026-01-02T00:00:00+00:00")


def test_injection_rejects_degenerate_epochs_and_mixed_channels():
    from siderea.research.injection import run_injection_recovery

    frame = pd.DataFrame(
        {
            "source_id": ["a"] * 3,
            "time": [1, 1, 2],
            "flux": [1, 1, 1],
            "flux_error": [1, 1, 1],
        }
    )
    with pytest.raises(ValueError, match="three distinct"):
        run_injection_recovery(frame)
    frame["time"] = [1, 2, 3]
    frame["band"] = ["g", "r", "g"]
    with pytest.raises(ValueError, match="one survey/band"):
        run_injection_recovery(frame)


@pytest.mark.parametrize("interval", [[float("inf"), float("inf")], [0.8, 0.2], [True, 1], [-1, 1]])
def test_invalid_intervals(interval):
    assert not valid_interval(interval, lower=0, upper=1)
