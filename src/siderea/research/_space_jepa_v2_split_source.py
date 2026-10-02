"""Re-derive the frozen Space JEPA 2 entity split from source data."""

from pathlib import Path

import pandas as pd

from siderea.ml.space_jepa_v2_data import _observations, chronological_entity_split
from siderea.research.space_jepa_v2_protocol import load_space_jepa_v2_protocol


def expected_splits(source: str | Path, protocol: str | Path):
    frozen = load_space_jepa_v2_protocol(protocol)
    settings = frozen.payload["split"]
    observations, _ = _observations(pd.read_csv(Path(source)))
    splits = chronological_entity_split(
        observations,
        train_fraction=float(settings["train_fraction"]),
        validation_fraction=float(settings["validation_fraction"]),
        test_fraction=float(settings["test_fraction"]),
    )
    return frozen, splits
