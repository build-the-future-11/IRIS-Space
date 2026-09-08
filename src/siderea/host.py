"""Transparent angular host-association utilities.

These functions expose a chance-coincidence statistic and positional
uncertainty.  They intentionally do **not** label that statistic a posterior
host probability: doing so would require a validated population prior and a
selection-function model that are outside this small utility.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


def _validate_coordinates(ra_deg: float, dec_deg: float, prefix: str) -> None:
    if isinstance(ra_deg, bool) or not math.isfinite(ra_deg) or not 0.0 <= ra_deg < 360.0:
        raise ValueError(f"{prefix} ra_deg must be finite and within [0, 360)")
    if isinstance(dec_deg, bool) or not math.isfinite(dec_deg) or not -90.0 <= dec_deg <= 90.0:
        raise ValueError(f"{prefix} dec_deg must be finite and within [-90, 90]")


def angular_separation_arcsec(
    first_ra_deg: float,
    first_dec_deg: float,
    second_ra_deg: float,
    second_dec_deg: float,
) -> float:
    """Return great-circle separation, robust to right-ascension wraparound."""

    _validate_coordinates(first_ra_deg, first_dec_deg, "first")
    _validate_coordinates(second_ra_deg, second_dec_deg, "second")
    ra_delta = math.radians(((second_ra_deg - first_ra_deg + 180.0) % 360.0) - 180.0)
    first_dec = math.radians(first_dec_deg)
    second_dec = math.radians(second_dec_deg)
    sin_dec = math.sin((second_dec - first_dec) / 2.0)
    sin_ra = math.sin(ra_delta / 2.0)
    haversine = sin_dec * sin_dec + math.cos(first_dec) * math.cos(second_dec) * sin_ra * sin_ra
    angle = 2.0 * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))
    return math.degrees(angle) * 3_600.0


@dataclass(frozen=True, slots=True)
class HostCandidate:
    """A possible host plus the local density of galaxies at least as bright.

    ``background_density_sigma_per_sq_deg`` is an optional one-standard-
    deviation statistical uncertainty. It cannot encode catalog completeness
    or selection-function systematics; those remain external validation inputs.
    """

    host_id: str
    ra_deg: float
    dec_deg: float
    background_density_per_sq_deg: float
    half_light_radius_arcsec: float = 0.0
    position_sigma_arcsec: float | None = None
    background_density_sigma_per_sq_deg: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.host_id, str):
            raise ValueError("host_id must be a string")
        identifier = self.host_id.strip()
        if not identifier:
            raise ValueError("host_id must not be empty")
        object.__setattr__(self, "host_id", identifier)
        _validate_coordinates(self.ra_deg, self.dec_deg, "host")
        for name in ("background_density_per_sq_deg", "half_light_radius_arcsec"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.position_sigma_arcsec is not None and (
            isinstance(self.position_sigma_arcsec, bool)
            or not math.isfinite(self.position_sigma_arcsec)
            or self.position_sigma_arcsec < 0.0
        ):
            raise ValueError("position_sigma_arcsec must be finite and non-negative when supplied")
        if self.background_density_sigma_per_sq_deg is not None and (
            isinstance(self.background_density_sigma_per_sq_deg, bool)
            or not math.isfinite(self.background_density_sigma_per_sq_deg)
            or self.background_density_sigma_per_sq_deg <= 0.0
        ):
            raise ValueError(
                "background_density_sigma_per_sq_deg must be finite and positive when supplied"
            )
        if self.background_density_per_sq_deg == 0.0:
            raise ValueError(
                "background_density_per_sq_deg must be positive; zero would imply false certainty"
            )


@dataclass(frozen=True, slots=True)
class HostAssociation:
    """One host's geometric association evidence (not a posterior probability)."""

    host_id: str
    separation_arcsec: float
    combined_position_sigma_arcsec: float | None
    uncertainty_complete: bool
    normalized_offset: float | None
    effective_radius_arcsec: float
    background_density_per_sq_deg: float
    chance_coincidence_probability: float
    statistic_is_posterior: bool = False
    background_density_sigma_per_sq_deg: float | None = None
    density_uncertainty_complete: bool = False
    chance_coincidence_probability_lower_bound: float | None = None
    chance_coincidence_probability_upper_bound: float | None = None
    density_sigma_multiplier: float = 3.0


