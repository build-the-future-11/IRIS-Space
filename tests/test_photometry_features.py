from __future__ import annotations

import pandas as pd
import pytest

from iris.features import (
    PhotometryFeatureConfig,
    compute_grouped_photometry_features,
    compute_photometry_features,
    flatten_photometry_features,
)


def test_different_band_zeropoints_do_not_create_false_variability() -> None:
    observations = pd.DataFrame(
        {
            "mjd": [1.0, 2.0, 3.0, 1.0, 2.0, 3.0],
            "filter": ["g", "g", "g", "r", "r", "r"],
            "mag": [18.0, 18.0, 18.0, 20.0, 20.0, 20.0],
            "magerr": [0.05] * 6,
        }
    )

    features = compute_photometry_features(observations)

    assert features["n_bands"] == 2
    assert features["max_band_amplitude_mag"] == pytest.approx(0.0)
    assert features["max_peak_brightening_mag"] == pytest.approx(0.0)
    assert "median_magnitude" not in features
    assert features["band_features"]["g"]["median_magnitude"] == pytest.approx(18.0)
    assert features["band_features"]["r"]["median_magnitude"] == pytest.approx(20.0)


def test_rise_fade_and_dimensionless_peak_flux_are_filter_local() -> None:
    observations = [
        {"mjd": 1.0, "fid": 1, "magpsf": 20.0, "sigmapsf": 0.05},
        {"mjd": 2.0, "fid": 1, "magpsf": 19.0, "sigmapsf": 0.05},
        {"mjd": 3.0, "fid": 1, "magpsf": 17.0, "sigmapsf": 0.05},
        {"mjd": 4.0, "fid": 1, "magpsf": 18.0, "sigmapsf": 0.05},
        {"mjd": 5.0, "fid": 1, "magpsf": 19.0, "sigmapsf": 0.05},
    ]

    features = compute_photometry_features(observations)
    g = features["band_features"]["g"]

    assert g["peak_brightening_mag"] == pytest.approx(2.0)
    assert g["peak_relative_flux"] == pytest.approx(10**0.8)
    assert g["rise_rate_mag_per_day"] > 0
    assert g["fade_rate_mag_per_day"] > 0
    assert features["max_rise_rate_mag_per_day"] == g["rise_rate_mag_per_day"]


def test_prior_nondetection_is_matched_within_band() -> None:
    observations = [
        {"mjd": 8.0, "filter": "g", "detected": False, "mag": None, "diffmaglim": 20.5},
        {"mjd": 9.0, "filter": "r", "detected": False, "mag": None, "diffmaglim": 24.0},
        {"mjd": 10.0, "filter": "g", "detected": True, "mag": 18.0, "magerr": 0.1},
        {"mjd": 11.0, "filter": "g", "detected": True, "mag": 17.5, "magerr": 0.1},
    ]

    features = compute_photometry_features(observations)

    assert features["has_prior_nondetection"] is True
    assert features["n_bands_with_prior_nondetection"] == 1
    assert features["n_channels_with_prior_nondetection"] == 1
    assert features["prior_nondetection_gap_days"] == pytest.approx(2.0)
    assert features["prior_nondetection_contrast_mag"] == pytest.approx(2.5)
    assert features["prior_nondetection_by_band"][0]["band"] == "g"


def test_prior_nondetection_band_and_channel_counts_have_distinct_semantics() -> None:
    observations = pd.DataFrame(
        {
            "mjd": [1.0, 2.0, 1.0, 2.0],
            "band": ["g"] * 4,
            "survey": ["survey-a", "survey-a", "survey-b", "survey-b"],
            "magnitude": [None, 18.0, None, 19.0],
            "magnitude_error": [None, 0.1, None, 0.1],
            "limiting_magnitude": [21.0, None, 22.0, None],
            "is_detection": [False, True, False, True],
        }
    )

    features = compute_photometry_features(observations)

    assert features["n_bands_with_prior_nondetection"] == 1
    assert features["n_channels_with_prior_nondetection"] == 2


def test_surveyless_band_metadata_is_none_not_stringified_nan() -> None:
    features = compute_photometry_features(
        [{"mjd": 1.0, "band": "g", "magnitude": 19.0, "magnitude_error": 0.1}]
    )

    assert features["band_features"]["g"]["survey"] is None


