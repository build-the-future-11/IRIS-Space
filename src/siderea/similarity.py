"""Small, dependency-light cosine index for scientific analogue retrieval."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path
from typing import BinaryIO

import numpy as np
from numpy.typing import ArrayLike, NDArray

from siderea.atomic import atomic_create_binary

Float32Array = NDArray[np.float32]


@dataclass(frozen=True)
class Neighbor:
    candidate_id: str
    similarity: float
    label: str = ""


class EmbeddingIndex:
    def __init__(self) -> None:
        self.ids: list[str] = []
        self.labels: list[str] = []
        self.embeddings = np.empty((0, 0), dtype=np.float32)
        self.provenance: dict[str, str] = {}

    @staticmethod
    def _normalize(values: ArrayLike) -> Float32Array:
        # Normalize in float64 with per-row max scaling. Direct float32 norms
        # can overflow for large but finite embeddings or underflow for small
        # ones even though cosine similarity is invariant to that scale.
        array = np.asarray(values, dtype=np.float64)
        if array.ndim == 1:
            array = array[None, :]
        if array.ndim != 2 or array.shape[1] < 1 or not np.isfinite(array).all():
            raise ValueError("embeddings must be a finite, non-empty 2D matrix")
        row_scales = np.max(np.abs(array), axis=1, keepdims=True)
        if np.any(row_scales == 0):
            raise ValueError("zero-norm embeddings cannot define cosine similarity")
        scaled = array / row_scales
        norms = np.linalg.norm(scaled, axis=1, keepdims=True)
        if not np.isfinite(norms).all() or np.any(norms == 0):
            raise ValueError("embeddings cannot be normalized safely")
        normalized: Float32Array = (scaled / norms).astype(np.float32)
        return normalized

    def fit(
        self,
        candidate_ids: Sequence[str],
        embeddings: ArrayLike,
        labels: Sequence[str] | None = None,
        provenance: Mapping[str, str] | None = None,
    ) -> EmbeddingIndex:
        matrix = np.asarray(embeddings, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[0] < 1 or len(candidate_ids) != matrix.shape[0]:
            raise ValueError("candidate_ids and non-empty 2D embeddings must have matching rows")
        if labels is not None and len(labels) != len(candidate_ids):
            raise ValueError("labels must match candidate_ids")
        new_ids = [str(value).strip() for value in candidate_ids]
        if any(not value for value in new_ids) or len(set(new_ids)) != len(new_ids):
            raise ValueError("candidate_ids must be non-empty and unique")
        new_labels = [str(value) for value in labels] if labels is not None else [""] * len(new_ids)
        normalized = self._normalize(matrix)
        normalized_provenance = {
            str(key).strip(): str(value).strip() for key, value in dict(provenance or {}).items()
        }
        if any(not key or not value for key, value in normalized_provenance.items()):
            raise ValueError("embedding provenance keys and values must be non-empty")
        if normalized_provenance:
            query_required = {"encoder_sha256", "token_contract_sha256"}
            if not query_required.issubset(normalized_provenance):
                raise ValueError(
                    "embedding provenance needs encoder_sha256 and token_contract_sha256"
                )
            invalid_digests = [
                name
                for name, value in normalized_provenance.items()
                if name.endswith("_sha256") and not re.fullmatch(r"[0-9a-fA-F]{64}", value)
            ]
            if invalid_digests:
                raise ValueError(
                    "embedding provenance has invalid SHA-256 value(s): "
                    f"{', '.join(sorted(invalid_digests))}"
                )
        self.ids = new_ids
        self.labels = new_labels
        self.embeddings = normalized
        self.provenance = normalized_provenance
        return self

    def query(
        self,
        embedding: ArrayLike,
        *,
        k: int = 5,
        exclude_id: str = "",
        provenance: Mapping[str, str] | None = None,
    ) -> list[Neighbor]:
        """Return nearest neighbors with candidate-ID-deterministic score ties.

        Equal cosine scores are ordered by case-folded candidate ID and then by
        the original ID.  Thus fit insertion order cannot change a tied result.
        A provenance-bearing index additionally requires the query vector's
        encoder and token-contract digests and rejects mismatches.
        """

        if isinstance(k, bool) or not isinstance(k, (int, np.integer)) or k < 0:
            raise ValueError("k must be a non-negative integer")
        if k == 0:
            return []
        if self.embeddings.size == 0:
            return []
        if self.provenance:
            required = {"encoder_sha256", "token_contract_sha256"}
            supplied = {
                str(key).strip(): str(value).strip()
                for key, value in dict(provenance or {}).items()
            }
            if not required.issubset(supplied):
                raise ValueError("query provenance needs encoder_sha256 and token_contract_sha256")
            for name in required:
                expected = self.provenance.get(name, "")
                actual = supplied[name]
                if not re.fullmatch(r"[0-9a-fA-F]{64}", actual) or not compare_digest(
                    expected.casefold(), actual.casefold()
                ):
                    raise ValueError(f"query {name} does not match the embedding index")
        query = np.asarray(embedding, dtype=np.float64)
        if query.ndim != 1:
            raise ValueError("query embedding must be one-dimensional")
        vector = self._normalize(query)[0]
        if vector.shape[0] != self.embeddings.shape[1]:
            raise ValueError("embedding dimension does not match index")
        scores = self.embeddings @ vector
        order = sorted(
            range(len(self.ids)),
            key=lambda index: (
                -float(scores[index]),
                self.ids[index].casefold(),
                self.ids[index],
            ),
        )
        neighbors: list[Neighbor] = []
        for index in order:
            if exclude_id and self.ids[index] == exclude_id:
                continue
            neighbors.append(
                Neighbor(
                    self.ids[index],
                    float(np.clip(scores[index], -1.0, 1.0)),
                    self.labels[index],
                )
            )
            if len(neighbors) >= max(0, k):
                break
        return neighbors

    def save(self, path: Path) -> None:
        if not self.ids or self.embeddings.ndim != 2 or self.embeddings.shape[0] != len(self.ids):
            raise RuntimeError("fit the embedding index before saving it")
        required = {"encoder_sha256", "token_contract_sha256", "dataset_snapshot_sha256"}
        if not required.issubset(self.provenance) or any(
            not re.fullmatch(r"[0-9a-fA-F]{64}", self.provenance[name]) for name in required
        ):
            raise RuntimeError(
                "persisted embedding indexes require SHA-256 encoder, token-contract, "
                "and dataset-snapshot provenance"
            )

        def write_index(handle: BinaryIO) -> None:
            np.savez_compressed(
                handle,
                ids=np.asarray(self.ids),
                labels=np.asarray(self.labels),
                embeddings=self.embeddings,
                format=np.asarray("siderea.embedding_index.v2"),
                provenance_json=np.asarray(json.dumps(self.provenance, sort_keys=True)),
            )

        atomic_create_binary(path, write_index)

    @classmethod
    def load(cls, path: Path) -> EmbeddingIndex:
        with np.load(path, allow_pickle=False) as payload:
            if (
                "format" not in payload.files
                or str(payload["format"]) != "siderea.embedding_index.v2"
            ):
                raise ValueError("unsupported or unprovenanced embedding index")
            ids = payload["ids"].astype(str).tolist()
            labels = payload["labels"].astype(str).tolist()
            embeddings = np.asarray(payload["embeddings"], dtype=np.float32)
            try:
                provenance = json.loads(str(payload["provenance_json"]))
            except (KeyError, json.JSONDecodeError) as exc:
                raise ValueError("embedding index provenance is missing or invalid") from exc
        if not isinstance(provenance, Mapping):
            raise ValueError("embedding index provenance must be an object")
        index = cls().fit(ids, embeddings, labels, provenance=provenance)
        required = {"encoder_sha256", "token_contract_sha256", "dataset_snapshot_sha256"}
        if not required.issubset(index.provenance) or any(
            not re.fullmatch(r"[0-9a-fA-F]{64}", index.provenance[name]) for name in required
        ):
            raise ValueError("embedding index provenance is incomplete")
        return index
