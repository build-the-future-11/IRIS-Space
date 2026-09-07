"""Strict, typed TOML configuration for IRIS.

Configuration is intentionally parsed with the Python standard library.  The
loader rejects unknown keys so misspelled scientific thresholds cannot be
silently ignored.
"""

from __future__ import annotations

import dataclasses
import math
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when an IRIS configuration file is missing or invalid."""


def _positive(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ConfigError(f"{name} must be finite and greater than zero")


def _integer_value(value: int, name: str, *, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive" if minimum == 1 else "non-negative"
        raise ConfigError(f"{name} must be a {qualifier} integer")


def _boolean_value(value: bool, name: str) -> None:
    if not isinstance(value, bool):
        raise ConfigError(f"{name} must be a boolean")


@dataclass(frozen=True, slots=True)
class GeneralConfig:
    name: str = "IRIS"
    campaign: str = "ispy"
    environment: str = "development"
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field_name in ("name", "campaign", "environment"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"general.{field_name} must be a non-empty string")
            object.__setattr__(self, field_name, value.strip())
        _integer_value(self.schema_version, "general.schema_version", minimum=1)
        if self.schema_version != 1:
            raise ConfigError("general.schema_version must be 1 for this IRIS release")


@dataclass(frozen=True, slots=True)
class StorageConfig:
    root: Path
    runs_dir: Path
    cache_dir: Path
    datasets_dir: Path


@dataclass(frozen=True, slots=True)
class HuntConfig:
    broker: str = "alerce"
    object_limit: int = 350
    discovered_within_days: float = 30.0
    min_detections: int = 3
    broker_classes: tuple[str, ...] = ("SN",)

    def __post_init__(self) -> None:
        if not isinstance(self.broker, str):
            raise ConfigError("hunt.broker must be a string")
        broker = self.broker.strip().casefold()
        if broker != "alerce":
            raise ConfigError("hunt.broker must be 'alerce' until another adapter is implemented")
        object.__setattr__(self, "broker", broker)
        _integer_value(self.object_limit, "hunt.object_limit", minimum=1)
        _positive(self.discovered_within_days, "hunt.discovered_within_days")
        _integer_value(self.min_detections, "hunt.min_detections", minimum=1)
        if self.min_detections < 2:
            raise ConfigError("hunt.min_detections must be at least 2")
        if (
            isinstance(self.broker_classes, str)
            or not self.broker_classes
            or any(not isinstance(item, str) or not item.strip() for item in self.broker_classes)
        ):
            raise ConfigError("hunt.broker_classes must contain non-empty class names")
        object.__setattr__(
            self, "broker_classes", tuple(item.strip() for item in self.broker_classes)
        )


@dataclass(frozen=True, slots=True)
class ValidationConfig:
    required_checks: tuple[str, ...] = ("skybot", "tns", "simbad", "vsx")
    evidence_ttl_hours: float = 24.0
    skybot_radius_arcsec: float = 10.0
    tns_radius_arcsec: float = 5.0
    catalog_radius_arcsec: float = 3.0
    fail_closed: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.required_checks, str) or any(
            not isinstance(item, str) for item in self.required_checks
        ):
            raise ConfigError("validation.required_checks must be an array of strings")
        normalized = tuple(item.strip().casefold() for item in self.required_checks)
        if not normalized or any(not item for item in normalized):
            raise ConfigError("validation.required_checks must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ConfigError("validation.required_checks must be unique")
        supported = {"tns", "skybot", "simbad", "vsx"}
        unsupported = sorted(set(normalized) - supported)
        if unsupported:
            raise ConfigError(f"validation.required_checks are unsupported: {unsupported}")
        object.__setattr__(self, "required_checks", normalized)
        _positive(self.evidence_ttl_hours, "validation.evidence_ttl_hours")
        _positive(self.skybot_radius_arcsec, "validation.skybot_radius_arcsec")
        _positive(self.tns_radius_arcsec, "validation.tns_radius_arcsec")
        _positive(self.catalog_radius_arcsec, "validation.catalog_radius_arcsec")
        _boolean_value(self.fail_closed, "validation.fail_closed")
        if not self.fail_closed:
            raise ConfigError("validation.fail_closed must remain true")


@dataclass(frozen=True, slots=True)
class NetworkConfig:
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_seconds: float = 1.0
    user_agent: str = "iris-astronomy/0.2"

    def __post_init__(self) -> None:
        _positive(self.timeout_seconds, "network.timeout_seconds")
        _integer_value(self.max_retries, "network.max_retries", minimum=0)
        if (
            isinstance(self.backoff_seconds, bool)
            or not isinstance(self.backoff_seconds, (int, float))
            or not math.isfinite(self.backoff_seconds)
            or self.backoff_seconds < 0
        ):
            raise ConfigError("network.backoff_seconds must be finite and non-negative")
        if not isinstance(self.user_agent, str) or not self.user_agent.strip():
            raise ConfigError("network.user_agent must be a non-empty string")
        if "\r" in self.user_agent or "\n" in self.user_agent:
            raise ConfigError("network.user_agent must not contain line breaks")
        object.__setattr__(self, "user_agent", self.user_agent.strip())


@dataclass(frozen=True, slots=True)
class ReviewConfig:
    nightly_budget: int = 10
    required_reviewers: int = 1
    require_human_approval: bool = True
    allow_self_approval: bool = False

    def __post_init__(self) -> None:
        _integer_value(self.nightly_budget, "review.nightly_budget", minimum=1)
        _integer_value(self.required_reviewers, "review.required_reviewers", minimum=1)
        _boolean_value(self.require_human_approval, "review.require_human_approval")
        _boolean_value(self.allow_self_approval, "review.allow_self_approval")
        if not self.require_human_approval:
            raise ConfigError("review.require_human_approval must remain true")
        if self.allow_self_approval:
            raise ConfigError("review.allow_self_approval must remain false")


@dataclass(frozen=True, slots=True)
class RankingConfig:
    amplitude_weight: float = 0.24
    significance_weight: float = 0.22
    temporal_weight: float = 0.15
    nondetection_weight: float = 0.12
    sampling_weight: float = 0.12
    quality_weight: float = 0.15
    anomaly_slots: int = 2
    audit_slots: int = 0

    def __post_init__(self) -> None:
        weights = (
            self.amplitude_weight,
            self.significance_weight,
            self.temporal_weight,
            self.nondetection_weight,
            self.sampling_weight,
            self.quality_weight,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            for value in weights
        ):
            raise ConfigError("ranking weights must be finite and non-negative")
        if abs(sum(weights) - 1.0) > 1e-9:
            raise ConfigError("ranking weights must sum to 1.0")
        slot_values = (
            ("anomaly_slots", self.anomaly_slots),
            ("audit_slots", self.audit_slots),
        )
        for name, value in slot_values:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ConfigError(f"ranking.{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class JEPAConfig:
    enabled: bool = False
    shadow_mode: bool = True
    dataset_path: Path = Path("var/iris/datasets/jepa")
    embedding_dim: int = 256
    encoder_layers: int = 6
    attention_heads: int = 8
    mask_fraction: float = 0.5
    learning_rate: float = 0.0003
    batch_size: int = 128
    seed: int = 2026

    def __post_init__(self) -> None:
        _boolean_value(self.enabled, "jepa.enabled")
        _boolean_value(self.shadow_mode, "jepa.shadow_mode")
        if not self.shadow_mode:
            raise ConfigError("jepa.shadow_mode must remain true until promotion gates pass")
        _integer_value(self.embedding_dim, "jepa.embedding_dim", minimum=1)
        if self.embedding_dim < 8:
            raise ConfigError("jepa.embedding_dim must be at least 8")
        _integer_value(self.encoder_layers, "jepa.encoder_layers", minimum=1)
        _integer_value(self.attention_heads, "jepa.attention_heads", minimum=1)
        if self.embedding_dim % self.attention_heads:
            raise ConfigError("jepa.embedding_dim must be divisible by jepa.attention_heads")
        if (
            isinstance(self.mask_fraction, bool)
            or not isinstance(self.mask_fraction, (int, float))
            or not math.isfinite(self.mask_fraction)
            or not 0 < self.mask_fraction < 1
        ):
            raise ConfigError("jepa.mask_fraction must be finite and between 0 and 1")
        _positive(self.learning_rate, "jepa.learning_rate")
        _integer_value(self.batch_size, "jepa.batch_size", minimum=1)
        _integer_value(self.seed, "jepa.seed", minimum=0)


@dataclass(frozen=True, slots=True)
class IRISConfig:
    """Complete validated configuration used to start an IRIS run."""

    general: GeneralConfig
    storage: StorageConfig
    hunt: HuntConfig = field(default_factory=HuntConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    ranking: RankingConfig = field(default_factory=RankingConfig)
    jepa: JEPAConfig = field(default_factory=JEPAConfig)
    source_path: Path | None = None


_ROOT_KEYS = {
    "general",
    "storage",
    "hunt",
    "validation",
    "network",
    "review",
    "ranking",
    "jepa",
}


def default_config_path() -> Path:
    """Return the repository's default configuration path.

    ``IRIS_CONFIG`` may override it for deployments, while CLI ``--config``
    remains the most explicit option.
    """

    configured = os.environ.get("IRIS_CONFIG")
    if configured:
        return Path(configured).expanduser()
    repository_config = Path(__file__).resolve().parents[2] / "configs" / "default.toml"
    if repository_config.is_file():
        return repository_config
    return Path(__file__).with_name("default.toml")


def _reject_unknown(table: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(f"unknown {context} key(s): {', '.join(unknown)}")


def _section(data: Mapping[str, Any], name: str, allowed: set[str]) -> Mapping[str, Any]:
    raw = data.get(name, {})
    if not isinstance(raw, Mapping):
        raise ConfigError(f"{name} must be a TOML table")
    _reject_unknown(raw, allowed, name)
    return raw


def _string(table: Mapping[str, Any], key: str, default: str, context: str) -> str:
    value = table.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"{context}.{key} must be a string")
    return value


def _boolean(table: Mapping[str, Any], key: str, default: bool, context: str) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{context}.{key} must be a boolean")
    return value


def _integer(table: Mapping[str, Any], key: str, default: int, context: str) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{context}.{key} must be an integer")
    return value


def _number(table: Mapping[str, Any], key: str, default: float, context: str) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{context}.{key} must be a number")
    return float(value)


def _strings(
    table: Mapping[str, Any], key: str, default: tuple[str, ...], context: str
) -> tuple[str, ...]:
    value = table.get(key, default)
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise ConfigError(f"{context}.{key} must be an array of strings")
    return tuple(value)


def _path_value(value: str, base_dir: Path, context: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{context} must be a non-empty path string")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def load_config(path: str | Path | None = None) -> IRISConfig:
    """Load and validate an IRIS TOML file.

    Relative filesystem values are resolved relative to the configuration file,
    making a run independent of the shell's current directory.
    """

    source = Path(path).expanduser() if path is not None else default_config_path()
    source = source.resolve()
    try:
        with source.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise ConfigError(f"cannot read configuration {source}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {source}: {exc}") from exc
    if not isinstance(data, Mapping):
        raise ConfigError("configuration root must be a TOML table")
    _reject_unknown(data, _ROOT_KEYS, "top-level")
    base_dir = source.parent

    general_data = _section(data, "general", {"name", "campaign", "environment", "schema_version"})
    general = GeneralConfig(
        name=_string(general_data, "name", "IRIS", "general"),
        campaign=_string(general_data, "campaign", "ispy", "general"),
        environment=_string(general_data, "environment", "development", "general"),
        schema_version=_integer(general_data, "schema_version", 1, "general"),
    )

    storage_data = _section(data, "storage", {"root", "runs_dir", "cache_dir", "datasets_dir"})
    root = _path_value(
        _string(storage_data, "root", "../var/iris", "storage"), base_dir, "storage.root"
    )
    storage = StorageConfig(
        root=root,
        runs_dir=_path_value(
            _string(storage_data, "runs_dir", str(root / "runs"), "storage"),
            base_dir,
            "storage.runs_dir",
        ),
        cache_dir=_path_value(
            _string(storage_data, "cache_dir", str(root / "cache"), "storage"),
            base_dir,
            "storage.cache_dir",
        ),
        datasets_dir=_path_value(
            _string(storage_data, "datasets_dir", str(root / "datasets"), "storage"),
            base_dir,
            "storage.datasets_dir",
        ),
    )

    hunt_data = _section(
        data,
        "hunt",
        {"broker", "object_limit", "discovered_within_days", "min_detections", "broker_classes"},
    )
    hunt = HuntConfig(
        broker=_string(hunt_data, "broker", "alerce", "hunt"),
        object_limit=_integer(hunt_data, "object_limit", 350, "hunt"),
        discovered_within_days=_number(hunt_data, "discovered_within_days", 30.0, "hunt"),
        min_detections=_integer(hunt_data, "min_detections", 3, "hunt"),
        broker_classes=_strings(hunt_data, "broker_classes", ("SN",), "hunt"),
    )

    validation_data = _section(
        data,
        "validation",
        {
            "required_checks",
            "evidence_ttl_hours",
            "skybot_radius_arcsec",
            "tns_radius_arcsec",
            "catalog_radius_arcsec",
            "fail_closed",
        },
    )
    validation = ValidationConfig(
        required_checks=_strings(
            validation_data,
            "required_checks",
            ("skybot", "tns", "simbad", "vsx"),
            "validation",
        ),
        evidence_ttl_hours=_number(validation_data, "evidence_ttl_hours", 24.0, "validation"),
        skybot_radius_arcsec=_number(validation_data, "skybot_radius_arcsec", 10.0, "validation"),
        tns_radius_arcsec=_number(validation_data, "tns_radius_arcsec", 5.0, "validation"),
        catalog_radius_arcsec=_number(validation_data, "catalog_radius_arcsec", 3.0, "validation"),
        fail_closed=_boolean(validation_data, "fail_closed", True, "validation"),
    )

    network_data = _section(
        data, "network", {"timeout_seconds", "max_retries", "backoff_seconds", "user_agent"}
    )
    network = NetworkConfig(
        timeout_seconds=_number(network_data, "timeout_seconds", 30.0, "network"),
        max_retries=_integer(network_data, "max_retries", 3, "network"),
        backoff_seconds=_number(network_data, "backoff_seconds", 1.0, "network"),
        user_agent=_string(network_data, "user_agent", "iris-astronomy/0.2", "network"),
    )

    review_data = _section(
        data,
        "review",
        {"nightly_budget", "required_reviewers", "require_human_approval", "allow_self_approval"},
    )
    review = ReviewConfig(
        nightly_budget=_integer(review_data, "nightly_budget", 10, "review"),
        required_reviewers=_integer(review_data, "required_reviewers", 1, "review"),
        require_human_approval=_boolean(review_data, "require_human_approval", True, "review"),
        allow_self_approval=_boolean(review_data, "allow_self_approval", False, "review"),
    )

    ranking_data = _section(
        data,
        "ranking",
        {
            "amplitude_weight",
            "significance_weight",
            "temporal_weight",
            "nondetection_weight",
            "sampling_weight",
            "quality_weight",
            "anomaly_slots",
            "audit_slots",
        },
    )
    ranking = RankingConfig(
        amplitude_weight=_number(ranking_data, "amplitude_weight", 0.24, "ranking"),
        significance_weight=_number(ranking_data, "significance_weight", 0.22, "ranking"),
        temporal_weight=_number(ranking_data, "temporal_weight", 0.15, "ranking"),
        nondetection_weight=_number(ranking_data, "nondetection_weight", 0.12, "ranking"),
        sampling_weight=_number(ranking_data, "sampling_weight", 0.12, "ranking"),
        quality_weight=_number(ranking_data, "quality_weight", 0.15, "ranking"),
        anomaly_slots=_integer(ranking_data, "anomaly_slots", 2, "ranking"),
        audit_slots=_integer(ranking_data, "audit_slots", 0, "ranking"),
    )

    jepa_data = _section(
        data,
        "jepa",
        {
            "enabled",
            "shadow_mode",
            "dataset_path",
            "embedding_dim",
            "encoder_layers",
            "attention_heads",
            "mask_fraction",
            "learning_rate",
            "batch_size",
            "seed",
        },
    )
    jepa = JEPAConfig(
        enabled=_boolean(jepa_data, "enabled", False, "jepa"),
        shadow_mode=_boolean(jepa_data, "shadow_mode", True, "jepa"),
        dataset_path=_path_value(
            _string(jepa_data, "dataset_path", str(storage.datasets_dir / "jepa"), "jepa"),
            base_dir,
            "jepa.dataset_path",
        ),
        embedding_dim=_integer(jepa_data, "embedding_dim", 256, "jepa"),
        encoder_layers=_integer(jepa_data, "encoder_layers", 6, "jepa"),
        attention_heads=_integer(jepa_data, "attention_heads", 8, "jepa"),
        mask_fraction=_number(jepa_data, "mask_fraction", 0.5, "jepa"),
        learning_rate=_number(jepa_data, "learning_rate", 0.0003, "jepa"),
        batch_size=_integer(jepa_data, "batch_size", 128, "jepa"),
        seed=_integer(jepa_data, "seed", 2026, "jepa"),
    )

    return IRISConfig(
        general=general,
        storage=storage,
        hunt=hunt,
        validation=validation,
        network=network,
        review=review,
        ranking=ranking,
        jepa=jepa,
        source_path=source,
    )


def config_to_dict(config: IRISConfig) -> dict[str, Any]:
    """Convert config dataclasses into a JSON-friendly mapping."""

    def convert(value: Any) -> Any:
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {
                item.name: convert(getattr(value, item.name)) for item in dataclasses.fields(value)
            }
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, tuple):
            return [convert(item) for item in value]
        if isinstance(value, Mapping):
            return {str(key): convert(item) for key, item in value.items()}
        return value

    return {item.name: convert(getattr(config, item.name)) for item in dataclasses.fields(config)}
