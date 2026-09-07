"""Advisory science-campaign concepts for experiment planning.

These profiles are deliberately *not* operational policy.  The current IRIS
pipeline does not activate a profile, enforce its service recommendations, or
produce a calibrated reality probability.  Keeping that boundary in the type
and field names prevents a planning preset from being mistaken for a live
scientific gate.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class CampaignProfile:
    """Non-binding research-program sketch for human experiment design."""

    name: str
    description: str
    suggested_review_budget_per_night: int
    recommended_services: tuple[str, ...]
    research_target_labels: tuple[str, ...]
    suggested_anomaly_reserve: int = 0
    operational_status: str = field(default="advisory_only_not_enforced", init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not isinstance(self.description, str)
            or not self.name.strip()
            or not self.description.strip()
        ):
            raise ValueError("campaign name and description are required")
        for name, value in {
            "suggested_review_budget_per_night": self.suggested_review_budget_per_night,
            "suggested_anomaly_reserve": self.suggested_anomaly_reserve,
        }.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        if self.suggested_review_budget_per_night < 1 or self.suggested_anomaly_reserve < 0:
            raise ValueError(
                "campaign review suggestions must be positive and reserves non-negative"
            )
        if self.suggested_anomaly_reserve > self.suggested_review_budget_per_night:
            raise ValueError(
                "campaign anomaly suggestion cannot exceed its nightly review suggestion"
            )
        for name, values in {
            "recommended_services": self.recommended_services,
            "research_target_labels": self.research_target_labels,
        }.items():
            if isinstance(values, (str, bytes)) or not isinstance(values, tuple):
                raise ValueError(f"{name} must be a tuple of strings")
            normalized = [item.strip().casefold() for item in values if isinstance(item, str)]
            if (
                len(normalized) != len(values)
                or any(not item for item in normalized)
                or len(set(normalized)) != len(normalized)
            ):
                raise ValueError(f"{name} must contain unique non-empty strings")


CAMPAIGNS: Mapping[str, CampaignProfile] = MappingProxyType(
    {
        "ispy": CampaignProfile(
            name="ispy",
            description="Young, novel extragalactic optical transients",
            suggested_review_budget_per_night=20,
            recommended_services=("tns", "skybot", "simbad", "vsx"),
            research_target_labels=("SNIa", "SNII", "SNIbc", "SLSN", "unknown_transient"),
            suggested_anomaly_reserve=3,
        ),
        "nuclear": CampaignProfile(
            name="nuclear",
            description="TDE, AGN flare, and nuclear-supernova candidates",
            suggested_review_budget_per_night=12,
            recommended_services=("tns", "skybot", "simbad", "vsx"),
            research_target_labels=("TDE", "AGN", "nuclear_transient"),
            suggested_anomaly_reserve=2,
        ),
        "fast_rare": CampaignProfile(
            name="fast_rare",
            description="Rapid, hostless, and otherwise rare optical transients",
            suggested_review_budget_per_night=10,
            recommended_services=("tns", "skybot", "simbad", "vsx"),
            research_target_labels=("FBOT", "kilonova_like", "orphan_afterglow", "hostless"),
            suggested_anomaly_reserve=5,
        ),
        "stellar": CampaignProfile(
            name="stellar",
            description="Eruptive and previously uncatalogued stellar phenomena",
            suggested_review_budget_per_night=10,
            recommended_services=("skybot", "simbad", "vsx"),
            research_target_labels=("CV", "dwarf_nova", "stellar_flare", "microlensing"),
            suggested_anomaly_reserve=3,
        ),
        "multimessenger": CampaignProfile(
            name="multimessenger",
            description=(
                "Optical counterparts to external high-energy or gravitational-wave triggers"
            ),
            suggested_review_budget_per_night=50,
            recommended_services=("tns", "skybot", "simbad", "vsx", "trigger_consistency"),
            research_target_labels=("kilonova_like", "afterglow", "unknown_transient"),
            suggested_anomaly_reserve=10,
        ),
        "distant_objects": CampaignProfile(
            name="distant_objects",
            description="Recoverable distant Solar System targets with orbit-improvement value",
            suggested_review_budget_per_night=25,
            recommended_services=("mpc", "jpl_horizons"),
            research_target_labels=("TNO", "centaur", "long_period_comet"),
        ),
    }
)


def get_campaign(name: str) -> CampaignProfile:
    """Return an advisory profile; this does not activate pipeline policy."""

    if not isinstance(name, str) or not name.strip():
        raise ValueError("campaign name must be a non-empty string")
    normalized = name.strip().casefold().replace("-", "_")
    if normalized == "i_spy":
        normalized = "ispy"
    try:
        return CAMPAIGNS[normalized]
    except KeyError as exc:
        raise ValueError(f"unknown campaign {name!r}; choose from {', '.join(CAMPAIGNS)}") from exc
