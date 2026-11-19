"""Constructed artifact contracts; these are not astronomical results."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from siderea.cli import main
from siderea.provenance import digest_value
from siderea.research.space_jepa_v2_pipeline import assemble_space_jepa_v2_shadow_evidence


def _artifacts() -> tuple[dict, dict]:
    candidates = {
        "schema": "siderea.candidates.v1",
        "candidates": [{"candidate_id": "a"}, {"candidate_id": "b"}],
    }
    evaluation = {
        "schema": "siderea.space_jepa_v2_evaluation.v1",
        "row_count": 2,
        "rows": [
            {
                "example_id": "a",
                "horizons_days": [1.0, 3.0],
                "mean_absolute_latent_error": [0.1, 0.2],
            },
            {
                "example_id": "b",
                "horizons_days": [1.0, 3.0],
                "mean_absolute_latent_error": [0.3, 0.4],
            },
        ],
    }
    return candidates, evaluation


def _assemble(candidates: dict, evaluation: dict) -> dict:
    signed = {**evaluation, "result_digest": digest_value(evaluation)}
    return assemble_space_jepa_v2_shadow_evidence(candidates, signed)


@pytest.mark.parametrize("conflicting", [False, True])
def test_duplicate_evaluation_identity_cannot_overwrite_evidence(conflicting: bool) -> None:
    candidates, evaluation = _artifacts()
    duplicate = deepcopy(evaluation["rows"][0])
    if conflicting:
        duplicate["mean_absolute_latent_error"] = [100.0, 200.0]
    evaluation["rows"].append(duplicate)
    evaluation["row_count"] = 3
    with pytest.raises(ValueError, match="evaluation identities.*unique"):
        _assemble(candidates, evaluation)


@pytest.mark.parametrize("identity", [None, True, 7, "", "   "])
@pytest.mark.parametrize("side", ["candidate", "evaluation"])
def test_identities_cannot_be_coerced_or_blank(identity: object, side: str) -> None:
    candidates, evaluation = _artifacts()
    if side == "candidate":
        candidates["candidates"][0]["candidate_id"] = identity
        evaluation["rows"][0]["example_id"] = str(identity)
    else:
        candidates["candidates"][0]["candidate_id"] = str(identity)
        evaluation["rows"][0]["example_id"] = identity
    with pytest.raises(ValueError, match="identit"):
        _assemble(candidates, evaluation)


@pytest.mark.parametrize("count", [None, True, 1, 3, 2.0, "2"])
def test_declared_evaluation_row_count_must_match_exactly(count: object) -> None:
    candidates, evaluation = _artifacts()
    evaluation["row_count"] = count
    with pytest.raises(ValueError, match="row_count"):
        _assemble(candidates, evaluation)


@pytest.mark.parametrize("errors", [[], ["0.1", "0.2"], [True, 0.2], [-0.1, 0.2], [0.1]])
def test_review_priorities_require_one_nonnegative_number_per_horizon(errors: list) -> None:
    candidates, evaluation = _artifacts()
    evaluation["rows"][0]["mean_absolute_latent_error"] = errors
    with pytest.raises(ValueError, match="horizon errors"):
        _assemble(candidates, evaluation)


@pytest.mark.parametrize("horizons", [[], [1.0, 1.0], [0.0, 3.0], [True, 3.0], ["1", 3.0]])
def test_horizon_identity_is_positive_numeric_and_unique(horizons: list) -> None:
    candidates, evaluation = _artifacts()
    evaluation["rows"][0]["horizons_days"] = horizons
    with pytest.raises(ValueError, match="horizons"):
        _assemble(candidates, evaluation)


def test_valid_reordered_evidence_keeps_candidate_association_and_shadow_boundary() -> None:
    candidates, evaluation = _artifacts()
    evaluation["rows"].reverse()
    before = deepcopy((candidates, evaluation))
    report = _assemble(candidates, evaluation)
    assert [(row["candidate_id"], row["review_priority"]) for row in report["rows"]] == [
        ("a", 0.2),
        ("b", 0.4),
    ]
    assert report["reporting_authorized"] is False
    assert report["mode"] == "shadow_only"
    assert (candidates, evaluation) == before


@pytest.mark.parametrize("duplicate", [False, True])
def test_shadow_cli_preserves_inputs_and_publishes_only_valid_evidence(
    tmp_path: Path, duplicate: bool
) -> None:
    candidates, evaluation = _artifacts()
    if duplicate:
        evaluation["rows"].append(deepcopy(evaluation["rows"][0]))
        evaluation["row_count"] = 3
    evaluation["result_digest"] = digest_value(evaluation)
    candidate_path = tmp_path / "candidates.json"
    evaluation_path = tmp_path / "evaluation.json"
    output = tmp_path / "shadow.json"
    candidate_path.write_text(json.dumps(candidates))
    evaluation_path.write_text(json.dumps(evaluation))
    before = candidate_path.read_bytes(), evaluation_path.read_bytes()
    code = main(
        [
            "space-jepa-2-shadow-assemble",
            str(candidate_path),
            str(evaluation_path),
            str(output),
        ]
    )
    assert (candidate_path.read_bytes(), evaluation_path.read_bytes()) == before
    if duplicate:
        assert code == 2
        assert not output.exists()
    else:
        assert code == 0
        report = json.loads(output.read_text())
        assert report["reporting_authorized"] is False
        assert report["candidate_count"] == 2
        assert [row["review_priority"] for row in report["rows"]] == [0.2, 0.4]
