from __future__ import annotations

import pytest

from siderea.scoring import HeuristicScoreConfig, score_photometry_candidate


def _features(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "max_peak_brightening_mag": 1.2,
        "median_band_amplitude_mag": 0.9,
        "max_peak_significance": 7.0,
        "max_rise_rate_mag_per_day": 0.8,
        "max_fade_rate_mag_per_day": 0.3,
        "has_prior_nondetection": True,
        "prior_nondetection_gap_days": 1.0,
        "prior_nondetection_contrast_mag": 1.8,
        "n_detections": 8,
        "n_bands": 2,
        "n_significant_bright_points": 3,
        "missing_critical_fraction": 0.0,
        "quality_rejected_fraction": 0.0,
        "magnitude_error_missing_fraction": 0.0,
        "rejected_detection_fraction": 0.0,
        "warnings": [],
    }
    values.update(overrides)
    return values


def test_priority_is_bounded_transparent_and_explicitly_not_probability() -> None:
    result = score_photometry_candidate(_features())

    assert 0.0 < result["priority_score"] < 1.0
    assert result["is_probability"] is False
    assert "not a probability" in result["interpretation"]
    assert set(result["components"]) == {
        "amplitude",
        "significance",
        "temporal_shape",
        "prior_nondetection",
        "sampling",
        "data_quality",
    }
    assert sum(component["weight"] for component in result["components"].values()) == pytest.approx(
        1.0
    )


def test_score_does_not_saturate_all_threshold_passing_candidates() -> None:
    moderate = score_photometry_candidate(
        _features(
            max_peak_brightening_mag=0.8,
            median_band_amplitude_mag=0.6,
            max_peak_significance=5.0,
            max_rise_rate_mag_per_day=0.4,
        )
    )
    strong = score_photometry_candidate(
        _features(
            max_peak_brightening_mag=2.0,
            median_band_amplitude_mag=1.5,
            max_peak_significance=12.0,
            max_rise_rate_mag_per_day=1.5,
        )
    )

    assert 0.0 < moderate["priority_score"] < strong["priority_score"] < 1.0
    assert moderate["components"]["amplitude"]["score"] < strong["components"]["amplitude"]["score"]


def test_data_gaps_and_rejections_reduce_priority() -> None:
    clean = score_photometry_candidate(_features())
    incomplete = score_photometry_candidate(
        _features(
            missing_critical_fraction=0.5,
            quality_rejected_fraction=0.4,
            magnitude_error_missing_fraction=0.5,
            rejected_detection_fraction=0.5,
            warnings=["incomplete_observations_present"],
        )
    )

    assert incomplete["priority_score"] < clean["priority_score"]
    assert (
        incomplete["components"]["data_quality"]["score"]
        < clean["components"]["data_quality"]["score"]
    )
    assert "incomplete_observations_present" in incomplete["warnings"]


def test_sparse_or_missing_evidence_is_retained_as_an_explainable_low_score() -> None:
    result = score_photometry_candidate(
        {
            "n_detections": 1,
            "n_bands": 1,
            "missing_critical_fraction": 0.5,
        }
    )

    assert 0.0 <= result["priority_score"] < 0.4
    assert result["adjustments"]["sparse_history_factor"] < 1.0
    assert "amplitude_evidence_missing" in result["warnings"]
    assert "significance_evidence_missing" in result["warnings"]
    assert "sparse_detection_history" in result["warnings"]


def test_flux_only_evidence_uses_explicit_fallback_components() -> None:
    result = score_photometry_candidate(
        {
            "max_fractional_flux_excursion": 2.0,
            "median_fractional_flux_excursion": 1.5,
            "max_flux_peak_significance": 8.0,
            "max_detection_significance": 8.0,
            "max_normalized_flux_rise_rate_per_day": 1.0,
            "max_normalized_flux_fade_rate_per_day": 0.5,
            "prior_forced_flux_contrast_significance": 5.0,
            "has_prior_nondetection": True,
            "prior_nondetection_gap_days": 1.0,
            "n_detections": 5,
            "n_bands": 1,
            "n_significant_measurements": 2,
            "missing_critical_fraction": 0.0,
            "quality_rejected_fraction": 0.0,
            "measurement_error_missing_fraction": 0.0,
            "rejected_detection_fraction": 0.0,
            "warnings": [],
        }
    )

    assert result["priority_score"] > 0.5
    assert result["components"]["amplitude"]["inputs"]["basis"] == "forced_flux"
    assert result["components"]["temporal_shape"]["inputs"]["basis"] == "forced_flux"
    assert "magnitude_amplitude_missing_using_flux" in result["warnings"]
    assert result["is_probability"] is False


def test_non_finite_scoring_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        HeuristicScoreConfig(amplitude_scale_mag=float("nan"))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -0.1])
def test_significance_midpoint_must_be_finite_and_non_negative(value: float) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        HeuristicScoreConfig(significance_midpoint_sigma=value)


def test_zero_significance_midpoint_is_allowed() -> None:
    config = HeuristicScoreConfig(significance_midpoint_sigma=0.0)

    assert config.significance_midpoint_sigma == 0.0


def test_boolean_feature_values_are_not_interpreted_as_measurements() -> None:
    result = score_photometry_candidate(
        {
            "max_peak_brightening_mag": True,
            "max_peak_significance": False,
            "n_detections": True,
        }
    )

    assert result["components"]["amplitude"]["inputs"]["basis"] == "missing"
    assert result["components"]["sampling"]["inputs"]["n_detections"] == 0
    assert "amplitude_evidence_missing" in result["warnings"]
    assert "significance_evidence_missing" in result["warnings"]
