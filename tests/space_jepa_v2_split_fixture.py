import pandas as pd

from siderea.ml.space_jepa_v2_data import prepare_space_jepa_v2_batches
from siderea.research.space_jepa_v2_protocol import load_space_jepa_v2_protocol


def prepared_fixture(tmp_path):
    rows = []
    for entity in range(6):
        for epoch in range(18):
            rows.append(
                {
                    "entity_id": f"e{entity}",
                    "observation_id": f"e{entity}-{epoch}",
                    "observed_at_mjd": 60000 + entity * 100 + epoch,
                    "available_at_mjd": 60000 + entity * 100 + epoch,
                    "band": "g",
                    "value": float(epoch),
                    "value_error": 0.1,
                    "is_detection": True,
                }
            )
    source = tmp_path / "survey.csv"
    pd.DataFrame(rows).to_csv(source, index=False)
    protocol_path = "configs/space-jepa-2-protocol.json"
    protocol = load_space_jepa_v2_protocol(protocol_path)
    split = protocol.payload["split"]
    output = tmp_path / "prepared"
    prepare_space_jepa_v2_batches(
        source,
        output,
        horizons_days=protocol.horizons_days,
        train_fraction=float(split["train_fraction"]),
        validation_fraction=float(split["validation_fraction"]),
        test_fraction=float(split["test_fraction"]),
        batch_size=4,
    )
    return output, source, protocol_path