def test_distinct_magnitude_and_flux_significant_epochs_are_counted_as_a_union() -> None:
    features = compute_photometry_features(
        pd.DataFrame(
            {
                "mjd": [1.0, 2.0, 3.0],
                "band": ["g"] * 3,
                "magnitude": [10.0, 20.0, 20.0],
                "magnitude_error": [0.01] * 3,
                "flux": [0.0, 10.0, 0.0],
                "flux_error": [0.01] * 3,
                "is_detection": [True] * 3,
            }
        )
    )

    band = features["band_features"]["g"]
    assert band["n_significant_bright_points"] == 1
    assert band["n_significant_flux_points"] == 1
    assert band["n_significant_measurements"] == 2
    assert features["n_significant_measurements"] == 2


def test_quality_and_missingness_are_visible_not_silently_imputed() -> None:
    observations = pd.DataFrame(
        {
            "mjd": [1.0, 2.0, None, 4.0],
            "filter": ["g", "g", "g", None],
            "mag": [19.0, 18.0, 17.0, 16.0],
            "magerr": [0.1, None, 0.1, 0.1],
            "catflags": [0, 1, 0, 0],
        }
    )

    features = compute_photometry_features(observations)

    assert features["n_detections_raw"] == 4
    assert features["n_detections"] == 1
    assert features["n_rejected_detections"] == 3
    assert features["quality_rejected_fraction"] == pytest.approx(0.25)
    assert features["band_missing_fraction"] == pytest.approx(0.25)
    assert features["magnitude_error_missing_fraction"] == pytest.approx(0.25)
    assert "quality_rejections_present" in features["warnings"]
    assert "incomplete_observations_present" in features["warnings"]


def test_grouped_feature_extraction_keeps_source_identity_and_band_detail() -> None:
    observations = pd.DataFrame(
        {
            "source_id": ["A", "A", "B", "B"],
            "mjd": [1.0, 2.0, 1.0, 2.0],
            "filter": ["g", "g", "r", "r"],
            "mag": [19.0, 18.0, 20.0, 20.0],
            "magerr": [0.1, 0.1, 0.1, 0.1],
        }
    )

    result = compute_grouped_photometry_features(observations)

    assert result["source_id"].tolist() == ["A", "B"]
    assert result.loc[0, "band_g_peak_brightening_mag"] == pytest.approx(0.5)
    assert result.loc[1, "band_features"]["r"]["peak_brightening_mag"] == pytest.approx(0.0)


def test_peak_significance_uses_leave_one_out_baseline_uncertainty() -> None:
    features = compute_photometry_features(
        [
            {"mjd": 1.0, "band": "g", "mag": 20.0, "magerr": 0.1},
            {"mjd": 2.0, "band": "g", "mag": 18.0, "magerr": 0.1},
        ]
    )

    band = features["band_features"]["g"]
    assert band["peak_contrast_mag"] == pytest.approx(2.0)
    assert band["peak_significance"] == pytest.approx(2.0 / (2 * 0.1**2) ** 0.5)


def test_partial_comparison_uncertainty_never_inflates_significance() -> None:
    magnitude = compute_photometry_features(
        [
            {"mjd": 1.0, "band": "g", "mag": 20.0, "magerr": None},
            {"mjd": 2.0, "band": "g", "mag": 20.0, "magerr": 0.1},
            {"mjd": 3.0, "band": "g", "mag": 18.0, "magerr": 0.1},
        ]
    )
    flux = compute_photometry_features(
        [
            {"mjd": 1.0, "band": "g", "flux": 1.0, "fluxerr": None, "detected": True},
            {"mjd": 2.0, "band": "g", "flux": 1.0, "fluxerr": 0.1, "detected": True},
            {"mjd": 3.0, "band": "g", "flux": 10.0, "fluxerr": 0.1, "detected": True},
        ]
    )

    assert magnitude["band_features"]["g"]["peak_significance"] is None
    assert magnitude["band_features"]["g"]["n_significant_bright_points"] == 0
    assert flux["band_features"]["g"]["flux_peak_significance"] is None
    assert flux["band_features"]["g"]["n_significant_flux_points"] == 0


def test_ambiguous_aliases_and_unknown_detection_words_are_rejected() -> None:
    ambiguous = pd.DataFrame(
        {"mjd": [1], "band": ["g"], "mag": [19], "magpsf": [19], "magerr": [0.1]}
    )
    with pytest.raises(ValueError, match="Ambiguous"):
        compute_photometry_features(ambiguous)

    unknown = pd.DataFrame(
        {
            "mjd": [1],
            "band": ["g"],
            "mag": [19],
            "magerr": [0.1],
            "detected": ["perhaps"],
        }
    )
    with pytest.raises(ValueError, match="Unrecognized detection"):
        compute_photometry_features(unknown)


