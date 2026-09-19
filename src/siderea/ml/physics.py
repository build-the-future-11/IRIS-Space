"""Physics and likelihood primitives for the Space JEPA 2 auxiliary route."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

PLANCK_J_S = 6.62607015e-34
BOLTZMANN_J_K = 1.380649e-23
LIGHT_SPEED_M_S = 299792458.0
STEFAN_BOLTZMANN_W_M2_K4 = 5.670374419e-8
PARSEC_M = 3.085677581491367e16
JANSKY_W_M2_HZ = 1e-26
AB_ZEROPOINT_JY = 3631.0


def ab_magnitude_to_jy(
    magnitude: float, magnitude_error: float | None = None
) -> tuple[float, float | None]:
    """Convert a verified AB magnitude to flux density in Jy."""

    if not math.isfinite(magnitude):
        raise ValueError("magnitude must be finite")
    flux = AB_ZEROPOINT_JY * 10.0 ** (-0.4 * magnitude)
    if magnitude_error is None:
        return flux, None
    if not math.isfinite(magnitude_error) or magnitude_error <= 0.0:
        raise ValueError("magnitude_error must be positive and finite")
    return flux, math.log(10.0) / 2.5 * flux * magnitude_error


def jy_to_ab_magnitude(flux_jy: float) -> float:
    if not math.isfinite(flux_jy) or flux_jy <= 0.0:
        raise ValueError("flux_jy must be positive and finite")
    return -2.5 * math.log10(flux_jy / AB_ZEROPOINT_JY)


def planck_nu(
    frequency_hz: FloatArray | Sequence[float] | float, temperature_k: float
) -> FloatArray:
    """Planck spectral radiance B_nu in W m^-2 Hz^-1 sr^-1."""

    if not math.isfinite(temperature_k) or temperature_k <= 0.0:
        raise ValueError("temperature_k must be positive and finite")
    frequency = np.asarray(frequency_hz, dtype=np.float64)
    if np.any(~np.isfinite(frequency)) or np.any(frequency <= 0.0):
        raise ValueError("frequencies must be positive and finite")
    exponent = PLANCK_J_S * frequency / (BOLTZMANN_J_K * temperature_k)
    denominator = np.expm1(np.clip(exponent, 0.0, 700.0))
    return 2.0 * PLANCK_J_S * frequency**3 / LIGHT_SPEED_M_S**2 / denominator


def luminosity_distance_mpc(
    redshift: float,
    *,
    hubble_km_s_mpc: float = 70.0,
    omega_matter: float = 0.3,
    integration_steps: int = 4096,
) -> float:
    """Flat-LambdaCDM luminosity distance using deterministic quadrature."""

    if not math.isfinite(redshift) or redshift < 0.0:
        raise ValueError("redshift must be finite and non-negative")
    if not math.isfinite(hubble_km_s_mpc) or hubble_km_s_mpc <= 0.0:
        raise ValueError("hubble_km_s_mpc must be positive and finite")
    if not math.isfinite(omega_matter) or not 0.0 < omega_matter < 1.0:
        raise ValueError("omega_matter must lie within (0, 1)")
    if integration_steps < 32:
        raise ValueError("integration_steps must be at least 32")
    if redshift == 0.0:
        return 0.0
    grid = np.linspace(0.0, redshift, integration_steps + 1, dtype=np.float64)
    expansion = np.sqrt(omega_matter * (1.0 + grid) ** 3 + (1.0 - omega_matter))
    comoving_mpc = LIGHT_SPEED_M_S / 1000.0 / hubble_km_s_mpc * np.trapezoid(1.0 / expansion, grid)
    return float((1.0 + redshift) * comoving_mpc)


def blackbody_luminosity_nu(
    emitted_frequency_hz: FloatArray | Sequence[float] | float,
    *,
    radius_m: float,
    temperature_k: float,
) -> FloatArray:
    if not math.isfinite(radius_m) or radius_m <= 0.0:
        raise ValueError("radius_m must be positive and finite")
    return 4.0 * math.pi**2 * radius_m**2 * planck_nu(emitted_frequency_hz, temperature_k)


def observed_blackbody_flux_nu(
    observed_frequency_hz: FloatArray | Sequence[float] | float,
    *,
    radius_m: float,
    temperature_k: float,
    redshift: float,
    luminosity_distance_m: float,
    attenuation_magnitudes: FloatArray | Sequence[float] | float = 0.0,
) -> FloatArray:
    """Observed F_nu for an isotropic redshifted blackbody photosphere."""

    if not math.isfinite(redshift) or redshift < 0.0:
        raise ValueError("redshift must be finite and non-negative")
    if not math.isfinite(luminosity_distance_m) or luminosity_distance_m <= 0.0:
        raise ValueError("luminosity_distance_m must be positive and finite")
    observed = np.asarray(observed_frequency_hz, dtype=np.float64)
    emitted = (1.0 + redshift) * observed
    attenuation = np.asarray(attenuation_magnitudes, dtype=np.float64)
    luminosity = blackbody_luminosity_nu(emitted, radius_m=radius_m, temperature_k=temperature_k)
    return (
        (1.0 + redshift)
        * luminosity
        / (4.0 * math.pi * luminosity_distance_m**2)
        * 10.0 ** (-0.4 * attenuation)
    )


def integrate_passband_frequency(
    frequency_hz: Sequence[float] | FloatArray,
    flux_nu: Sequence[float] | FloatArray,
    transmission: Sequence[float] | FloatArray,
    *,
    photon_counting: bool,
) -> float:
    """Return a response-weighted mean F_nu through a passband."""

    frequency = np.asarray(frequency_hz, dtype=np.float64)
    flux = np.asarray(flux_nu, dtype=np.float64)
    response = np.asarray(transmission, dtype=np.float64)
    if frequency.ndim != 1 or flux.shape != frequency.shape or response.shape != frequency.shape:
        raise ValueError("frequency, flux and transmission must be equal one-dimensional arrays")
    if len(frequency) < 2 or np.any(~np.isfinite(frequency)) or np.any(frequency <= 0.0):
        raise ValueError("frequency requires at least two positive finite samples")
    if np.any(~np.isfinite(flux)) or np.any(~np.isfinite(response)) or np.any(response < 0.0):
        raise ValueError("flux and non-negative transmission must be finite")
    order = np.argsort(frequency)
    frequency = frequency[order]
    flux = flux[order]
    response = response[order]
    weight = response / frequency if photon_counting else response
    denominator = float(np.trapezoid(weight, frequency))
    if denominator <= 0.0:
        raise ValueError("passband transmission has zero integrated response")
    return float(np.trapezoid(flux * weight, frequency) / denominator)


def student_t_negative_log_likelihood(
    observation: float,
    location: float,
    scale: float,
    degrees_of_freedom: float,
) -> float:
    if any(
        not math.isfinite(value) for value in (observation, location, scale, degrees_of_freedom)
    ):
        raise ValueError("Student-t parameters must be finite")
    if scale <= 0.0 or degrees_of_freedom <= 0.0:
        raise ValueError("Student-t scale and degrees_of_freedom must be positive")
    standardized = (observation - location) / scale
    log_density = (
        math.lgamma((degrees_of_freedom + 1.0) / 2.0)
        - math.lgamma(degrees_of_freedom / 2.0)
        - 0.5 * math.log(degrees_of_freedom * math.pi)
        - math.log(scale)
        - (degrees_of_freedom + 1.0)
        / 2.0
        * math.log1p(standardized * standardized / degrees_of_freedom)
    )
    return -log_density


def _continued_beta(a: float, b: float, x: float) -> float:
    maximum_iterations = 400
    epsilon = 3e-14
    floor = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    d = 1.0 / max(abs(d), floor) * (1.0 if d >= 0.0 else -1.0)
    result = d
    for iteration in range(1, maximum_iterations + 1):
        even = 2 * iteration
        coefficient = iteration * (b - iteration) * x / ((qam + even) * (a + even))
        d = 1.0 + coefficient * d
        d = floor if abs(d) < floor else d
        c = 1.0 + coefficient / c
        c = floor if abs(c) < floor else c
        d = 1.0 / d
        result *= d * c
        coefficient = -(a + iteration) * (qab + iteration) * x / ((a + even) * (qap + even))
        d = 1.0 + coefficient * d
        d = floor if abs(d) < floor else d
        c = 1.0 + coefficient / c
        c = floor if abs(c) < floor else c
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < epsilon:
            return result
    raise RuntimeError("incomplete beta continued fraction did not converge")


def _regularized_beta(a: float, b: float, x: float) -> float:
    if not 0.0 <= x <= 1.0:
        raise ValueError("regularized beta x must lie within [0, 1]")
    if x in {0.0, 1.0}:
        return x
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _continued_beta(a, b, x) / a
    return 1.0 - front * _continued_beta(b, a, 1.0 - x) / b


def student_t_cdf(value: float, degrees_of_freedom: float) -> float:
    if not math.isfinite(value) or not math.isfinite(degrees_of_freedom):
        raise ValueError("Student-t CDF arguments must be finite")
    if degrees_of_freedom <= 0.0:
        raise ValueError("degrees_of_freedom must be positive")
    if value == 0.0:
        return 0.5
    x = degrees_of_freedom / (degrees_of_freedom + value * value)
    tail = 0.5 * _regularized_beta(degrees_of_freedom / 2.0, 0.5, x)
    return 1.0 - tail if value > 0.0 else tail


def censored_student_t_negative_log_likelihood(
    upper_limit: float,
    location: float,
    scale: float,
    degrees_of_freedom: float,
) -> float:
    if scale <= 0.0 or not math.isfinite(scale):
        raise ValueError("scale must be positive and finite")
    probability = student_t_cdf((upper_limit - location) / scale, degrees_of_freedom)
    return -math.log(max(probability, np.finfo(np.float64).tiny))


@dataclass(frozen=True)
class PhotosphereState:
    radius_m: float
    internal_energy_j: float
    diffusion_time_s: float
    velocity_m_s: float


def diffusion_derivatives(state: PhotosphereState, *, input_power_w: float) -> tuple[float, float]:
    values = (
        state.radius_m,
        state.internal_energy_j,
        state.diffusion_time_s,
        state.velocity_m_s,
        input_power_w,
    )
    if any(not math.isfinite(value) for value in values):
        raise ValueError("photosphere state and input power must be finite")
    if state.radius_m <= 0.0 or state.internal_energy_j < 0.0 or state.diffusion_time_s <= 0.0:
        raise ValueError(
            "photosphere radius/diffusion time must be positive and energy non-negative"
        )
    if input_power_w < 0.0:
        raise ValueError("input_power_w must be non-negative")
    volume = 4.0 * math.pi * state.radius_m**3 / 3.0
    pressure = state.internal_energy_j / (3.0 * volume)
    volume_rate = 4.0 * math.pi * state.radius_m**2 * state.velocity_m_s
    luminosity = state.internal_energy_j / state.diffusion_time_s
    energy_rate = input_power_w - luminosity - pressure * volume_rate
    return state.velocity_m_s, energy_rate


def effective_temperature_k(*, luminosity_w: float, radius_m: float) -> float:
    if luminosity_w <= 0.0 or radius_m <= 0.0:
        raise ValueError("luminosity_w and radius_m must be positive")
    return float((luminosity_w / (4.0 * math.pi * STEFAN_BOLTZMANN_W_M2_K4 * radius_m**2)) ** 0.25)


def physics_identifiability(
    *, bands: int, detections: int, has_redshift: bool, compatible_population: bool
) -> tuple[bool, str]:
    if not compatible_population:
        return False, "physics_incompatible_population"
    if bands < 2 or detections < 4 or not has_redshift:
        return False, "physics_not_identifiable"
    return True, "physics_identifiable"


__all__ = [
    "AB_ZEROPOINT_JY",
    "JANSKY_W_M2_HZ",
    "PARSEC_M",
    "PhotosphereState",
    "ab_magnitude_to_jy",
    "blackbody_luminosity_nu",
    "censored_student_t_negative_log_likelihood",
    "diffusion_derivatives",
    "effective_temperature_k",
    "integrate_passband_frequency",
    "jy_to_ab_magnitude",
    "luminosity_distance_mpc",
    "observed_blackbody_flux_nu",
    "physics_identifiability",
    "planck_nu",
    "student_t_cdf",
    "student_t_negative_log_likelihood",
]
