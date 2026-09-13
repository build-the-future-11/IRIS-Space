from __future__ import annotations

import json
from pathlib import Path

import pytest

from siderea.cli import main
from siderea.provenance import digest_value
from siderea.research.pilot import assemble_shadow_evidence, build_integrated_shadow_queue


def _sealed(payload):
    payload = dict(payload)
    payload["result_digest"] = digest_value(payload)
    return payload


def _embeddings(rows, *, cutoff=10.0):
    return _sealed(
        {
            "schema": "siderea.jepa_embeddings.v1",
            "checkpoint_sha256": "a" * 64,
            "token_contract_sha256": "b" * 64,
            "code_identity_sha256": "c" * 64,
            "prediction_cutoff_mjd": cutoff,
            "rows": rows,
        }
    )


def _search(*sources, cutoff=10.0):
    return _sealed(
        {
            "schema": "siderea.transient_search.v1",
            "prediction_cutoff_mjd": cutoff,
            "objects": [
                {
                    "source_id": source,
                    "status": "evaluated",
                    "object_pvalue": 0.2,
                    "shadow_excess": False,
                }
                for source in sources
            ],
        }
    )


def test_shadow_assembly_keeps_scores_separate_and_binds_entities():
    candidates = _embeddings(
        [
            {"entity_id": "TNS-A", "object_id": "survey-a", "embedding": [4.0, 4.0]},
            {"entity_id": "TNS-B", "object_id": "survey-b", "embedding": [0.0, 0.0]},
        ]
    )
    reference = _embeddings(
        [
            {"entity_id": "ref-1", "object_id": "r1", "embedding": [0.0, 0.1]},
            {"entity_id": "ref-2", "object_id": "r2", "embedding": [0.1, 0.0]},
            {"entity_id": "ref-3", "object_id": "r3", "embedding": [-0.1, 0.0]},
        ]
    )
    result = assemble_shadow_evidence(_search("tns-a", "tns-b"), candidates, reference)
    assert result["fusion_rule"] is None
    assert result["qualifies_reportability"] is False
    assert result["candidate_entity_count"] == 2
    assert result["rows"][0]["jepa_anomaly_score"] > result["rows"][1]["jepa_anomaly_score"]
    assert result["result_digest"]


