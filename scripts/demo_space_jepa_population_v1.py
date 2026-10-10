"""One bounded, generated population-input walkthrough; no training or science."""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

import torch

from siderea.ml.space_jepa_population_v1 import MEMBERSHIP_SCHEMA, prepare_population_batches
from siderea.ml.space_jepa_v2 import AQPMJEPA, SpaceJEPA2Config
from siderea.provenance import digest_value


def write_generated_inputs(directory: Path) -> tuple[Path, Path]:
    """Write exactly 64 artificial measurements, six A entities and two B entities."""
    directory.mkdir(parents=True, exist_ok=False)
    rows = []
    entities = []
    for entity_index in range(8):
        population = "source_A" if entity_index < 6 else "source_B"
        entity = f"physical-{entity_index}"
        aliases = [f"survey:{entity_index}", f"catalog:{entity_index}"]
        entities.append(
            {"physical_entity_id": entity, "population": population, "aliases": aliases}
        )
        # B deliberately enrolls before A, so accidentally pooling populations
        # into chronological splitting changes the training population.
        start = 100.0 + 10 * entity_index if entity_index < 6 else 80.0 + entity_index - 6
        for index in range(8):
            observed = start + index
            rows.append(
                {
                    "entity_id": aliases[index % 2],
                    "observation_id": f"observation-{index}",
                    "observed_at_mjd": observed,
                    "available_at_mjd": observed + (0.5 if index == 1 else 0.0),
                    "survey": population,
                    "band": "g" if index % 2 else "r",
                    "calibration_id": "generated-common-scale-v1",
                    "value": [1.0, 2.0, 4.0, 3.0, 6.0, 5.0, 8.0, 7.0][index] + entity_index,
                    "value_error": 0.1,
                    "is_detection": "true",
                    "limiting_value": "",
                }
            )
    csv_path = directory / "photometry.csv"
    with csv_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    membership_path = directory / "membership.json"
    document = {
        "schema": MEMBERSHIP_SCHEMA,
        "purpose": "development",
        "population_a": "source_A",
        "population_b": "source_B",
        "population_basis": "Artificial source labels declared by this generated fixture",
        "measurement": {"value_kind": "flux", "unit": "arbitrary_common_flux_unit"},
        "entities": entities,
    }
    membership_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return csv_path, membership_path


def run_demo(destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    photometry, membership = write_generated_inputs(destination / "generated-inputs")
    prepared = destination / "prepared"
    manifest = prepare_population_batches(
        photometry,
        membership,
        prepared,
        horizons_days=(1.0, 3.0),
        batch_size=4,
    )
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(7)
        model = AQPMJEPA(
            SpaceJEPA2Config(
                input_dim=7,
                quaternion_width=2,
                encoder_blocks=1,
                attention_heads=1,
                predictor_blocks=1,
                dropout=0.0,
                horizons_days=(1.0, 3.0),
                flow_steps=1,
            )
        ).eval()
    before = {name: value.clone() for name, value in model.state_dict().items()}
    outputs = {}
    with torch.no_grad():
        for name in manifest["splits"]:
            batches = torch.load(prepared / f"{name}.pt", weights_only=True, map_location="cpu")
            shapes = []
            for batch in batches:
                prediction = model(batch["context_tokens"], batch["context_mask"])["base_forecast"]
                target = model.encode_targets(batch["target_tokens"], batch["target_mask"])
                if (
                    prediction.shape != target.shape
                    or not bool(torch.isfinite(prediction).all())
                    or not bool(torch.isfinite(target).all())
                ):
                    raise RuntimeError("generated model execution failed shape/finite checks")
                shapes.append(list(prediction.shape))
            outputs[name] = {
                "rows": manifest["splits"][name]["row_count"],
                "forecast_shapes": shapes,
            }
    if any(not torch.equal(before[name], value) for name, value in model.state_dict().items()):
        raise RuntimeError("inference changed persistent model state")
    identity = {
        "schema": "siderea.space_jepa_population_demo.v1",
        "generated_fixture": True,
        "photometry_rows": 64,
        "prepared_result_digest": manifest["result_digest"],
        "model_config": model.config.to_dict(),
        "generated_initialization_seed": 7,
        "model_parameters": sum(parameter.numel() for parameter in model.parameters()),
        "training_steps": 0,
        "persistent_model_state_unchanged": True,
        "partitions": outputs,
        "scientific_execution_authorized": False,
        "interpretation": "Generated input and untrained inference only; no efficacy estimate",
    }
    result = {
        **identity,
        "result_digest": digest_value(identity),
        "wall_seconds": time.monotonic() - start,
    }
    (destination / "demo-receipt.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    torch.set_num_threads(1)
    print(json.dumps(run_demo(args.output), sort_keys=True))
