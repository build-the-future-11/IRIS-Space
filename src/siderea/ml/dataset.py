"""Light-curve tokenization and batching for SIDEREA representation learning.

The functions in this module deliberately keep the on-disk/input format small:
one record contains parallel arrays of observation times, values, errors, bands,
and detection flags.  Tokens are sorted by time and packed at the start of a
batch so the boolean ``padding_mask`` has a single, unambiguous meaning: ``True``
denotes a real observation and ``False`` denotes padding.

PyTorch is an optional dependency for SIDEREA.  Importing this module works without
it; attempting to build a dataset or tensor gives a focused installation error.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from numbers import Integral, Real
from typing import Any

from siderea.bands import normalize_passband
from siderea.provenance import digest_value

try:  # Keep the non-ML SIDEREA install usable without a large optional dependency.
    import torch
    from torch.utils.data import Dataset
except ImportError as exc:  # pragma: no cover - exercised only in torch-free installs.
    torch = None  # type: ignore[assignment]
    Dataset = object  # type: ignore[assignment,misc]
    _TORCH_IMPORT_ERROR: ImportError | None = exc
else:
    _TORCH_IMPORT_ERROR = None


TOKEN_FIELDS = (
    "delta_time",
    "normalized_value",
    "normalized_error",
    "band_id",
    "detected",
    "value_present",
)
TOKENIZATION_CONTRACT_VERSION = "siderea.light_curve_tokens.v3"
DELTA_TIME_INDEX = 0
VALUE_INDEX = 1
ERROR_INDEX = 2
BAND_INDEX = 3
DETECTION_INDEX = 4
VALUE_PRESENT_INDEX = 5
TOKEN_DIM = len(TOKEN_FIELDS)

# IDs are stable and intentionally survey-agnostic.  Unknown survey filters map
# to the final bucket unless callers supply a project-specific vocabulary.
DEFAULT_BAND_TO_ID: dict[str, int] = {
    "u": 0,
    "g": 1,
    "r": 2,
    "i": 3,
    "z": 4,
    "y": 5,
    "unknown": 6,
}

_FLOAT_MAX = sys.float_info.max


def require_torch() -> None:
    """Raise a clear error when the optional ML dependency is unavailable."""

    if torch is None:
        raise RuntimeError(
            "SIDEREA JEPA support requires PyTorch. Install the optional ML dependencies "
            "before tokenizing or training light curves."
        ) from _TORCH_IMPORT_ERROR


@dataclass(frozen=True)
class TokenizedLightCurve:
    """A single packed light curve and the metadata needed to interpret it."""

    tokens: Any
    padding_mask: Any
    object_id: str | None = None
    times: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def length(self) -> int:
        return int(self.tokens.shape[0])


@dataclass(frozen=True)
class LightCurveBatch:
    """Padded light curves suitable for ``TSJEPA.forward``."""

    tokens: Any
    padding_mask: Any
    lengths: Any
    object_ids: tuple[str | None, ...]
    metadata: tuple[Mapping[str, Any], ...] = ()

    def to(self, device: Any) -> LightCurveBatch:
        """Return a copy with tensor fields moved to ``device``."""

        require_torch()
        return LightCurveBatch(
            tokens=self.tokens.to(device),
            padding_mask=self.padding_mask.to(device),
            lengths=self.lengths.to(device),
            object_ids=self.object_ids,
            metadata=self.metadata,
        )


def _as_list(values: Iterable[Any], name: str) -> list[Any]:
    try:
        return list(values)
    except TypeError as exc:
        raise TypeError(f"{name} must be an iterable") from exc


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in {"", "nan", "none", "null"}
    try:
        return bool(math.isnan(float(value)))
    except (TypeError, ValueError):
        return False


def _optional_finite(value: Any, name: str) -> float | None:
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number, not a boolean")
    number = _finite_number(value)
    if number is None:
        raise ValueError(f"{name} must be finite when supplied")
    return number


def _detection_value(value: Any, *, measurement_present: bool) -> bool:
    if value is None:
        return measurement_present
    if isinstance(value, bool):
        detected = value
    elif isinstance(value, Real) and not isinstance(value, bool):
        number = _finite_number(value)
        if number not in {0.0, 1.0}:
            raise ValueError(f"detection values must be boolean or 0/1, got {value!r}")
        detected = number == 1.0
    elif isinstance(value, str):
        normalized = value.strip().casefold()
        truthy = {"true", "t", "yes", "y", "detected", "detection", "1"}
        falsey = {"false", "f", "no", "n", "nondetection", "non-detection", "0"}
        if normalized not in truthy | falsey:
            raise ValueError(f"unrecognized detection value {value!r}")
        detected = normalized in truthy
    else:
        raise ValueError(f"unrecognized detection value {value!r}")
    if detected and not measurement_present:
        raise ValueError("a detected JEPA observation requires a finite value")
    return detected


def _robust_center_scale(
    values: Sequence[float], errors: Sequence[float | None]
) -> tuple[float, float]:
    """Return a robust location and non-zero scale without requiring NumPy."""

    if not values:
        return 0.0, 1.0

    # Calculate in max-absolute-value units. Directly averaging two large
    # central values, subtracting an opposite-signed center, or squaring a
    # large deviation can overflow even though every input is finite.
    reference = max(abs(value) for value in values)
    scaled_values = [value / reference for value in values] if reference else list(values)
    scaled_center = _finite_median(scaled_values)
    center = scaled_center * reference if reference else scaled_center
    scaled_deviations = [abs(value - scaled_center) for value in scaled_values]
    scaled_scale = 1.4826 * _finite_median(scaled_deviations)
    scale = _checked_rescale(scaled_scale, reference, "photometry value scale")
    if scale <= 0.0:
        scaled_variance = sum(deviation * deviation for deviation in scaled_deviations) / len(
            scaled_deviations
        )
        scaled_scale = math.sqrt(scaled_variance)
        scale = _checked_rescale(scaled_scale, reference, "photometry value scale")
    if scale <= 0.0:
        valid_errors = [error for error in errors if error is not None and error > 0]
        scale = _finite_median(valid_errors) if valid_errors else 1.0
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("photometry value scale is not representable; rescale the input values")
    return center, scale


def _finite_median(values: Sequence[float]) -> float:
    """Return a median without overflowing the midpoint of two finite values."""

    if not values:
        raise ValueError("cannot calculate the median of an empty sequence")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    lower = ordered[midpoint - 1]
    upper = ordered[midpoint]
    if lower == upper:
        return lower
    return lower / 2.0 + upper / 2.0


def _checked_rescale(value: float, reference: float, quantity: str) -> float:
    """Undo a numerical rescaling or fail with an actionable domain error."""

    if value == 0.0 or reference == 0.0:
        return 0.0
    if abs(value) > _FLOAT_MAX / abs(reference):
        raise ValueError(f"{quantity} exceeds the finite numeric range; rescale the input values")
    result = value * reference
    if not math.isfinite(result):  # Defensive guard for non-IEEE Python runtimes.
        raise ValueError(f"{quantity} exceeds the finite numeric range; rescale the input values")
    return result


def _checked_difference(later: float, earlier: float, quantity: str) -> float:
    """Subtract finite values while converting overflow into a domain error."""

    difference = later - earlier
    if not math.isfinite(difference):
        raise ValueError(f"{quantity} exceeds the finite numeric range; rescale the input units")
    return difference


def _checked_ratio(numerator: float, denominator: float, quantity: str) -> float:
    """Divide finite values and reject a result outside the float64 domain."""

    result = numerator / denominator
    if not math.isfinite(result):
        raise ValueError(f"{quantity} exceeds the finite numeric range; rescale the input units")
    return result


def _standardized_value(value: float, center: float, scale: float) -> float:
    """Standardize a value without overflowing an intermediate subtraction."""

    difference = value - center
    if math.isfinite(difference):
        return _checked_ratio(difference, scale, "normalized photometry value")
    # A sufficiently large scale can still make the mathematically correct
    # standardized value finite when the raw subtraction is not representable.
    standardized = value / scale - center / scale
    if not math.isfinite(standardized):
        raise ValueError(
            "normalized photometry value exceeds the finite numeric range; rescale the input values"
        )
    return standardized


def tokenize_light_curve(
    times: Iterable[Any],
    values: Iterable[Any],
    errors: Iterable[Any],
    bands: Iterable[Any],
    detections: Iterable[Any] | None = None,
    *,
    object_id: str | None = None,
    value_kind: str = "flux",
    band_to_id: Mapping[str, int] | None = None,
    max_length: int | None = None,
    allow_unknown_bands: bool = True,
) -> TokenizedLightCurve:
    """Convert irregular photometry into six-field temporal tokens.

    ``value_kind`` may be ``"flux"`` or ``"magnitude"`` and is recorded in the
    returned metadata.  Values are robustly standardized using detections only.
    Missing/non-finite values are retained as non-detections with neutral value
    content, allowing upper-limit epochs to contribute timing information.
    Unmapped passbands use the explicit ``unknown`` bucket and are counted in
    metadata. Set ``allow_unknown_bands=False`` when a training or evaluation
    contract requires a fully enumerated passband vocabulary.

    Delta times are measured in input time units and divided by the median
    positive cadence.  This preserves irregular spacing without making a
    survey's absolute time scale dominate the network.
    """

    require_torch()
    if value_kind not in {"flux", "magnitude", "mag"}:
        raise ValueError("value_kind must be 'flux', 'magnitude', or 'mag'")
    if max_length is not None and (
        isinstance(max_length, bool) or not isinstance(max_length, Integral) or max_length < 1
    ):
        raise ValueError("max_length must be a positive integer")
    if not isinstance(allow_unknown_bands, bool):
        raise ValueError("allow_unknown_bands must be boolean")

    raw_times = _as_list(times, "times")
    raw_values = _as_list(values, "values")
    raw_errors = _as_list(errors, "errors")
    raw_bands = _as_list(bands, "bands")
    raw_detections = (
        [None] * len(raw_times) if detections is None else _as_list(detections, "detections")
    )
    if detections is None and value_kind == "flux":
        raise ValueError("flux JEPA records require explicit detection flags")
    lengths = {
        len(raw_times),
        len(raw_values),
        len(raw_errors),
        len(raw_bands),
        len(raw_detections),
    }
    if len(lengths) != 1:
        raise ValueError("times, values, errors, bands, and detections must have equal lengths")
    if not raw_times:
        raise ValueError("a light curve must contain at least one observation")

    vocabulary = dict(DEFAULT_BAND_TO_ID if band_to_id is None else band_to_id)
    if not vocabulary:
        raise ValueError("band_to_id cannot be empty")
    if "unknown" not in vocabulary:
        raise ValueError("band_to_id must define an 'unknown' bucket")
    if any(
        not isinstance(key, str) or normalize_passband(key, map_ztf_numeric=False) != key
        for key in vocabulary
    ):
        raise ValueError("band_to_id keys must be canonical lower-case passband strings")
    ids = list(vocabulary.values())
    if any(isinstance(index, bool) or not isinstance(index, int) or index < 0 for index in ids):
        raise ValueError("band IDs must be non-negative integers")
    if len(set(ids)) != len(ids):
        raise ValueError("band IDs must be unique")
    unknown_id = vocabulary["unknown"]

    rows: list[tuple[float, float | None, float | None, str, bool]] = []
    for raw_time, raw_value, raw_error, raw_band, raw_detection in zip(
        raw_times, raw_values, raw_errors, raw_bands, raw_detections, strict=True
    ):
        time = _optional_finite(raw_time, "observation time")
        if time is None:
            raise ValueError("observation times cannot be missing")
        value = _optional_finite(raw_value, "photometry value")
        error = _optional_finite(raw_error, "photometry error")
        if error is not None and error <= 0:
            raise ValueError("photometry errors must be positive when supplied")
        detected = _detection_value(raw_detection, measurement_present=value is not None)
        if isinstance(raw_band, bool):
            raise ValueError("passbands cannot be boolean values")
        band = (
            normalize_passband(
                raw_band,
                map_ztf_numeric=band_to_id is None,
            )
            or "unknown"
        )
        if (band not in vocabulary or band == "unknown") and not allow_unknown_bands:
            raise ValueError(f"passband {band!r} is not in the configured vocabulary")
        rows.append((time, value, error, band, detected))

    # Equal-time observations have no intrinsic sequence order. A stable input
    # sort would make embeddings depend on upstream row order, so use physical
    # token content as deterministic secondary keys.
    rows.sort(
        key=lambda row: (
            row[0],
            row[3].casefold(),
            row[3],
            not row[4],
            row[1] is None,
            0.0 if row[1] is None else row[1],
            row[2] is None,
            0.0 if row[2] is None else row[2],
        )
    )
    if max_length is not None and len(rows) > max_length:
        # Keep the latest observations: early-classification callers can instead
        # pass an explicitly truncated prefix when simulating historical nights.
        rows = rows[-max_length:]
    unknown_bands = [
        band for _, _, _, band, _ in rows if band not in vocabulary or band == "unknown"
    ]

    detected_values = [value for _, value, _, _, detected in rows if detected and value is not None]
    finite_values = [value for _, value, _, _, _ in rows if value is not None]
    error_values = [error for _, _, error, _, detected in rows if detected]
    center, scale = _robust_center_scale(detected_values or finite_values, error_values)

    deltas = [
        _checked_difference(current[0], previous[0], "observation time span")
        for previous, current in zip(rows, rows[1:], strict=False)
    ]
    positive_deltas = [delta for delta in deltas if delta > 0]
    cadence_scale = _finite_median(positive_deltas) if positive_deltas else 1.0

    token_rows: list[list[float]] = []
    sorted_times: list[float] = []
    float32_max = float(torch.finfo(torch.float32).max)
    for index, (time, value, error, band, detected) in enumerate(rows):
        delta = (
            0.0
            if index == 0
            else _checked_ratio(deltas[index - 1], cadence_scale, "normalized time delta")
        )
        if value is None:
            normalized_value = 0.0
        elif value_kind in {"magnitude", "mag"}:
            normalized_value = -_standardized_value(value, center, scale)
        else:
            normalized_value = _standardized_value(value, center, scale)
        # Zero is an explicit missing-uncertainty sentinel because supplied
        # uncertainties are required to be strictly positive.  Imputing from
        # the full curve here would let a hidden target epoch influence visible
        # context tokens during masked JEPA training.
        # A value-presence bit is essential here: a finite non-detection (for
        # example a forced-flux measurement) and an epoch with no measurement
        # are scientifically different.  It also lets context-only rebasing
        # keep absent values neutral without leaking full-curve normalization
        # statistics from a masked target.
        value_present = value is not None
        normalized_error = (
            0.0
            if error is None or not value_present
            else _checked_ratio(error, scale, "normalized photometry error")
        )
        band_id = int(vocabulary.get(band, unknown_id))
        token_row = [
            delta,
            normalized_value,
            normalized_error,
            float(band_id),
            float(detected),
            float(value_present),
        ]
        if any(not math.isfinite(item) or abs(item) > float32_max for item in token_row):
            raise ValueError(
                "normalized JEPA token exceeds the float32 numeric range; "
                "rescale the input values, errors, or time units"
            )
        token_rows.append(token_row)
        sorted_times.append(time)

    tokens = torch.tensor(token_rows, dtype=torch.float32)
    padding_mask = torch.ones(len(token_rows), dtype=torch.bool)
    canonical_value_kind = "magnitude" if value_kind == "mag" else value_kind
    token_contract = {
        "format": TOKENIZATION_CONTRACT_VERSION,
        "token_fields": TOKEN_FIELDS,
        "value_kind": canonical_value_kind,
        "value_direction": "brighter_is_positive",
        "band_to_id": vocabulary,
        "unknown_band_policy": "map_to_unknown" if allow_unknown_bands else "reject",
        "detection_policy": "flux_requires_explicit; magnitude_may_infer_from_finite_value",
        "value_presence_policy": "explicit_token_field; missing_values_and_errors_are_zeroed",
        "missing_error_sentinel": 0.0,
        "error_presence_policy": "errors_without_measured_values_are_ignored",
        "max_length": None if max_length is None else int(max_length),
        "truncation_policy": "keep_latest",
        "equal_time_ordering": "time_band_detection_value_error",
        "normalization_scope": "full_curve_then_context_rebased_during_masking",
    }
    return TokenizedLightCurve(
        tokens=tokens,
        padding_mask=padding_mask,
        object_id=object_id,
        times=torch.tensor(sorted_times, dtype=torch.float64),
        metadata={
            "value_kind": canonical_value_kind,
            "value_center": center,
            "value_scale": scale,
            "cadence_scale": cadence_scale,
            "band_to_id": vocabulary,
            "band_vocabulary_sha256": digest_value(vocabulary),
            "token_fields": TOKEN_FIELDS,
            "token_contract": token_contract,
            "token_contract_sha256": digest_value(token_contract),
            "missing_error_count": sum(
                value is not None and error is None for _, value, error, _, _ in rows
            ),
            "value_missing_count": sum(value is None for _, value, _, _, _ in rows),
            "ignored_error_without_value_count": sum(
                value is None and error is not None for _, value, error, _, _ in rows
            ),
            "unknown_band_count": len(unknown_bands),
            "unknown_bands": tuple(sorted(set(unknown_bands), key=lambda item: item.casefold())),
            "detection_flags_inferred": detections is None,
            "equal_time_ordering": "time_band_detection_value_error",
            "normalization_scope": "full_curve_then_context_rebased_during_masking",
        },
    )


def pad_light_curves(items: Sequence[TokenizedLightCurve]) -> LightCurveBatch:
    """Right-pad tokenized light curves and return their validity masks."""

    require_torch()
    if not items:
        raise ValueError("cannot collate an empty batch")
    max_length = max(item.length for item in items)
    if max_length < 1:
        raise ValueError("light curves must not be empty")
    contract_digests: list[Any] = []
    for item in items:
        contract = item.metadata.get("token_contract")
        contract_digest = item.metadata.get("token_contract_sha256")
        if (contract is None) != (contract_digest is None):
            raise ValueError("JEPA token-contract metadata is incomplete")
        if contract is not None and digest_value(contract) != contract_digest:
            raise ValueError("JEPA token-contract metadata digest does not match")
        contract_digests.append(contract_digest)
    known_contracts = {str(value) for value in contract_digests if value is not None}
    mixed_provenance = bool(known_contracts) and any(value is None for value in contract_digests)
    if len(known_contracts) > 1 or mixed_provenance:
        raise ValueError("a JEPA batch cannot mix different or unprovenanced token contracts")

    tokens = torch.zeros((len(items), max_length, TOKEN_DIM), dtype=torch.float32)
    padding_mask = torch.zeros((len(items), max_length), dtype=torch.bool)
    lengths: list[int] = []
    for row, item in enumerate(items):
        if item.tokens.ndim != 2 or item.tokens.shape[1] != TOKEN_DIM:
            raise ValueError(f"tokens must have shape [time, {TOKEN_DIM}]")
        length = item.length
        if item.padding_mask.shape != (length,) or item.padding_mask.dtype != torch.bool:
            raise ValueError("each item padding_mask must be boolean and match token length")
        if not bool(item.padding_mask.all()):
            raise ValueError("unpadded light-curve items must mark every token as valid")
        if not bool(torch.isfinite(item.tokens).all()):
            raise ValueError("JEPA tokens must be finite")
        tokens[row, :length] = item.tokens.to(dtype=torch.float32)
        padding_mask[row, :length] = item.padding_mask.to(dtype=torch.bool)
        lengths.append(int(item.padding_mask.sum().item()))

    return LightCurveBatch(
        tokens=tokens,
        padding_mask=padding_mask,
        lengths=torch.tensor(lengths, dtype=torch.long),
        object_ids=tuple(item.object_id for item in items),
        metadata=tuple(item.metadata for item in items),
    )


def batch_token_contract_digest(batch: Any) -> str | None:
    """Return one verified token-contract digest for an SIDEREA batch.

    Mapping/tuple batches are intentionally treated as unprovenanced so the
    lower-level training API remains usable for callers that construct tensors
    themselves. A run may use that legacy path consistently, but the trainer
    and evaluator reject transitions between provenanced and unprovenanced
    batches or between two different contracts.
    """

    if not isinstance(batch, LightCurveBatch):
        return None
    if not batch.metadata:
        return None
    if len(batch.metadata) != int(batch.tokens.shape[0]):
        raise ValueError("JEPA batch metadata must match the batch row count")
    digests: set[str] = set()
    missing = 0
    for metadata in batch.metadata:
        if not isinstance(metadata, Mapping):
            raise ValueError("JEPA token metadata must be a mapping")
        contract = metadata.get("token_contract")
        contract_digest = metadata.get("token_contract_sha256")
        if (contract is None) != (contract_digest is None):
            raise ValueError("JEPA token-contract metadata is incomplete")
        if contract is None:
            missing += 1
            continue
        if not isinstance(contract_digest, str) or digest_value(contract) != contract_digest:
            raise ValueError("JEPA token-contract metadata digest does not match")
        digests.add(contract_digest)
    if len(digests) > 1 or (digests and missing):
        raise ValueError("a JEPA batch cannot mix different or unprovenanced token contracts")
    return next(iter(digests), None)


class LightCurveDataset(Dataset[TokenizedLightCurve]):
    """Lazy adapter from mappings to :class:`TokenizedLightCurve` objects."""

    def __init__(
        self,
        records: Sequence[Mapping[str, Any] | TokenizedLightCurve],
        *,
        band_to_id: Mapping[str, int] | None = None,
        max_length: int | None = None,
        allow_unknown_bands: bool = True,
    ) -> None:
        require_torch()
        self.records = list(records)
        if not self.records:
            raise ValueError("light-curve dataset cannot be empty")
        self.band_to_id = band_to_id
        self.max_length = max_length
        self.allow_unknown_bands = allow_unknown_bands

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> TokenizedLightCurve:
        record = self.records[index]
        if isinstance(record, TokenizedLightCurve):
            return record
        missing = {"times", "values", "errors", "bands"} - record.keys()
        if missing:
            raise KeyError(f"light-curve record is missing: {', '.join(sorted(missing))}")
        return tokenize_light_curve(
            record["times"],
            record["values"],
            record["errors"],
            record["bands"],
            record.get("detections"),
            object_id=record.get("object_id"),
            value_kind=record.get("value_kind", "flux"),
            band_to_id=self.band_to_id,
            max_length=self.max_length,
            allow_unknown_bands=self.allow_unknown_bands,
        )


# DataLoader convention-friendly alias.
collate_light_curves = pad_light_curves


__all__ = [
    "BAND_INDEX",
    "DEFAULT_BAND_TO_ID",
    "DELTA_TIME_INDEX",
    "DETECTION_INDEX",
    "ERROR_INDEX",
    "LightCurveBatch",
    "LightCurveDataset",
    "TOKEN_DIM",
    "TOKEN_FIELDS",
    "TOKENIZATION_CONTRACT_VERSION",
    "TokenizedLightCurve",
    "VALUE_INDEX",
    "VALUE_PRESENT_INDEX",
    "batch_token_contract_digest",
    "collate_light_curves",
    "pad_light_curves",
    "require_torch",
    "tokenize_light_curve",
]