def test_forced_flux_is_a_first_class_unit_invariant_measurement() -> None:
    observations = pd.DataFrame(
        {
            "mjd": [0.0, 1.0, 2.0, 3.0],
            "band": ["g"] * 4,
            "flux": [0.0, 5.0, 12.0, 5.0],
            "flux_error": [1.0] * 4,
            "detected": [False, True, True, True],
        }
    )

    features = compute_photometry_features(observations)
    band = features["band_features"]["g"]

    assert features["feature_schema"] == "iris.photometry.v4"
    assert features["n_detections"] == 3
    assert features["n_nondetections_with_forced_flux"] == 1
    assert band["fractional_flux_excursion"] > 1.0
    assert band["flux_peak_significance"] > 3.0
    assert band["n_significant_flux_points"] == 1
    assert "median_magnitude" not in band
    assert features["max_detection_significance"] == band["flux_peak_significance"]
    assert features["prior_forced_flux_contrast_significance"] == pytest.approx(5.0 / 2**0.5)
    assert features["measurement_error_missing_fraction"] == pytest.approx(0.0)
    assert "flux_only_detections_present" in features["warnings"]

    scaled = observations.copy()
    scaled["flux"] *= 1000.0
    scaled["flux_error"] *= 1000.0
    scaled_features = compute_photometry_features(scaled)
    assert scaled_features["max_fractional_flux_excursion"] == pytest.approx(
        features["max_fractional_flux_excursion"]
    )
    assert scaled_features["max_flux_peak_significance"] == pytest.approx(
        features["max_flux_peak_significance"]
    )


def test_flux_only_input_requires_explicit_detection_semantics() -> None:
    with pytest.raises(ValueError, match="explicit detection"):
        compute_photometry_features(pd.DataFrame({"mjd": [1.0], "band": ["g"], "flux": [2.0]}))


def test_missing_peak_uncertainty_never_produces_peak_significance() -> None:
    magnitude = compute_photometry_features(
        [
            {"mjd": 1.0, "band": "g", "mag": 20.0, "magerr": 0.1},
            {"mjd": 2.0, "band": "g", "mag": 18.0, "magerr": None},
            {"mjd": 3.0, "band": "g", "mag": 20.1, "magerr": 0.1},
        ]
    )
    assert magnitude["band_features"]["g"]["peak_significance"] is None
    assert magnitude["max_peak_significance"] is None

    flux = compute_photometry_features(
        [
            {
                "mjd": 1.0,
                "band": "g",
                "flux": 1.0,
                "flux_error": 0.1,
                "detected": True,
            },
            {
                "mjd": 2.0,
                "band": "g",
                "flux": 10.0,
                "flux_error": None,
                "detected": True,
            },
            {
                "mjd": 3.0,
                "band": "g",
                "flux": 1.1,
                "flux_error": 0.1,
                "detected": True,
            },
        ]
    )
    assert flux["band_features"]["g"]["flux_peak_significance"] is None
    assert flux["max_flux_peak_significance"] is None


def test_numeric_detection_and_negative_flag_values_fail_closed() -> None:
    with pytest.raises(ValueError, match="boolean or 0/1"):
        compute_photometry_features(
            [{"mjd": 1.0, "band": "g", "mag": 19.0, "magerr": 0.1, "detected": 2}]
        )

    features = compute_photometry_features(
        [{"mjd": 1.0, "band": "g", "mag": 19.0, "magerr": 0.1, "catflags": -1}]
    )
    assert features["n_detections"] == 0
    assert features["quality_rejected_fraction"] == pytest.approx(1.0)


def test_project_numeric_bands_can_disable_ztf_fid_interpretation() -> None:
    features = compute_photometry_features(
        [
            {"mjd": 1.0, "band": "1", "mag": 19.0, "magerr": 0.1},
            {"mjd": 2.0, "band": "1", "mag": 18.0, "magerr": 0.1},
        ],
        config=PhotometryFeatureConfig(map_ztf_numeric_bands=False),
    )

    assert features["bands"] == ["1"]
    assert "g" not in features["band_features"]


