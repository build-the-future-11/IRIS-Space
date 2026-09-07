"""Scientific safety gates."""

from .binding import (
    DEFAULT_REQUIRED_RADII_ARCSEC,
    EvidenceBindingContext,
    bind_completed_check,
    bind_completed_checks,
    preflight_digest,
)
from .catalog_policy import CatalogInterpretation, interpret_simbad
from .gates import GateDecision, GateOutcome, evaluate_reportability
from .suite import VerificationBundle, VerificationSuite

__all__ = [
    "CatalogInterpretation",
    "DEFAULT_REQUIRED_RADII_ARCSEC",
    "EvidenceBindingContext",
    "GateDecision",
    "GateOutcome",
    "VerificationBundle",
    "VerificationSuite",
    "bind_completed_check",
    "bind_completed_checks",
    "evaluate_reportability",
    "interpret_simbad",
    "preflight_digest",
]