def test_shadow_assembly_binds_verified_operational_pipeline_candidates(tmp_path, capsys):
    source = tmp_path / "pipeline.csv"
    source.write_text(
        "source_id,ra_deg,dec_deg,survey,band,mjd,flux,flux_error,is_detection\n"
        "TNS-A,10,2,test,g,1,0,1,true\n"
        "TNS-A,10,2,test,g,2,1,1,true\n"
        "TNS-A,10,2,test,g,3,4,1,true\n"
        "TNS-B,20,3,test,g,1,0,1,true\n"
        "TNS-B,20,3,test,g,2,0,1,true\n"
        "TNS-B,20,3,test,g,3,0,1,true\n"
    )
    assert (
        main(
            [
                "analyze",
                str(source),
                "--output-dir",
                str(tmp_path / "analysis"),
                "--ledger",
                str(tmp_path / "outcomes.sqlite"),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    pipeline_path = report["candidates_path"]
    pipeline = json.loads(Path(pipeline_path).read_text(encoding="utf-8"))
    candidates = _embeddings(
        [
            {"entity_id": "TNS-A", "object_id": "a", "embedding": [2.0, 2.0]},
            {"entity_id": "TNS-B", "object_id": "b", "embedding": [0.0, 0.0]},
        ]
    )
    reference = _embeddings(
        [
            {"entity_id": "ref-1", "object_id": "r1", "embedding": [0.0, 0.1]},
            {"entity_id": "ref-2", "object_id": "r2", "embedding": [0.1, 0.0]},
        ]
    )
    result = assemble_shadow_evidence(
        _search("TNS-A", "TNS-B"),
        candidates,
        reference,
        pipeline_candidates=pipeline,
        manifest_binding={
            "pilot_manifest_digest": "a" * 64,
            "pilot_manifest_sha256": "b" * 64,
            "pipeline_manifest_sha256": "c" * 64,
            "pipeline_configuration_digest": "d" * 64,
            "pipeline_code_source_digest": "e" * 64,
        },
    )
    assert result["framework_channels"] == {
        "aadi_operational_heuristic": True,
        "aadi_template_search": True,
        "jepa_representation_novelty": True,
    }
    assert all(row["pipeline_candidate_version"] for row in result["rows"])
    assert all(row["pipeline_priority_score"] is not None for row in result["rows"])

    tampered = json.loads(json.dumps(pipeline))
    tampered["candidates"][0]["score"]["priority_score"] = 1.0
    with pytest.raises(ValueError, match="record digest"):
        assemble_shadow_evidence(
            _search("TNS-A", "TNS-B"),
            candidates,
            reference,
            pipeline_candidates=tampered,
            manifest_binding={
                "pilot_manifest_digest": "a" * 64,
                "pilot_manifest_sha256": "b" * 64,
                "pipeline_manifest_sha256": "c" * 64,
                "pipeline_configuration_digest": "d" * 64,
                "pipeline_code_source_digest": "e" * 64,
            },
        )


def test_shadow_assembly_rejects_tampering_overlap_cutoff_and_missing_entities():
    candidates = _embeddings([{"entity_id": "candidate", "object_id": "c", "embedding": [1.0]}])
    reference = _embeddings(
        [
            {"entity_id": "ref-1", "object_id": "r1", "embedding": [0.0]},
            {"entity_id": "ref-2", "object_id": "r2", "embedding": [0.1]},
        ]
    )
    with pytest.raises(ValueError, match="entity sets differ"):
        assemble_shadow_evidence(_search("other"), candidates, reference)
    with pytest.raises(ValueError, match="cutoffs"):
        assemble_shadow_evidence(_search("candidate", cutoff=9), candidates, reference)
    overlapping = _embeddings(
        [
            {"entity_id": "candidate", "object_id": "r1", "embedding": [0.0]},
            {"entity_id": "ref-2", "object_id": "r2", "embedding": [0.1]},
        ]
    )
    with pytest.raises(ValueError, match="disjoint"):
        assemble_shadow_evidence(_search("candidate"), candidates, overlapping)
    tampered = dict(candidates)
    tampered["rows"] = [{"entity_id": "candidate", "embedding": [99.0]}]
    with pytest.raises(ValueError, match="digest"):
        assemble_shadow_evidence(_search("candidate"), tampered, reference)


def test_transient_cli_rejects_future_observation_and_records_cutoff(tmp_path):
    source = tmp_path / "flux.csv"
    source.write_text(
        "source_id,survey,band,mjd,flux,flux_error\n"
        "a,test,g,1,0,1\n"
        "a,test,g,2,1,1\n"
        "a,test,g,3,2,1\n"
        "a,test,g,4,1,1\n"
    )
    rejected = tmp_path / "rejected.json"
    assert (
        main(["transient-search", str(source), str(rejected), "--prediction-cutoff-mjd", "3"]) == 2
    )
    assert not rejected.exists()
    output = tmp_path / "result.json"
    assert (
        main(
            [
                "transient-search",
                str(source),
                str(output),
                "--prediction-cutoff-mjd",
                "4",
                "--null-trials",
                "99",
            ]
        )
        == 0
    )
    assert json.loads(output.read_text())["prediction_cutoff_mjd"] == 4


def test_jepa_embed_requires_and_preserves_prediction_identity(tmp_path):
    torch = pytest.importorskip("torch")
    from siderea.ml import TSJEPA, save_checkpoint

    torch.manual_seed(3)
    checkpoint = tmp_path / "checkpoint.pt"
    save_checkpoint(checkpoint, TSJEPA(d_model=8, n_heads=2, num_layers=1, dropout=0.0))
    record = {
        "object_id": "survey-object",
        "entity_id": "TNS-object",
        "prediction_cutoff_mjd": 4.0,
        "times": [1.0, 2.0, 4.0],
        "values": [0.0, 1.0, 2.0],
        "errors": [0.1, 0.1, 0.1],
        "bands": ["g", "g", "g"],
        "detections": [True, True, True],
    }
    dataset = tmp_path / "data.jsonl"
    dataset.write_text(json.dumps(record) + "\n")
    output = tmp_path / "embeddings.json"
    assert main(["jepa-embed", str(checkpoint), str(dataset), str(output)]) == 0
    payload = json.loads(output.read_text())
    assert payload["rows"][0]["entity_id"] == "TNS-object"
    assert payload["prediction_cutoff_mjd"] == 4.0
    assert payload["checkpoint_sha256"] and payload["code_identity_sha256"]

    record["times"].append(5.0)
    record["values"].append(3.0)
    record["errors"].append(0.1)
    record["bands"].append("g")
    record["detections"].append(True)
    future = tmp_path / "future.jsonl"
    future.write_text(json.dumps(record) + "\n")
    assert main(["jepa-embed", str(checkpoint), str(future), str(tmp_path / "bad.json")]) == 2


def test_pilot_prepare_canonicalizes_entities_and_emits_both_inputs(tmp_path):
    source = tmp_path / "raw.csv"
    source.write_text(
        "source_id,entity,survey,band,mjd,flux,flux_error,detected,observation_id,ra_deg,dec_deg\n"
        "alias-a,TNS-A,test,g,1,0,1,false,001,12.5,-2.5\n"
        "alias-b,TNS-A,test,g,2,1,1,true,002,12.5,-2.5\n"
        "alias-a,TNS-A,test,g,3,2,1,true,003,12.5,-2.5\n"
        "alias-a,TNS-A,test,g,4,1,1,true,004,12.5,-2.5\n"
    )
    output = tmp_path / "prepared"
    assert (
        main(
            [
                "pilot-prepare",
                str(source),
                str(output),
                "--prediction-cutoff-mjd",
                "4",
                "--flux-unit",
                "uJy",
                "--calibration",
                "synthetic-test",
                "--entity-column",
                "entity",
                "--detection-column",
                "detected",
                "--require-pipeline-view",
            ]
        )
        == 0
    )
    manifest = json.loads((output / "manifest.json").read_text())
    record = json.loads((output / "jepa.jsonl").read_text())
    detector = (output / "detector_flux.csv").read_text()
    pipeline = (output / "pipeline_photometry.csv").read_text()
    assert manifest["entities"] == 1 and manifest["observations"] == 4
    assert manifest["schema"] == "siderea.pilot_dataset.v2"
    assert manifest["pipeline_view"]["status"] == "available"
    assert record["entity_id"] == "TNS-A"
    assert record["source_aliases"] == ["alias-a", "alias-b"]
    assert record["detections"] == [False, True, True, True]
    assert "alias-a" not in detector and "TNS-A" in detector
    assert "alias-a" not in pipeline and "TNS-A" in pipeline

    assert (
        main(
            [
                "pilot-prepare",
                str(source),
                str(tmp_path / "future"),
                "--prediction-cutoff-mjd",
                "3",
                "--flux-unit",
                "uJy",
                "--calibration",
                "synthetic-test",
                "--entity-column",
                "entity",
                "--detection-column",
                "detected",
            ]
        )
        == 2
    )


def test_integrated_queue_preserves_separate_aadi_jepa_and_audit_routes():
    rows = []
    for index in range(6):
        rows.append(
            {
                "entity_id": f"candidate-{index}",
                "pipeline_priority_score": 1.0 - index / 10,
                "pipeline_review_eligible": True,
                "detector_campaign_pvalue": 0.001 if index == 4 else 0.5,
                "detector_campaign_shadow_excess": index == 4,
                "jepa_anomaly_score": 0.99 if index == 5 else index / 10,
                "jepa_anomaly_score_valid": True,
            }
        )
    evidence = _sealed(
        {
            "schema": "siderea.shadow_evidence.v2",
            "framework_channels": {"aadi_operational_heuristic": True},
            "transient_campaign_inference": {"method": "bonferroni_union_bound"},
            "rows": rows,
        }
    )
    queue = build_integrated_shadow_queue(
        evidence,
        budget=4,
        detector_slots=1,
        jepa_slots=1,
        audit_slots=1,
        jepa_threshold=0.8,
        audit_seed="fixed-audit",
    )
    routes = [entry["selection_route"] for entry in queue["entries"]]
    assert len(queue["entries"]) == 4
    assert len({entry["entity_id"] for entry in queue["entries"]}) == 4
    assert "aadi_template_reserve" in routes
    assert "jepa_novelty_reserve" in routes
    assert "random_audit" in routes
    assert queue["fusion_rule"] is None
    assert queue["qualifies_reportability"] is False
    assert queue == build_integrated_shadow_queue(
        evidence,
        budget=4,
        detector_slots=1,
        jepa_slots=1,
        audit_slots=1,
        jepa_threshold=0.8,
        audit_seed="fixed-audit",
    )

    no_campaign = dict(evidence)
    no_campaign["transient_campaign_inference"] = None
    no_campaign.pop("result_digest")
    no_campaign = _sealed(no_campaign)
    with pytest.raises(ValueError, match="campaign-level inference"):
        build_integrated_shadow_queue(
            no_campaign,
            budget=1,
            detector_slots=1,
            jepa_slots=0,
        )