@dataclass(frozen=True, slots=True)
class HostAssociationResult:
    """Ranked host evidence with an explicit ambiguity decision."""

    associations: tuple[HostAssociation, ...]
    preferred_host_id: str | None
    accepted_host_id: str | None
    ambiguous: bool
    reason: str


def _poisson_chance_probability(radius_arcsec: float, density_per_sq_deg: float) -> float:
    """Evaluate ``1-exp(-pi*r^2*density)`` without squaring overflow."""

    if radius_arcsec <= 0.0 or density_per_sq_deg <= 0.0:
        return 0.0
    if not math.isfinite(radius_arcsec) or not math.isfinite(density_per_sq_deg):
        return 1.0
    log_expected = (
        math.log(math.pi)
        + 2.0 * (math.log(radius_arcsec) - math.log(3_600.0))
        + math.log(density_per_sq_deg)
    )
    # Once the expected background exceeds ~37, exp(-expected) rounds below
    # double precision and the representable probability is exactly one.
    if log_expected >= math.log(37.0):
        return 1.0
    expected_background = math.exp(log_expected)
    return -math.expm1(-expected_background)


def chance_coincidence_association(
    transient_ra_deg: float,
    transient_dec_deg: float,
    host: HostCandidate,
    *,
    transient_position_sigma_arcsec: float | None = None,
    density_sigma_multiplier: float = 3.0,
) -> HostAssociation:
    """Compute a Poisson chance-coincidence statistic for one candidate host.

    The effective aperture is the larger of the three-sigma astrometric radius
    and ``sqrt(separation^2 + 4 * half_light_radius^2)``.  The Poisson statistic
    is ``1 - exp(-pi * radius^2 * density)`` with consistent square-degree
    units.  This is a ranking statistic, not a calibrated host posterior. When
    a host supplies a one-sigma background-density uncertainty, lower and upper
    statistics propagate ``density_sigma_multiplier`` times that uncertainty.
    The interval does not cover catalog-selection systematics.

    Unknown astrometric uncertainty is represented by ``None`` rather than
    zero. The returned ``uncertainty_complete`` is true only when both the
    transient and host uncertainties are explicitly positive; callers must not
    interpret an incomplete association as safe for automatic acceptance. The
    dimensionless ``normalized_offset`` is likewise ``None`` when neither a
    positive positional uncertainty nor a positive half-light radius supplies
    a defensible normalization scale.
    """

    _validate_coordinates(transient_ra_deg, transient_dec_deg, "transient")
    if transient_position_sigma_arcsec is not None and (
        isinstance(transient_position_sigma_arcsec, bool)
        or not math.isfinite(transient_position_sigma_arcsec)
        or transient_position_sigma_arcsec < 0.0
    ):
        raise ValueError(
            "transient_position_sigma_arcsec must be finite and non-negative when supplied"
        )
    if (
        isinstance(density_sigma_multiplier, bool)
        or not math.isfinite(density_sigma_multiplier)
        or density_sigma_multiplier <= 0.0
    ):
        raise ValueError("density_sigma_multiplier must be finite and positive")
    separation = angular_separation_arcsec(
        transient_ra_deg,
        transient_dec_deg,
        host.ra_deg,
        host.dec_deg,
    )
    host_position_sigma = host.position_sigma_arcsec
    if transient_position_sigma_arcsec is None or host_position_sigma is None:
        combined_sigma = None
        uncertainty_complete = False
    else:
        combined_sigma = math.hypot(transient_position_sigma_arcsec, host_position_sigma)
        uncertainty_complete = transient_position_sigma_arcsec > 0.0 and host_position_sigma > 0.0
    morphological_radius = math.hypot(separation, 2.0 * host.half_light_radius_arcsec)
    astrometric_radius = 3.0 * combined_sigma if combined_sigma is not None else 0.0
    effective_radius = max(astrometric_radius, morphological_radius)
    if not math.isfinite(effective_radius):
        raise ValueError("host angular scales exceed the finite numeric range; rescale them")
    p_chance = _poisson_chance_probability(
        effective_radius,
        host.background_density_per_sq_deg,
    )
    density_sigma = host.background_density_sigma_per_sq_deg
    if density_sigma is None:
        lower_probability = None
        upper_probability = None
    else:
        lower_density = max(
            0.0,
            host.background_density_per_sq_deg - density_sigma_multiplier * density_sigma,
        )
        upper_density = (
            host.background_density_per_sq_deg + density_sigma_multiplier * density_sigma
        )
        lower_probability = _poisson_chance_probability(effective_radius, lower_density)
        upper_probability = _poisson_chance_probability(effective_radius, upper_density)
    offset_scale = math.hypot(combined_sigma or 0.0, host.half_light_radius_arcsec)
    normalized_offset: float | None
    if offset_scale > 0.0:
        normalized_offset = separation / offset_scale
    else:
        normalized_offset = 0.0 if separation == 0.0 else None
    return HostAssociation(
        host_id=host.host_id,
        separation_arcsec=separation,
        combined_position_sigma_arcsec=combined_sigma,
        uncertainty_complete=uncertainty_complete,
        normalized_offset=normalized_offset,
        effective_radius_arcsec=effective_radius,
        background_density_per_sq_deg=host.background_density_per_sq_deg,
        chance_coincidence_probability=min(1.0, max(0.0, p_chance)),
        background_density_sigma_per_sq_deg=density_sigma,
        density_uncertainty_complete=density_sigma is not None,
        chance_coincidence_probability_lower_bound=(
            None if lower_probability is None else min(1.0, max(0.0, lower_probability))
        ),
        chance_coincidence_probability_upper_bound=(
            None if upper_probability is None else min(1.0, max(0.0, upper_probability))
        ),
        density_sigma_multiplier=float(density_sigma_multiplier),
    )


