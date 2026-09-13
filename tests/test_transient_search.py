from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from siderea.research.transients import (
    FAMILIES,
    TransientBank,
    empirical_pvalue,
    search_flux_table,
    transient_template,
)


@pytest.mark.parametrize("family", FAMILIES)
def test_shapes_are_finite_unit_peak_and_nonnegative(family):
    curve = transient_template([-1e6, -3, 0, 3, 1e6], center=0, width=2, family=family)
    assert np.isfinite(curve).all() and (curve >= 0).all() and (curve <= 1).all()
    assert curve[2] == pytest.approx(1)


def test_profiled_fit_matches_weighted_least_squares_and_offset_invariance():
    times = np.linspace(0, 30, 50)
    errors = np.linspace(0.5, 2, 50)
    shape = transient_template(times, center=15, width=3, family="bazin")
    flux = 30 + 7 * shape + np.random.default_rng(8).normal(size=50) * errors
    bank = TransientBank(times, errors, centers=[15], widths=[3], families=["bazin"])
    design = np.stack([np.ones(50), shape], axis=1) / errors[:, None]
    expected = np.linalg.lstsq(design, flux / errors, rcond=None)[0]
    fit = bank.fit(flux)
    assert [fit["baseline"], fit["amplitude"]] == pytest.approx(expected)
    assert bank.statistics(flux + 10000) == pytest.approx(bank.statistics(flux))
    null_chi = np.sum(((flux - np.average(flux, weights=1 / errors**2)) / errors) ** 2)
    fit_chi = np.sum(((flux - design @ expected * errors) / errors) ** 2)
    assert fit["delta_chi_square"] == pytest.approx(null_chi - fit_chi)
    assert bank.fit(np.full(50, 100.0))["amplitude"] == 0


def test_null_is_reproducible_search_corrected_and_never_zero_pvalue():
    bank = TransientBank(np.arange(20), np.ones(20), centers=[5, 10, 15], widths=[1, 3])
    null = bank.simulate_null(trials=199, seed=13)
    assert np.array_equal(null, bank.simulate_null(trials=199, seed=13))
    assert empirical_pvalue(1e6, null) == 1 / 200
    assert empirical_pvalue(0, null) == 1
    assert np.all(bank.statistics(np.zeros((5, 20))) == 0)
    with pytest.raises(ValueError):
        bank.simulate_null(trials=1, seed=0)


def test_wild_residual_null_is_reproducible_and_records_assumptions():
    times = np.arange(20.0)
    errors = np.linspace(0.8, 1.2, 20)
    rng = np.random.default_rng(31)
    flux = 12 + rng.standard_t(df=4, size=20) * errors
    bank = TransientBank(times, errors, centers=[5, 10, 15], widths=[1, 3])
    first = bank.simulate_wild_null(flux, trials=199, seed=7, block_size=2)
    second = bank.simulate_wild_null(flux, trials=199, seed=7, block_size=2)
    assert np.array_equal(first, second)
    assert np.isfinite(first).all() and (first >= 0).all()

    frame = pd.DataFrame(
        {
            "source_id": "wild",
            "survey": "synthetic",
            "band": "g",
            "mjd": times,
            "flux": flux,
            "flux_error": errors,
        }
    )
    report = search_flux_table(
        frame,
        null_trials=199,
        center_count=3,
        widths=[2],
        null_method="wild_residual",
        wild_block_size=2,
    )
    assert report["null_method"] == "wild_residual"
    assert report["wild_block_size"] == 2
    assert "sign-symmetric" in report["assumptions"]
    with pytest.raises(ValueError, match="null_method"):
        search_flux_table(frame, null_method="unknown")
    with pytest.raises(ValueError, match="block size"):
        bank.simulate_wild_null(flux, trials=99, seed=1, block_size=0)


def test_channel_correction_limits_and_missing_epochs():
    frame = pd.DataFrame(
        {
            "source_id": "a",
            "survey": "test",
            "band": "g",
            "mjd": np.arange(12),
            "flux": np.exp(-(((np.arange(12) - 6) / 2) ** 2)) * 30,
            "flux_error": 1.0,
        }
    )
    frame = pd.concat([frame, frame.assign(band="r")])
    report = search_flux_table(frame, widths=[2], center_count=3, null_trials=99)
    assert report["objects"][0]["object_pvalue"] == 0.02
    assert report["objects"][0]["shadow_excess"] is False
    assert report["physical_classification"] is False
    with pytest.raises(ValueError, match="censored"):
        search_flux_table(frame.assign(is_detection=False))
    with pytest.raises(ValueError, match="resolve"):
        search_flux_table(frame, null_trials=99, alpha=0.0001)
    assert search_flux_table(frame.iloc[:2])["channels"][0]["status"] == "insufficient_epochs"


