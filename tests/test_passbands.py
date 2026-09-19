from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from siderea.data.passbands import effective_frequency_hz, load_passband_csv


def test_passband_loads_sorts_and_binds_source(tmp_path: Path) -> None:
    source = tmp_path / "g.csv"
    pd.DataFrame({"frequency_hz": [6e14, 4e14, 5e14], "transmission": [0.0, 0.0, 1.0]}).to_csv(
        source, index=False
    )
    band = load_passband_csv(source, identifier="ztf-g-v1", counting_convention="photon")
    assert band.frequency_hz.tolist() == [4e14, 5e14, 6e14]
    assert effective_frequency_hz(band) == pytest.approx(5e14)
    assert len(band.contract_digest) == 64
