from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from siderea.ingest.tns_data import audit_tns_input, normalize_tns_photometry


def test_tns_inventory_distinguishes_registry_and_photometry(tmp_path: Path) -> None:
    pd.DataFrame([{"objid": 1, "objname": "2026abc", "ra": 10.0, "dec": -2.0}]).to_csv(
        tmp_path / "registry.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "tns_name": "2026abc",
                "observation_id": "p1",
                "mjd": 60000.0,
                "query_mjd": 60001.0,
                "filter": "g",
                "flux": 1.0,
                "flux_error": 0.1,
            }
        ]
    ).to_csv(tmp_path / "photometry.csv", index=False)
    report = audit_tns_input(tmp_path)
    assert report["readiness"] == "READY_FULL"
    assert report["row_counts"] == {"photometry": 1, "registry": 1}
    assert len(str(report["inventory_digest"])) == 64


def test_normalization_retains_rejections() -> None:
    frame = pd.DataFrame(
        [
            {
                "tns_name": "2026abc",
                "observation_id": "p1",
                "mjd": 60000.0,
                "query_mjd": 60001.0,
                "filter": "g",
                "flux": 1.0,
                "flux_error": 0.1,
                "is_detection": True,
            },
            {
                "tns_name": "2026bad",
                "observation_id": "p2",
                "mjd": 60000.0,
                "query_mjd": 60001.0,
                "filter": "r",
                "flux": 1.0,
                "flux_error": -1.0,
                "is_detection": True,
            },
        ]
    )
    accepted, rejected = normalize_tns_photometry(frame)
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert json.loads(rejected.iloc[0]["row"])["tns_name"] == "2026bad"
