from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

torch = pytest.importorskip("torch")

from siderea.cli import main  # noqa: E402


def _protocol(tmp_path: Path) -> Path:
    payload = json.loads(Path("configs/space-jepa-2-protocol.json").read_text())
    payload["model"].update(
        {
            "quaternion_width": 4,
            "encoder_blocks": 1,
            "attention_heads": 2,
            "predictor_blocks": 1,
            "dropout": 0.0,
        }
    )
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload))
    return path


def _batches(seed: int) -> list[dict[str, object]]:
    generator = torch.Generator().manual_seed(seed)
    return [
        {
            "context_tokens": torch.randn((2, 3, 5), generator=generator),
            "context_mask": torch.ones((2, 3), dtype=torch.bool),
            "target_tokens": torch.randn((2, 4, 2, 5), generator=generator),
            "target_mask": torch.ones((2, 4, 2), dtype=torch.bool),
            "example_ids": ["a", "b"],
        }
    ]


def _photometry(path: Path) -> None:
    rows = []
    for entity_index in range(6):
        base = 60_000.0 + entity_index * 100.0
        for observation_index, offset in enumerate((0.0, 1.0, 2.0, 4.0, 8.0, 15.0)):
            rows.append(
                {
                    "entity_id": f"object-{entity_index}",
                    "observation_id": f"object-{entity_index}-{observation_index}",
                    "observed_at_mjd": base + offset,
                    "available_at_mjd": base + offset,
                    "band": "g" if observation_index % 2 == 0 else "r",
                    "value": 20.0 - 0.1 * observation_index,
                    "value_error": 0.05,
                    "is_detection": True,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_prepare_cli_writes_causal_entity_disjoint_batches(tmp_path: Path) -> None:
    protocol = _protocol(tmp_path)
    photometry = tmp_path / "photometry.csv"
    _photometry(photometry)
    output = tmp_path / "prepared"
    assert (
        main(
            [
                "space-jepa-2-prepare",
                str(protocol),
                str(photometry),
                str(output),
                "--batch-size",
                "2",
            ]
        )
        == 0
    )
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["schema"] == "siderea.space_jepa_v2_tensor_batches.v1"
    assert (output / "train.pt").is_file()
    assert (output / "validation.pt").is_file()
    assert (output / "test.pt").is_file()


def test_train_infer_memory_benchmark_and_shadow_cli(tmp_path: Path) -> None:
    protocol = _protocol(tmp_path)
    train = tmp_path / "train.pt"
    validation = tmp_path / "validation.pt"
    inference = tmp_path / "inference.pt"
    torch.save(_batches(1), train)
    torch.save(_batches(2), validation)
    torch.save(_batches(3), inference)
    checkpoint = tmp_path / "model.pt"
    assert (
        main(
            [
                "space-jepa-2-train",
                str(protocol),
                str(train),
                str(validation),
                str(checkpoint),
                "--input-dim",
                "5",
                "--epochs",
                "1",
                "--seed",
                "17",
            ]
        )
        == 0
    )
    evaluation = tmp_path / "evaluation.json"
    assert (
        main(
            [
                "space-jepa-2-infer",
                str(checkpoint),
                str(inference),
                str(evaluation),
            ]
        )
        == 0
    )

    entries = tmp_path / "entries.json"
    entries.write_text(
        json.dumps(
            [
                {
                    "entry_id": "m1",
                    "key": [[0.0, 0.0, 0.0, 0.0]],
                    "residual": [[0.1, 0.0, 0.0, 0.0]],
                    "source_group": "train-a",
                    "cutoff_mjd": 60000.0,
                    "population": "A",
                    "calibration": "cal-v1",
                }
            ]
        )
    )
    memory = tmp_path / "memory.json"
    assert main(["space-jepa-2-memory-build", str(entries), str(memory)]) == 0

    routing_input = tmp_path / "routing-input.json"
    routing_input.write_text(
        json.dumps(
            {
                "base_forecast": [[[0.0, 0.0, 0.0, 0.0]]],
                "observed_target": [[[0.2, 0.0, 0.0, 0.0]]],
                "covariance": torch.eye(4).tolist(),
                "memory_query": [[0.0, 0.0, 0.0, 0.0]],
                "query_source_group": "held-out",
                "query_cutoff_mjd": 60_001.0,
                "population": "A",
                "calibration": "cal-v1",
                "physics_residual": None,
                "physics_status": "physics_not_identifiable",
                "score_weights": {"corrected_surprise": 1.0},
            }
        )
    )
    routed = tmp_path / "routed.json"
    assert (
        main(
            [
                "space-jepa-2-route",
                str(routing_input),
                str(routed),
                "--memory",
                str(memory),
            ]
        )
        == 0
    )
    assert json.loads(routed.read_text())["memory_route"]["status"] == "applied"

    benchmark_input = tmp_path / "benchmark.csv"
    pd.DataFrame(
        {
            "entity": ["a", "b", "c", "d"],
            "label": [1, 0, 1, 0],
            "incumbent": [4.0, 3.0, 2.0, 1.0],
            "aqpm": [4.0, 1.0, 3.0, 2.0],
        }
    ).to_csv(benchmark_input, index=False)
    benchmark = tmp_path / "benchmark.json"
    assert (
        main(
            [
                "space-jepa-2-benchmark",
                str(benchmark_input),
                str(benchmark),
                "--entity",
                "entity",
                "--label",
                "label",
                "--scores",
                "incumbent",
                "aqpm",
                "--review-budget",
                "2",
                "--bootstrap-repeats",
                "100",
            ]
        )
        == 0
    )

    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps(
            {
                "schema": "siderea.candidates.v1",
                "candidates": [{"candidate_id": "a"}, {"candidate_id": "b"}],
            }
        )
    )
    shadow = tmp_path / "shadow.json"
    assert (
        main(
            [
                "space-jepa-2-shadow-assemble",
                str(candidates),
                str(evaluation),
                str(shadow),
            ]
        )
        == 0
    )
    assert json.loads(shadow.read_text())["reporting_authorized"] is False