def test_different_surveys_in_the_same_passband_are_never_pooled() -> None:
    frame = pd.DataFrame(
        {
            "mjd": [60000.0, 60001.0, 60000.0, 60001.0],
            "band": ["g", "g", "g", "g"],
            "survey": ["survey-a", "survey-a", "survey-b", "survey-b"],
            "magnitude": [10.0, 10.0, 20.0, 20.0],
            "magnitude_error": [0.1, 0.1, 0.1, 0.1],
        }
    )

    features = compute_photometry_features(frame)

    assert features["feature_schema"] == "iris.photometry.v4"
    assert features["n_bands"] == 1
    assert features["n_channels"] == 2
    assert features["channels"] == ["survey-a::g", "survey-b::g"]
    assert features["max_band_amplitude_mag"] == pytest.approx(0.0)
    assert features["max_peak_brightening_mag"] == pytest.approx(0.0)
    assert features["max_peak_significance"] == pytest.approx(0.0)
    assert features["band_features"]["survey-a::g"]["survey"] == "survey-a"
    assert "multi_survey_channels_separated" in features["warnings"]


def test_numeric_ztf_aliases_are_applied_only_in_declared_survey_contexts() -> None:
    base = {
        "mjd": [60000.0, 60001.0],
        "band": [1, 1],
        "magnitude": [19.0, 18.5],
        "magnitude_error": [0.1, 0.1],
    }
    custom = compute_photometry_features(pd.DataFrame({**base, "survey": ["custom", "custom"]}))
    ztf = compute_photometry_features(pd.DataFrame({**base, "survey": ["ztf", "ztf"]}))
    alerce = compute_photometry_features(
        pd.DataFrame({**base, "survey": ["ZTF/ALeRCE", "ZTF/ALeRCE"]})
    )

    assert custom["channels"] == ["custom::1"]
    assert custom["band_features"]["custom::1"]["passband"] == "1"
    assert ztf["channels"] == ["ztf::g"]
    assert ztf["band_features"]["ztf::g"]["passband"] == "g"
    assert alerce["channels"] == ["ztf%2Falerce::g"]


def test_tiny_flux_unit_rescaling_remains_invariant() -> None:
    rows = pd.DataFrame(
        {
            "mjd": [1.0, 2.0, 3.0],
            "band": ["g"] * 3,
            "flux": [1.0, 5.0, 2.0],
            "flux_error": [0.2, 0.2, 0.2],
            "detected": [True] * 3,
        }
    )
    original = compute_photometry_features(rows)
    rows[["flux", "flux_error"]] *= 1.0e-15
    tiny = compute_photometry_features(rows)
    assert tiny["max_fractional_flux_excursion"] == pytest.approx(
        original["max_fractional_flux_excursion"]
    )
    assert tiny["max_flux_peak_significance"] == pytest.approx(
        original["max_flux_peak_significance"]
    )


def test_extreme_finite_photometry_is_defined_or_fails_with_a_rescaling_error() -> None:
    stable = compute_photometry_features(
        [
            {"mjd": 1.0, "band": "g", "flux": 1.0e308, "fluxerr": 1.0e308, "detected": True},
            {"mjd": 2.0, "band": "g", "flux": 1.0e308, "fluxerr": 1.0e308, "detected": True},
        ]
    )
    assert stable["max_fractional_flux_excursion"] == pytest.approx(0.0)
    assert stable["max_flux_peak_significance"] == pytest.approx(0.0)

    with pytest.raises(ValueError, match="flux dynamic range.*rescale"):
        compute_photometry_features(
            [
                {"mjd": 1.0, "band": "g", "flux": -1.0e308, "fluxerr": 1.0, "detected": True},
                {"mjd": 2.0, "band": "g", "flux": 1.0e308, "fluxerr": 1.0, "detected": True},
            ]
        )

    with pytest.raises(ValueError, match="magnitude dynamic range"):
        compute_photometry_features(
            [
                {"mjd": 1.0, "band": "g", "mag": 2_000.0, "magerr": 0.1},
                {"mjd": 2.0, "band": "g", "mag": 0.0, "magerr": 0.1},
            ]
        )


def test_feature_configuration_and_flattened_band_collisions_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive or None"):
        PhotometryFeatureConfig(max_magnitude_error=float("nan"))
    with pytest.raises(ValueError, match="collide"):
        flatten_photometry_features({"band_features": {"g-r": {"peak": 1.0}, "g_r": {"peak": 2.0}}})
