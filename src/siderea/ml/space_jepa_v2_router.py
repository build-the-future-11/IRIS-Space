"""Dual-route evidence assembly for AQPM prediction and anomaly detection."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

import numpy as np

from siderea.provenance import digest_value

from .episodic_memory import EpisodicResidualMemory
from .space_jepa_v2_anomaly import anomaly_components


def route_space_jepa_v2_evidence(
    *,
    base_forecast: Any,
    observed_target: Any,
    covariance: Any,
    memory: EpisodicResidualMemory | None,
    memory_query: Any | None,
    query_source_group: str,
    query_cutoff_mjd: float,
    population: str,
    calibration: str,
    physics_residual: float | None,
    physics_status: str,
    score_weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Assemble inspectable predictive, memory, anomaly and physics routes.

    The memory key and forecast use ``[horizon * channels, 4]`` so the memory
    bank corrects the complete multi-horizon trajectory as one causal object.
    A scalar ranking score is emitted only when frozen non-negative weights are
    supplied by the caller.
    """

    base = np.asarray(base_forecast, dtype=np.float64)
    target = np.asarray(observed_target, dtype=np.float64)
    if base.ndim != 3 or base.shape[-1] != 4 or target.shape != base.shape:
        raise ValueError("base_forecast and observed_target must be equal [horizon, channel, 4]")
    if np.any(~np.isfinite(base)) or np.any(~np.isfinite(target)):
        raise ValueError("forecast and target must be finite")
    if not physics_status.strip():
        raise ValueError("physics_status must not be empty")
    physical = 0.0 if physics_residual is None else float(physics_residual)
    if not math.isfinite(physical) or physical < 0.0:
        raise ValueError("physics_residual must be finite and non-negative when supplied")

    flat_base = base.reshape(-1, 4)
    if memory is None:
        corrected = flat_base.copy()
        memory_payload: dict[str, Any] = {
            "status": "memory_off",
            "supported": False,
            "gate": 0.0,
            "neighbor_ids": [],
            "weights": [],
            "nearest_distance": 0.0,
            "entropy": 0.0,
        }
    else:
        if memory_query is None:
            raise ValueError("memory_query is required when memory is enabled")
        retrieval = memory.retrieve(
            memory_query,
            flat_base,
            query_source_group=query_source_group,
            query_cutoff_mjd=query_cutoff_mjd,
            population=population,
            calibration=calibration,
        )
        corrected = retrieval.corrected
        memory_payload = {
            "status": "applied" if retrieval.supported else "unsupported",
            "supported": retrieval.supported,
            "gate": retrieval.gate,
            "neighbor_ids": list(retrieval.neighbor_ids),
            "weights": list(retrieval.weights),
            "nearest_distance": (
                retrieval.nearest_distance if math.isfinite(retrieval.nearest_distance) else None
            ),
            "entropy": retrieval.entropy,
        }
    corrected_trajectory = corrected.reshape(base.shape)
    diagnostics = anomaly_components(
        target=target.reshape(-1, 4),
        base_prediction=flat_base,
        corrected_prediction=corrected,
        covariance=covariance,
        memory_distance=float(memory_payload["nearest_distance"] or 0.0),
        memory_entropy=float(memory_payload["entropy"]),
        physics_residual=physical,
    )
    components = asdict(diagnostics)
    ranking_score: float | None = None
    frozen_weights: dict[str, float] | None = None
    if score_weights is not None:
        unknown = sorted(set(score_weights) - set(components))
        if unknown:
            raise ValueError(f"score_weights contains unknown anomaly components: {unknown}")
        frozen_weights = {}
        ranking_score = 0.0
        for name, raw_weight in score_weights.items():
            weight = float(raw_weight)
            if not math.isfinite(weight) or weight < 0.0:
                raise ValueError("score weights must be finite and non-negative")
            frozen_weights[name] = weight
            ranking_score += weight * math.log1p(float(components[name]))
    identity = {
        "schema": "siderea.space_jepa_v2_dual_route.v1",
        "base_forecast": base.tolist(),
        "corrected_forecast": corrected_trajectory.tolist(),
        "prediction_route": {
            "status": "evaluated",
            "mean_absolute_latent_error": np.mean(
                np.abs(target - corrected_trajectory), axis=(1, 2)
            ).tolist(),
        },
        "memory_route": memory_payload,
        "anomaly_route": {"status": "evaluated", "components": components},
        "physics_route": {
            "status": physics_status,
            "residual": None if physics_residual is None else physical,
        },
        "ranking_score": ranking_score,
        "score_weights": frozen_weights,
        "reporting_authorized": False,
    }
    return {**identity, "result_digest": digest_value(identity)}


__all__ = ["route_space_jepa_v2_evidence"]
