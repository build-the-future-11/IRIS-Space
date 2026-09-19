from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from siderea.research.space_jepa_v2_campaign import (
    run_space_jepa_v2_campaign,
    verify_space_jepa_v2_campaign,
)


def test_campaign_qualifies_inputs_and_verifies(tmp_path: Path) -> None:
    protocol_payload = json.loads(Path("configs/space-jepa-2-protocol.json").read_text())
    protocol_payload["seeds"] = [17]
    protocol_payload["model"].update(
        {
            "quaternion_width": 4,
            "encoder_blocks": 1,
            "attention_heads": 2,
            "predictor_blocks": 1,
            "dropout": 0.0,
        }
    )
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps(protocol_payload))
    tns = tmp_path / "tns.csv"
    survey = tmp_path / "survey.csv"
    pd.DataFrame([{"objid": 1, "objname": "2026abc", "ra": 1.0}]).to_csv(tns, index=False)
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
    pd.DataFrame(rows).to_csv(survey, index=False)
    output = tmp_path / "run"
    status = run_space_jepa_v2_campaign(
        protocol_path=protocol,
        tns_input=tns,
        survey_input=survey,
        output=output,
        epochs=1,
        batch_size=2,
    )
    assert status["state"] == "COMPLETED"
    assert status["completed_work_cells"] == 1
    assert status["scientific_promotion_authorized"] is False
    assert (output / "checkpoints/seed-17.pt").is_file()
    assert (output / "forecasts/test-seed-17.json").is_file()
    verification = verify_space_jepa_v2_campaign(output)
    assert verification["valid"]
