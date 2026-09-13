#!/usr/bin/env python3
"""Run a deterministic, restartable local scale qualification for shadow search."""

from __future__ import annotations

import argparse
import json
import platform
import resource
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from siderea.provenance import digest_file, digest_value, stable_json
from siderea.research.overnight import (
    merge_transient_searches,
    shard_flux_table,
    verify_shard_manifest,
)
from siderea.research.transients import search_flux_table


def _rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def _workload(entities: int, epochs: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    times = np.arange(epochs, dtype=float)
    pulse = np.exp(-0.5 * ((times - epochs * 0.55) / 2.0) ** 2)
    errors = rng.uniform(0.8, 1.2, size=(entities, epochs))
    signals = (np.arange(entities) % 50 == 0)[:, None] * pulse[None, :] * 7.0
    flux = 20.0 + signals + rng.standard_t(df=5, size=(entities, epochs)) * errors
    entity_ids = np.repeat(np.arange(entities), epochs)
    epoch_ids = np.tile(np.arange(epochs), entities)
    return pd.DataFrame(
        {
            "source_id": [f"scale-{entity:06d}" for entity in entity_ids],
            "survey": "qualification-synthetic",
            "band": "g",
            "mjd": 62000.0 + np.tile(times, entities),
            "flux": flux.ravel(),
            "flux_error": errors.ravel(),
            "observation_id": [
                f"{entity:06d}-{epoch:04d}"
                for entity, epoch in zip(entity_ids, epoch_ids, strict=True)
            ],
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--entities", type=int, default=500)
    parser.add_argument("--epochs", type=int, default=32)
    parser.add_argument("--null-trials", type=int, default=99)
    parser.add_argument("--seed", type=int, default=20260913)
    args = parser.parse_args()
    if args.entities < 2 or args.epochs < 4:
        raise ValueError("qualification requires at least two entities and four epochs")
    if args.entities > 100_000 or args.epochs > 2_048 or args.entities * args.epochs > 10_000_000:
        raise ValueError("qualification workload exceeds the bounded allocation limit")
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    args.output.mkdir(parents=True)

    started = time.perf_counter()
    frame = _workload(args.entities, args.epochs, args.seed)
    generated_at = time.perf_counter()
    manifest = shard_flux_table(frame, args.output / "shards", max_channels=100)
    verified_manifest = verify_shard_manifest(args.output / "shards")

    searches: list[dict[str, Any]] = []
    shard_latencies: list[float] = []
    for shard in verified_manifest["shards"]:
        shard_path = args.output / "shards" / shard["path"]
        result_path = args.output / f"{Path(shard['path']).stem}.search.json"
        shard_started = time.perf_counter()
        result = search_flux_table(
            pd.read_csv(shard_path, dtype={"source_id": "string", "observation_id": "string"}),
            widths=(1.0, 3.0),
            center_count=5,
            null_trials=args.null_trials,
            seed=args.seed,
            object_universe_size=args.entities,
            null_method="wild_residual",
            wild_block_size=2,
        )
        result["input_sha256"] = digest_file(shard_path)
        result.pop("result_digest")
        result["result_digest"] = digest_value(result)
        result_path.write_text(stable_json(result) + "\n", encoding="utf-8")
        searches.append(result)
        shard_latencies.append(time.perf_counter() - shard_started)

    merged = merge_transient_searches(searches)
    (args.output / "merged.json").write_text(stable_json(merged) + "\n", encoding="utf-8")

    resumed = [
        json.loads(path.read_text()) for path in sorted(args.output.glob("shard-*.search.json"))
    ]
    resumed_merge = merge_transient_searches(resumed)
    restart_reproduced = resumed_merge["result_digest"] == merged["result_digest"]

    corrupted = json.loads(json.dumps(searches[0]))
    corrupted["channels"][0]["rows"] += 1
    corruption_detected = False
    try:
        merge_transient_searches([corrupted, *searches[1:]])
    except ValueError:
        corruption_detected = True

    quota_guard_passed = False
    try:
        shard_flux_table(frame.iloc[: args.epochs], args.output / "invalid", max_channels=101)
    except ValueError:
        quota_guard_passed = True

    finished = time.perf_counter()
    artifact_bytes = sum(path.stat().st_size for path in args.output.rglob("*") if path.is_file())
    report: dict[str, Any] = {
        "schema": "siderea.scale_qualification.v1",
        "scientific_scope": "synthetic engineering qualification; no real-sky performance claim",
        "source_sha256": digest_file(Path(__file__)),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "seed": args.seed,
        "entities": args.entities,
        "epochs_per_entity": args.epochs,
        "rows": len(frame),
        "shards": manifest["shard_count"],
        "null_trials": args.null_trials,
        "null_method": "wild_residual",
        "wall_seconds": finished - started,
        "generation_seconds": generated_at - started,
        "search_seconds": sum(shard_latencies),
        "maximum_shard_seconds": max(shard_latencies),
        "entities_per_search_second": args.entities / sum(shard_latencies),
        "peak_rss_bytes": _rss_bytes(),
        "artifact_bytes": artifact_bytes,
        "quota_guard_passed": quota_guard_passed,
        "digest_corruption_detected": corruption_detected,
        "restart_from_completed_shards_reproduced": restart_reproduced,
        "merged_result_digest": merged["result_digest"],
    }
    if not all((quota_guard_passed, corruption_detected, restart_reproduced)):
        raise RuntimeError("scale qualification safety check failed")
    report["result_digest"] = digest_value(report)
    (args.output / "qualification.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