def test_campaign_correction_covers_declared_objects_and_planned_looks():
    frame = pd.DataFrame(
        {
            "source_id": "a",
            "survey": "test",
            "band": "g",
            "mjd": np.arange(12),
            "flux": np.exp(-(((np.arange(12) - 6) / 2) ** 2)) * 30,
            "flux_error": 1.0,
        }
    )
    report = search_flux_table(
        frame,
        widths=[2],
        center_count=3,
        null_trials=999,
        object_universe_size=10,
        planned_looks=4,
        look_index=2,
    )
    obj = report["objects"][0]
    assert obj["campaign_pvalue"] == pytest.approx(min(1, obj["object_pvalue"] * 40))
    assert report["campaign_inference"]["correction_factor"] == 40
    assert report["campaign_inference"]["look_index"] == 2
    assert "planned-look correction" in report["scope"]
    with pytest.raises(ValueError, match="smaller"):
        search_flux_table(pd.concat([frame, frame.assign(source_id="b")]), object_universe_size=1)
    with pytest.raises(ValueError, match="requires object_universe_size"):
        search_flux_table(frame, planned_looks=2)


def test_search_invalid_inputs_and_numeric_bounds():
    with pytest.raises(ValueError):
        TransientBank([1, 2, 3, 4], [1, 1, 0, 1], centers=[2], widths=[1])
    with pytest.raises(ValueError):
        TransientBank([1, 2, 3, 4], [1, 1, 1, 1], centers=[2], widths=[-1])
    with pytest.raises(ValueError):
        transient_template([1, 2], center=0, width=1, family="made-up")
    bank = TransientBank([1, 2, 3, 4], [1, 1, 1, 1], centers=[2], widths=[1])
    with pytest.raises(ValueError):
        bank.fit([1, 2, float("nan"), 4])


def test_search_cli_publishes_input_bound_report_without_overwrite(tmp_path, capsys):
    import json
    from hashlib import sha256

    from siderea.cli import main

    frame = pd.DataFrame(
        {
            "source_id": "cli",
            "survey": "synthetic",
            "band": "r",
            "mjd": np.arange(12),
            "flux": np.zeros(12),
            "flux_error": np.ones(12),
        }
    )
    source, output = tmp_path / "flux.csv", tmp_path / "search.json"
    frame.to_csv(source, index=False)
    arguments = [
        "transient-search",
        str(source),
        str(output),
        "--null-trials",
        "99",
        "--centers",
        "3",
    ]
    assert main(arguments) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["input_sha256"] == sha256(source.read_bytes()).hexdigest()
    assert report["objects"][0]["shadow_excess"] is False
    original = output.read_bytes()
    assert main(arguments) != 0
    assert output.read_bytes() == original


def test_correlated_fit_matches_generalized_least_squares():
    times = np.arange(12.0)
    errors = np.linspace(0.8, 1.2, 12)
    correlation = 0.7 ** np.abs(times[:, None] - times)
    shape = transient_template(times, center=6, width=2, family="bazin")
    flux = (
        10
        + 6 * shape
        + np.random.default_rng(17).multivariate_normal(np.zeros(12), correlation) * errors
    )
    bank = TransientBank(
        times, errors, centers=[6], widths=[2], families=["bazin"], correlation=correlation
    )
    design = np.stack([np.ones(12), shape], axis=1)
    covariance = correlation * errors[:, None] * errors
    precision = np.linalg.inv(covariance)
    expected = np.linalg.solve(design.T @ precision @ design, design.T @ precision @ flux)
    fit = bank.fit(flux)
    assert [fit["baseline"], fit["amplitude"]] == pytest.approx(expected)
    assert bank.statistics(flux + 100) == pytest.approx(bank.statistics(flux))
    assert np.array_equal(
        bank.simulate_null(trials=99, seed=4), bank.simulate_null(trials=99, seed=4)
    )
    with pytest.raises(ValueError, match="positive definite"):
        TransientBank(times, errors, centers=[6], widths=[2], correlation=np.ones((12, 12)))


def test_duplicate_measurements_are_not_independent_evidence():
    frame = pd.DataFrame(
        {
            "source_id": "a",
            "survey": "test",
            "band": "g",
            "mjd": np.arange(5.0),
            "flux": np.arange(5.0),
            "flux_error": 1.0,
        }
    )
    with pytest.raises(ValueError, match="duplicate measurements"):
        search_flux_table(pd.concat([frame, frame.iloc[:1]]))


def test_correlated_size_limit_precedes_quadratic_allocation():
    from unittest.mock import patch

    frame = pd.DataFrame(
        {
            "source_id": "a",
            "survey": "test",
            "band": "g",
            "mjd": np.arange(2049.0),
            "flux": 0.0,
            "flux_error": 1.0,
        }
    )
    with (
        patch("siderea.research.transients.np.exp", side_effect=AssertionError("allocated")),
        pytest.raises(ValueError, match="2048 epochs"),
    ):
        search_flux_table(frame, noise_timescale_days=2)


