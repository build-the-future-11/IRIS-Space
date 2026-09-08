from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from siderea.similarity import EmbeddingIndex


def _tied_neighbor_ids(candidate_ids: list[str], *, exclude_id: str = "") -> list[str]:
    embeddings = np.repeat([[1.0, 0.0]], repeats=len(candidate_ids), axis=0)
    index = EmbeddingIndex().fit(candidate_ids, embeddings)
    return [
        neighbor.candidate_id
        for neighbor in index.query([1.0, 0.0], k=len(candidate_ids), exclude_id=exclude_id)
    ]


def test_equal_similarity_ties_are_independent_of_fit_insertion_order() -> None:
    expected = ["alpha", "middle", "zulu"]

    assert _tied_neighbor_ids(["zulu", "alpha", "middle"]) == expected
    assert _tied_neighbor_ids(["middle", "zulu", "alpha"]) == expected


def test_equal_similarity_ties_remain_deterministic_when_excluding_candidate() -> None:
    assert _tied_neighbor_ids(["zulu", "alpha", "middle"], exclude_id="middle") == [
        "alpha",
        "zulu",
    ]


def test_query_rejects_multiple_vectors_instead_of_silently_using_the_first() -> None:
    index = EmbeddingIndex().fit(["a"], np.asarray([[1.0, 0.0]]))

    with pytest.raises(ValueError, match="one-dimensional"):
        index.query(np.asarray([[1.0, 0.0], [0.0, 1.0]]))


def test_fit_rejects_empty_indexes_and_malformed_digest_provenance() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        EmbeddingIndex().fit([], np.empty((0, 2)))

    with pytest.raises(ValueError, match="invalid SHA-256"):
        EmbeddingIndex().fit(
            ["a"],
            np.asarray([[1.0, 0.0]]),
            provenance={
                "encoder_sha256": "not-a-digest",
                "token_contract_sha256": "b" * 64,
            },
        )


def test_persistence_requires_and_round_trips_embedding_provenance() -> None:
    index = EmbeddingIndex().fit(["a"], np.asarray([[1.0, 0.0]]))
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "index.npz"
        with pytest.raises(RuntimeError, match="provenance"):
            index.save(path)

        provenance = {
            "encoder_sha256": "a" * 64,
            "token_contract_sha256": "b" * 64,
            "dataset_snapshot_sha256": "c" * 64,
        }
        index.fit(["a"], np.asarray([[1.0, 0.0]]), provenance=provenance).save(path)
        with pytest.raises(FileExistsError):
            index.save(path)
        restored = EmbeddingIndex.load(path)

    assert restored.provenance == provenance
    query_provenance = {
        "encoder_sha256": provenance["encoder_sha256"],
        "token_contract_sha256": provenance["token_contract_sha256"],
    }
    assert restored.query([1.0, 0.0], k=1, provenance=query_provenance)[0].candidate_id == "a"


def test_provenance_index_rejects_missing_or_mismatched_query_encoder() -> None:
    provenance = {
        "encoder_sha256": "a" * 64,
        "token_contract_sha256": "b" * 64,
        "dataset_snapshot_sha256": "c" * 64,
    }
    index = EmbeddingIndex().fit(
        ["a"],
        np.asarray([[1.0, 0.0]]),
        provenance=provenance,
    )

    with pytest.raises(ValueError, match="query provenance"):
        index.query([1.0, 0.0])
    with pytest.raises(ValueError, match="encoder_sha256"):
        index.query(
            [1.0, 0.0],
            provenance={
                "encoder_sha256": "d" * 64,
                "token_contract_sha256": "b" * 64,
            },
        )


def test_persistence_reports_missing_required_provenance_with_extra_keys() -> None:
    index = EmbeddingIndex().fit(
        ["a"],
        np.asarray([[1.0, 0.0]]),
        provenance={
            "encoder_sha256": "a" * 64,
            "token_contract_sha256": "b" * 64,
            "extra": "recorded-but-not-a-required-digest",
        },
    )
    with tempfile.TemporaryDirectory() as folder, pytest.raises(RuntimeError, match="provenance"):
        index.save(Path(folder) / "index.npz")
