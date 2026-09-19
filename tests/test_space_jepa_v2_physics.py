from __future__ import annotations

import math

import numpy as np
import pytest

from siderea.ml.physics import (
    PhotosphereState,
    ab_magnitude_to_jy,
    censored_student_t_negative_log_likelihood,
    diffusion_derivatives,
    effective_temperature_k,
    integrate_passband_frequency,
    jy_to_ab_magnitude,
    physics_identifiability,
    student_t_cdf,
)


def test_ab_round_trip_and_error() -> None:
    flux, error = ab_magnitude_to_jy(20.0, 0.1)
    assert jy_to_ab_magnitude(flux) == pytest.approx(20.0)
    assert error is not None and error > 0.0


def test_flat_passband_preserves_constant_flux() -> None:
    frequency = np.linspace(4e14, 8e14, 100)
    flux = np.full_like(frequency, 3.5e-29)
    response = np.ones_like(frequency)
    assert integrate_passband_frequency(
        frequency, flux, response, photon_counting=False
    ) == pytest.approx(float(flux[0]))
    assert integrate_passband_frequency(
        frequency, flux, response, photon_counting=True
    ) == pytest.approx(float(flux[0]))


def test_student_t_cdf_is_symmetric_and_censoring_finite() -> None:
    for value in (0.2, 1.0, 5.0):
        assert student_t_cdf(value, 5.0) + student_t_cdf(-value, 5.0) == pytest.approx(1.0)
    assert math.isfinite(censored_student_t_negative_log_likelihood(1.0, 0.0, 1.0, 5.0))


def test_photosphere_equations_and_identifiability() -> None:
    state = PhotosphereState(1e12, 1e38, 2e5, 1e6)
    radius_rate, energy_rate = diffusion_derivatives(state, input_power_w=1e32)
    assert radius_rate == state.velocity_m_s
    assert math.isfinite(energy_rate)
    assert effective_temperature_k(luminosity_w=1e30, radius_m=1e12) > 0.0
    assert physics_identifiability(
        bands=1, detections=20, has_redshift=True, compatible_population=True
    ) == (False, "physics_not_identifiable")
    assert physics_identifiability(
        bands=3, detections=20, has_redshift=True, compatible_population=False
    ) == (False, "physics_incompatible_population")