def associate_hosts(
    transient_ra_deg: float,
    transient_dec_deg: float,
    hosts: Sequence[HostCandidate],
    *,
    transient_position_sigma_arcsec: float | None = None,
    maximum_chance_probability: float = 0.10,
    minimum_contrast_ratio: float = 3.0,
    require_density_uncertainty: bool = False,
    density_sigma_multiplier: float = 3.0,
) -> HostAssociationResult:
    """Rank hosts and accept only a low-chance, sufficiently distinct result.

    ``minimum_contrast_ratio`` compares the runner-up and best chance
    statistics.  An accepted ID is withheld when the best association is weak
    or the first two are insufficiently distinct; the ranked evidence remains
    available for human review either way. Automatic acceptance additionally
    requires explicit, positive transient and host positional uncertainties for
    every supplied candidate because uncertainty affects both ranking and the
    runner-up contrast decision. Missing or zero uncertainty therefore fails
    closed while preserving the ranked evidence for review. Set
    ``require_density_uncertainty=True`` to additionally require local-density
    errors and compare thresholds using conservative propagated bounds.
    """

    _validate_coordinates(transient_ra_deg, transient_dec_deg, "transient")
    if (
        isinstance(maximum_chance_probability, bool)
        or not math.isfinite(maximum_chance_probability)
        or not 0.0 <= maximum_chance_probability <= 1.0
    ):
        raise ValueError("maximum_chance_probability must be finite and within [0, 1]")
    if (
        isinstance(minimum_contrast_ratio, bool)
        or not math.isfinite(minimum_contrast_ratio)
        or minimum_contrast_ratio <= 1.0
    ):
        raise ValueError("minimum_contrast_ratio must be finite and greater than one")
    if not isinstance(require_density_uncertainty, bool):
        raise ValueError("require_density_uncertainty must be boolean")
    if (
        isinstance(density_sigma_multiplier, bool)
        or not math.isfinite(density_sigma_multiplier)
        or density_sigma_multiplier <= 0.0
    ):
        raise ValueError("density_sigma_multiplier must be finite and positive")
    host_ids = [host.host_id for host in hosts]
    if len(set(host_ids)) != len(host_ids):
        raise ValueError("host_id values must be unique")

    associations = tuple(
        sorted(
            (
                chance_coincidence_association(
                    transient_ra_deg,
                    transient_dec_deg,
                    host,
                    transient_position_sigma_arcsec=transient_position_sigma_arcsec,
                    density_sigma_multiplier=density_sigma_multiplier,
                )
                for host in hosts
            ),
            key=lambda item: (
                (
                    item.chance_coincidence_probability_upper_bound
                    if require_density_uncertainty
                    and item.chance_coincidence_probability_upper_bound is not None
                    else (
                        math.inf
                        if require_density_uncertainty
                        else item.chance_coincidence_probability
                    )
                ),
                math.inf if item.normalized_offset is None else item.normalized_offset,
                item.separation_arcsec,
                item.host_id.casefold(),
                item.host_id,
            ),
        )
    )
    if not associations:
        return HostAssociationResult((), None, None, True, "no host candidates supplied")

    best = associations[0]
    if not all(association.uncertainty_complete for association in associations):
        return HostAssociationResult(
            associations,
            best.host_id,
            None,
            True,
            "automatic acceptance requires explicit positive transient and host positional "
            "uncertainties",
        )
    if require_density_uncertainty and not all(
        association.density_uncertainty_complete for association in associations
    ):
        return HostAssociationResult(
            associations,
            best.host_id,
            None,
            True,
            "automatic acceptance requires explicit positive background-density uncertainties",
        )
    best_threshold_probability = (
        best.chance_coincidence_probability_upper_bound
        if require_density_uncertainty
        else best.chance_coincidence_probability
    )
    if best_threshold_probability is None:
        raise RuntimeError("required host-density uncertainty bound was not computed")
    if best_threshold_probability > maximum_chance_probability:
        return HostAssociationResult(
            associations,
            best.host_id,
            None,
            True,
            "best chance-coincidence statistic exceeds the acceptance threshold",
        )
    if len(associations) > 1:
        runner_up = associations[1]
        numerical_floor = 1e-15
        if require_density_uncertainty:
            runner_probability = runner_up.chance_coincidence_probability_lower_bound
            best_probability = best.chance_coincidence_probability_upper_bound
            if runner_probability is None or best_probability is None:
                raise RuntimeError("required host-density uncertainty bounds were not computed")
        else:
            runner_probability = runner_up.chance_coincidence_probability
            best_probability = best.chance_coincidence_probability
        contrast = (runner_probability + numerical_floor) / (best_probability + numerical_floor)
        if contrast < minimum_contrast_ratio:
            return HostAssociationResult(
                associations,
                best.host_id,
                None,
                True,
                "top host candidates are not sufficiently distinct",
            )
    return HostAssociationResult(
        associations,
        best.host_id,
        best.host_id,
        False,
        (
            "best association passes conservative density-bound chance-coincidence and "
            "contrast thresholds"
            if require_density_uncertainty
            else "best association passes chance-coincidence and contrast thresholds"
        ),
    )


__all__ = [
    "HostAssociation",
    "HostAssociationResult",
    "HostCandidate",
    "angular_separation_arcsec",
    "associate_hosts",
    "chance_coincidence_association",
]
