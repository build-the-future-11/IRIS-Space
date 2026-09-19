from __future__ import annotations

import json
from pathlib import Path

import pytest

from siderea.research.space_jepa_v2_protocol import (
    SPACE_JEPA_V2_FROZEN_SCHEMA,
    freeze_space_jepa_v2_protocol,
    load_space_jepa_v2_protocol,
)


def test_checked_in_protocol_validates_and_freezes(tmp_path: Path) -> None:
    source = Path("configs/space-jepa-2-protocol.json")
    protocol = load_space_jepa_v2_protocol(source)
    assert protocol.horizons_days == (1.0, 3.0, 7.0, 14.0)
    assert protocol.seeds == (17, 29, 43, 71, 101)
    assert protocol.payload["stress_tests"]["primary_ood"] == "source_population_change"

    destination = tmp_path / "frozen.json"
    frozen = freeze_space_jepa_v2_protocol(source, destination)
    assert frozen.protocol_digest == protocol.protocol_digest
    payload = json.loads(destination.read_text())
    assert payload["schema"] == SPACE_JEPA_V2_FROZEN_SCHEMA
    assert load_space_jepa_v2_protocol(destination).protocol_digest == protocol.protocol_digest


def test_protocol_rejects_missing_required_control(tmp_path: Path) -> None:
    payload = json.loads(Path("configs/space-jepa-2-protocol.json").read_text())
    payload["memory_controls"].remove("shuffled_keys")
    source = tmp_path / "invalid.json"
    source.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="missing memory controls"):
        load_space_jepa_v2_protocol(source)
