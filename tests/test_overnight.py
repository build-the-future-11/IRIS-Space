from __future__ import annotations

import json

import pandas as pd
import pytest

from siderea.provenance import digest_value
from siderea.research.overnight import (
    freeze_reference_cohort,
    merge_transient_searches,
    shard_flux_table,
    verify_reference_embeddings,
    verify_shard_manifest,
)
from siderea.research.transients import search_flux_table


def _sealed(payload):
    result = dict(payload)
    result.pop("result_digest", None)
    result["result_digest"] = digest_value(result)
    return result


def _flux(*sources):
    rows = []
    for index, source in enumerate(sources):
        for epoch in range(4):
            rows.append(
                {
                    "source_id": source,
                    "survey": "test",
                    "band": "g",
                    "mjd": float(epoch),
                    "flux": float(epoch if index % 2 else 0),
                    "flux_error": 1.0,
                }
            )
    return pd.DataFrame(rows)


def test_entity_safe_sharding_and_manifest_verification(tmp_path):
    frame = pd.concat([_flux("a", "b"), _flux("c", "d").assign(band="r")])
    output = tmp_path / "shards"
    manifest = shard_flux_table(frame, output, max_channels=2)
    assert manifest["shard_count"] == 2
    assert verify_shard_manifest(output) == manifest
    assert sorted(len(item["entities"]) for item in manifest["shards"]) == [2, 2]

    first = output / manifest["shards"][0]["path"]
    first.write_text(first.read_text() + "\n")
    with pytest.raises(ValueError, match="differs from its digest"):
        verify_shard_manifest(output)


def test_transient_merge_rejects_contract_mismatch_and_duplicate_entities():
    left = search_flux_table(
        _flux("a", "b"),
        null_trials=99,
        object_universe_size=4,
        planned_looks=2,
    )
    right = search_flux_table(
        _flux("c", "d"),
        null_trials=99,
        object_universe_size=4,
        planned_looks=2,
    )
    merged = merge_transient_searches([left, right])
    assert merged["shard_count"] == 2
    assert merged["campaign_inference"]["searched_object_count"] == 4
    assert [row["source_id"] for row in merged["objects"]] == ["a", "b", "c", "d"]
    assert merged["result_digest"]
    with pytest.raises(ValueError, match="repeat entity"):
        merge_transient_searches([left, left])
    mismatched = json.loads(json.dumps(right))
    mismatched["campaign_inference"]["planned_looks"] = 3
    mismatched = _sealed(mismatched)
    with pytest.raises(ValueError, match="planned_looks"):
        merge_transient_searches([left, mismatched])


def test_frozen_reference_cohort_binds_dataset_and_entities():
    records = [
        {"entity_id": "Ref-A", "prediction_cutoff_mjd": 3.0, "times": [1.0, 2.0]},
        {"entity_id": "Ref-B", "prediction_cutoff_mjd": 4.0, "times": [2.0, 4.0]},
    ]
    cohort = freeze_reference_cohort(
        records,
        dataset_sha256="a" * 64,
        cohort_id="nightly-controls-v1",
        selection_policy="all eligible controls frozen before scoring",
    )
    embeddings = {
        "dataset_snapshot_sha256": "a" * 64,
        "rows": [{"entity_id": "ref-a"}, {"entity_id": "REF-B"}],
    }
    assert verify_reference_embeddings(cohort, embeddings)["cohort_id"] == ("nightly-controls-v1")
    altered = json.loads(json.dumps(embeddings))
    altered["rows"][1]["entity_id"] = "other"
    with pytest.raises(ValueError, match="frozen cohort"):
        verify_reference_embeddings(cohort, altered)