def test_unresolvable_threshold_and_unevaluated_objects_are_explicit():
    frame = pd.DataFrame(
        {
            "source_id": "a",
            "survey": "test",
            "band": "g",
            "mjd": np.arange(5.0),
            "flux": np.arange(5.0),
            "flux_error": 1.0,
        }
    )
    report = search_flux_table(
        pd.concat([frame, frame.assign(band="r")]), null_trials=99, center_count=2, widths=[1]
    )
    obj = report["objects"][0]
    assert obj["status"] == "insufficient_null_resolution"
    assert obj["minimum_resolvable_object_pvalue"] == 0.02
    assert obj["threshold_resolvable"] is False
    missing = search_flux_table(frame.iloc[:2])["objects"][0]
    assert missing["status"] == "insufficient_epochs"
    assert missing["object_pvalue"] is None and missing["evaluated_channels"] == 0


def test_outlier_influence_and_correlated_deletion_match_refitting():
    times = np.arange(20.0)
    errors = np.ones(20)
    correlation = 0.6 ** np.abs(times[:, None] - times)
    for matrix in (None, correlation):
        bank = TransientBank(
            times, errors, centers=[10], widths=[2], families=["gaussian"], correlation=matrix
        )
        outlier = np.zeros(20)
        outlier[10] = 20
        fit = bank.fit(outlier)
        assert fit["influence"]["most_influential_row"] == 10
        assert fit["influence"]["minimum_remaining_local_z"] == pytest.approx(0, abs=1e-10)
        for i in (2, 10, 17):
            keep = np.arange(20) != i
            reduced = TransientBank(
                times[keep],
                errors[keep],
                centers=[10],
                widths=[2],
                families=["gaussian"],
                correlation=None if matrix is None else matrix[np.ix_(keep, keep)],
            )
            assert fit["influence"]["remaining_local_z"][i] == pytest.approx(
                reduced.fit(outlier[keep])["max_local_z"], abs=1e-9
            )
    pulse = 8 * transient_template(times, center=10, width=2, family="gaussian")
    fit = bank.fit(pulse)
    assert fit["influence"]["minimum_remaining_local_z"] > fit["max_local_z"] * 0.8
    assert fit["influence"]["changes_detection_rule"] is False


@pytest.mark.parametrize("changed", [False, True])
def test_shadow_rejects_replayed_observation_ids(changed):
    frame = pd.DataFrame(
        {
            "source_id": ["a", "a"],
            "survey": "test",
            "band": "g",
            "mjd": [1.0, 2.0 if changed else 1.0],
            "flux": [2.0, 3.0 if changed else 2.0],
            "flux_error": 1.0,
            "observation_id": [" exposure-1 ", "exposure-1"],
        }
    )
    with pytest.raises(ValueError, match="reused observation_id"):
        search_flux_table(frame)


def test_shadow_keeps_distinct_same_time_observations():
    frame = pd.DataFrame(
        {
            "source_id": "a",
            "survey": "test",
            "band": "g",
            "mjd": [1.0, 1.0],
            "flux": 2.0,
            "flux_error": 1.0,
            "observation_id": ["001", "1"],
        }
    )
    assert search_flux_table(frame)["channels"][0]["rows"] == 2


@pytest.mark.parametrize("ids", [[None, " "], ["null", "None"], ["nan", ""], [None, "known-id"]])
def test_shadow_normalizes_missing_ids_before_duplicate_check(ids):
    frame = pd.DataFrame(
        {
            "source_id": "a",
            "survey": "test",
            "band": "g",
            "mjd": [1.0, 1.0],
            "flux": 2.0,
            "flux_error": 1.0,
            "observation_id": ids,
        }
    )
    with pytest.raises(ValueError, match="duplicate measurements"):
        search_flux_table(frame)


def test_shadow_csv_preserves_textual_observation_identifiers(tmp_path, capsys):
    from siderea.cli import main

    source = tmp_path / "flux.csv"
    source.write_text(
        "source_id,survey,band,mjd,flux,flux_error,observation_id\n"
        "001,test,g,60000,2,1,001\n"
        "001,test,g,60000,2,1,1\n"
    )
    output = tmp_path / "result.json"
    assert main(["transient-search", str(source), str(output)]) == 0
    import json

    result = json.loads(output.read_text())
    assert result["channels"][0]["source_id"] == "001"
    assert result["channels"][0]["rows"] == 2


def test_shadow_normalizes_survey_before_identity_checks():
    frame = pd.DataFrame(
        {
            "source_id": "a",
            "survey": [" Test Survey ", "test   survey"],
            "band": "g",
            "mjd": [1.0, 2.0],
            "flux": [2.0, 3.0],
            "flux_error": 1.0,
            "observation_id": "exposure",
        }
    )
    with pytest.raises(ValueError, match="reused observation_id"):
        search_flux_table(frame)
