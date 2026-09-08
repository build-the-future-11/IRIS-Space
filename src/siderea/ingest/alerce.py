"""Optional, lazy ALeRCE broker adapter.

Importing SIDEREA never imports the third-party ALeRCE client.  A caller may also
inject a client-compatible object, which makes the adapter testable and allows
deployments to configure authentication outside this package.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from typing import Any, TypeVar

import pandas as pd

from .base import BrokerDependencyError, BrokerQuery, IngestionBatch, IngestionError
from .schema import normalize_photometry_frame

T = TypeVar("T")

_DEFAULT_CLASSIFIERS = {
    "ztf": "lc_classifier_transient",
    "lsst": "stamp_classifier_rubin_beta",
}
_DEFAULT_LSST_CLASSIFIER_VERSION = "2.0.1"
_KNOWN_LSST_TAXONOMIES = {
    "stamp_classifier_rubin_beta": frozenset({"SN", "AGN", "VS", "asteroid", "bogus"})
}
_LSST_PIXEL_FAILURE_FLAGS = (
    "pixelflags_bad",
    "pixelflags_cr",
    "pixelflags_crcenter",
    "pixelflags_edge",
    "pixelflags_nodata",
    "pixelflags_nodatacenter",
    "pixelflags_interpolated",
    "pixelflags_interpolatedcenter",
    "pixelflags_offimage",
    "pixelflags_saturated",
    "pixelflags_saturatedcenter",
    "pixelflags_suspect",
    "pixelflags_suspectcenter",
    "pixelflags_streak",
    "pixelflags_streakcenter",
)
_LSST_INJECTION_FLAGS = (
    "pixelflags_injected",
    "pixelflags_injectedcenter",
    "pixelflags_injected_template",
    "pixelflags_injected_templatecenter",
)


class AlerceAdapter:
    """Fetch detections and non-detections from ALeRCE into canonical form."""

    name = "alerce"

    def __init__(
        self,
        client: Any | None = None,
        *,
        classifier: str | None = None,
        classifier_version: str | None = None,
        survey: str = "ztf",
        timeout_seconds: float = 30.0,
        user_agent: str = "siderea-astronomy/0.3",
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(survey, str):
            raise TypeError("survey must be a string")
        survey = survey.strip().casefold()
        if survey not in {"ztf", "lsst"}:
            raise ValueError("survey must be 'ztf' or 'lsst'")
        classifier_is_default = classifier is None
        if classifier_is_default:
            classifier = _DEFAULT_CLASSIFIERS[survey]
        elif not isinstance(classifier, str):
            raise TypeError("classifier must be a string or None")
        classifier = classifier.strip()
        if not classifier:
            raise ValueError("classifier must not be empty")
        if survey == "lsst":
            if classifier_version is None:
                if not classifier_is_default:
                    raise ValueError(
                        "a custom LSST classifier requires an explicit classifier_version"
                    )
                classifier_version = _DEFAULT_LSST_CLASSIFIER_VERSION
            elif not isinstance(classifier_version, str):
                raise TypeError("classifier_version must be a string or None")
            classifier_version = classifier_version.strip()
            if not classifier_version:
                raise ValueError("classifier_version must not be empty")
        elif classifier_version is not None:
            raise ValueError("classifier_version is supported only for the LSST survey")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise TypeError("timeout_seconds must be a number")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if not isinstance(user_agent, str):
            raise TypeError("user_agent must be a string")
        user_agent = user_agent.strip()
        if not user_agent or "\r" in user_agent or "\n" in user_agent:
            raise ValueError("user_agent must be non-empty and contain no line breaks")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        if (
            isinstance(backoff_seconds, bool)
            or not isinstance(backoff_seconds, (int, float))
            or not math.isfinite(backoff_seconds)
            or backoff_seconds < 0
        ):
            raise ValueError("backoff_seconds must be finite and non-negative")
        if not callable(sleeper):
            raise TypeError("sleeper must be callable")
        self._provided_client = client
        self.classifier = classifier
        self.classifier_version = classifier_version
        self.survey = survey
        self.timeout_seconds = float(timeout_seconds)
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.backoff_seconds = float(backoff_seconds)
        self.sleeper = sleeper
        self._network_policy_enforced = False

    def _configure_network(self, client: Any, *, required: bool) -> None:
        search_client = getattr(
            client,
            "legacy_ztf_client" if self.survey == "ztf" else "multisurvey_client",
            None,
        )
        session = getattr(search_client, "session", None)
        request = getattr(session, "request", None)
        headers = getattr(session, "headers", None)
        if session is None or not callable(request) or headers is None:
            if required:
                raise BrokerDependencyError(
                    "ALeRCE client does not expose the expected configurable HTTP session"
                )
            self._network_policy_enforced = False
            return
        existing_agent = str(headers.get("User-Agent", "")).strip()
        if self.user_agent not in existing_agent:
            headers["User-Agent"] = f"{existing_agent} {self.user_agent}".strip()
        session.request = partial(request, timeout=self.timeout_seconds)
        self._network_policy_enforced = True

    def _client(self) -> Any:
        if self._provided_client is not None:
            self._configure_network(self._provided_client, required=False)
            return self._provided_client
        try:
            from alerce.core import Alerce
        except ImportError as exc:
            raise BrokerDependencyError(
                "ALeRCE ingestion requires the optional 'alerce' package"
            ) from exc
        client = Alerce()
        self._configure_network(client, required=True)
        return client

    def _call(self, operation: str, call: Callable[[], T]) -> T:
        attempts = self.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return call()
            except Exception as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    self.sleeper(self.backoff_seconds * (2**attempt))
        raise IngestionError(
            f"ALeRCE {operation} failed after {attempts} attempt(s): {last_error}"
        ) from last_error

    @staticmethod
    def _as_frame(value: Any, operation: str) -> pd.DataFrame:
        if isinstance(value, pd.DataFrame):
            return value.copy()
        try:
            return pd.DataFrame.from_records(value)
        except Exception as exc:
            raise IngestionError(f"ALeRCE {operation} returned an unsupported value") from exc

    @staticmethod
    def _required_column(frame: pd.DataFrame, name: str, operation: str) -> str:
        matches = [str(column) for column in frame.columns if str(column).casefold() == name]
        if len(matches) != 1:
            raise IngestionError(
                f"ALeRCE {operation} requires exactly one {name!r} column; found {matches}"
            )
        return matches[0]

    @classmethod
    def _binary_flag(cls, frame: pd.DataFrame, name: str, operation: str) -> pd.Series:
        column = cls._required_column(frame, name.casefold(), operation)
        values = pd.to_numeric(frame[column], errors="coerce")
        invalid = values.isna() | ~values.isin([0, 1])
        if invalid.any():
            rows = frame.index[invalid].tolist()[:10]
            raise IngestionError(
                f"ALeRCE {operation} has invalid binary flag {column!r} at row(s) {rows}"
            )
        return values.eq(1)

    def _prepare_photometry(self, frame: pd.DataFrame, *, detected: bool) -> pd.DataFrame:
        """Apply an explicit survey response and quality policy before pooling rows."""

        prepared = frame.copy()
        if not detected:
            if self.survey == "lsst":
                # The current ALeRCE LSST service explicitly does not provide
                # non-detections. A non-empty response is a schema/policy drift,
                # not evidence SIDEREA can interpret safely.
                raise IngestionError("ALeRCE LSST unexpectedly returned non-detection rows")
            prepared["quality"] = True
            return prepared

        if self.survey == "ztf":
            for field in ("mjd", "fid", "magpsf", "sigmapsf"):
                self._required_column(prepared, field, "ZTF detections")
            sign_column = self._required_column(prepared, "isdiffpos", "ZTF detections")
            signs = prepared[sign_column].astype("string").str.strip().str.casefold()
            positive = signs.isin({"1", "true", "t", "yes", "y"})
            negative = signs.isin({"-1", "0", "false", "f", "no", "n"})
            invalid = signs.isna() | ~(positive | negative)
            if invalid.any():
                rows = prepared.index[invalid].tolist()[:10]
                raise IngestionError(
                    f"ALeRCE ZTF detections have invalid 'isdiffpos' at row(s) {rows}"
                )
            prepared["quality"] = positive
            return prepared

        for field in ("mjd", "band_name", "psfflux", "psffluxerr"):
            self._required_column(prepared, field, "LSST detections")
        bad = pd.Series(False, index=prepared.index, dtype=bool)
        for flag in (
            "psfflux_flag",
            "psfflux_flag_edge",
            "psfflux_flag_nogoodpixels",
            "pixelflags",
            *_LSST_PIXEL_FAILURE_FLAGS,
            *_LSST_INJECTION_FLAGS,
        ):
            bad |= self._binary_flag(prepared, flag, "LSST detections")
        # Rubin's isNegative describes the sign of a real difference-flux
        # detection; it is not a measurement-failure flag. Validate the
        # declared sign field while preserving the signed psfFlux value.
        self._binary_flag(prepared, "isnegative", "LSST detections")
        withdrawn_column = self._required_column(prepared, "timewithdrawnmjdtai", "LSST detections")
        withdrawn = prepared[withdrawn_column].notna() & prepared[withdrawn_column].astype(
            "string"
        ).str.strip().ne("")
        prepared["quality"] = ~(bad | withdrawn)
        return prepared

    def _objects(self, client: Any, query: BrokerQuery) -> pd.DataFrame:
        if self.survey == "lsst" and self.classifier in _KNOWN_LSST_TAXONOMIES:
            supported_classes = _KNOWN_LSST_TAXONOMIES[self.classifier]
            unsupported_classes = sorted(set(query.classes) - supported_classes)
            if unsupported_classes:
                raise IngestionError(
                    f"SIDEREA's qualified ALeRCE LSST profile {self.classifier!r} does not support "
                    f"classes {unsupported_classes}; supported classes are "
                    f"{sorted(supported_classes)}"
                )
        frames: list[pd.DataFrame] = []
        remaining = query.max_objects
        for class_name in query.classes:
            if remaining <= 0:
                break
            kwargs: dict[str, Any] = {
                "classifier": self.classifier,
                "class_name": class_name,
                "page_size": remaining,
                "page": 1,
                "format": "pandas",
                "survey": self.survey,
            }
            # ALeRCE 2 routes ZTF to the legacy API and LSST to the
            # multisurvey API.  Their detection-count filters deliberately
            # have different names; sending ``ndet`` to LSST is rejected by
            # the client before a request is made.
            detection_count_key = "ndet" if self.survey == "ztf" else "n_det"
            kwargs[detection_count_key] = [query.min_detections, 1_000_000]
            if self.survey == "lsst":
                # Pin upstream defaults that affect which objects and order are
                # returned; the live service may otherwise change them without
                # changing this local scientific request.
                kwargs.update(
                    {
                        "ranking": 1,
                        "probability": 0.0,
                        "order_by": "probability",
                        "order_mode": "DESC",
                    }
                )
            if query.discovered_after_mjd is not None:
                kwargs["firstmjd"] = [query.discovered_after_mjd, 1_000_000.0]
            result = self._call(
                f"object query for class {class_name!r}",
                partial(client.query_objects, **kwargs),
            )
            objects = self._as_frame(result, "query_objects")
            if not objects.empty:
                objects = objects.copy()
                if self.survey == "lsst":
                    self._validate_lsst_objects(
                        objects,
                        requested_class=class_name,
                        min_detections=query.min_detections,
                    )
                objects["_queried_class"] = class_name
                frames.append(objects)
                remaining -= len(objects)
        if not frames:
            raise IngestionError("ALeRCE query returned no candidate objects")
        combined = pd.concat(frames, ignore_index=True)
        oid_column = next(
            (name for name in ("oid", "objectId", "object_id", "source_id") if name in combined),
            None,
        )
        if oid_column is None:
            raise IngestionError("ALeRCE objects response has no object identifier")
        return combined.drop_duplicates(subset=[oid_column], keep="first").iloc[: query.max_objects]

    def _validate_lsst_objects(
        self,
        objects: pd.DataFrame,
        *,
        requested_class: str,
        min_detections: int,
    ) -> None:
        """Fail closed when the LSST service ignores or changes query semantics."""

        if self.classifier_version is None:  # Defensive invariant for direct/internal calls.
            raise IngestionError("ALeRCE LSST validation requires a classifier version")
        required = {"class_name", "classifier_name", "classifier_version", "n_det"}
        missing = sorted(required - set(objects.columns))
        if missing:
            raise IngestionError(
                f"ALeRCE LSST objects response is missing contract fields: {missing}"
            )
        expected_strings = {
            "class_name": requested_class,
            "classifier_name": self.classifier,
            "classifier_version": self.classifier_version,
        }
        for field, expected in expected_strings.items():
            values = objects[field].astype("string")
            mismatch = values.isna() | values.ne(expected)
            if mismatch.any():
                observed = sorted(set(values.loc[mismatch].dropna().astype(str)))
                raise IngestionError(
                    f"ALeRCE LSST response {field!r} does not match requested "
                    f"value {expected!r}; observed {observed}"
                )
        counts = pd.to_numeric(objects["n_det"], errors="coerce")
        invalid_counts = (
            counts.isna()
            | ~counts.map(math.isfinite)
            | counts.lt(min_detections)
            | counts.mod(1).ne(0)
        )
        if invalid_counts.any():
            raise IngestionError(
                "ALeRCE LSST response violates the requested minimum-detection contract"
            )

    @staticmethod
    def _object_value(row: pd.Series, names: tuple[str, ...], field: str) -> Any:
        for name in names:
            if name in row and pd.notna(row[name]):
                return row[name]
        raise IngestionError(f"ALeRCE candidate is missing {field}")

    def fetch(self, query: BrokerQuery) -> IngestionBatch:
        client = self._client()
        objects = self._objects(client, query)
        rows: list[pd.DataFrame] = []
        classes: dict[str, str] = {}
        for _, candidate in objects.iterrows():
            oid = str(
                self._object_value(
                    candidate, ("oid", "objectId", "object_id", "source_id"), "identifier"
                )
            )
            ra = self._object_value(candidate, ("meanra", "ramean", "ra"), "right ascension")
            dec = self._object_value(
                candidate, ("meandec", "decmean", "dec", "declination"), "declination"
            )
            classes[oid] = str(candidate.get("_queried_class", ""))
            detections = self._as_frame(
                self._call(
                    f"detection query for {oid}",
                    partial(
                        client.query_detections,
                        oid,
                        survey=self.survey,
                        format="pandas",
                    ),
                ),
                "query_detections",
            )
            nondetections = self._as_frame(
                self._call(
                    f"non-detection query for {oid}",
                    partial(
                        client.query_non_detections,
                        oid,
                        survey=self.survey,
                        format="pandas",
                    ),
                ),
                "query_non_detections",
            )

            for photometry, detected in ((detections, True), (nondetections, False)):
                if photometry.empty:
                    continue
                enriched = self._prepare_photometry(photometry, detected=detected)
                enriched["source_id"] = oid
                enriched["ra_deg"] = ra
                enriched["dec_deg"] = dec
                enriched["is_detection"] = detected
                enriched["survey"] = f"{self.survey}/ALeRCE"
                rows.append(enriched)
        if not rows:
            raise IngestionError("ALeRCE candidates had no detection or non-detection records")

        combined = pd.concat(rows, ignore_index=True, sort=False)
        column_map = {
            "source_id": "source_id",
            "ra_deg": "ra_deg",
            "dec_deg": "dec_deg",
            "is_detection": "is_detection",
            "survey": "survey",
            "quality": "quality",
        }
        # The multi-survey client adds ``band_name`` while retaining its
        # numeric ``band`` code, and Rubin/LSST measurements use PSF-flux
        # names.  Prefer the physical passband label and bind those fields
        # explicitly so they cannot be mistaken for ZTF ``fid`` semantics.
        columns_by_name = {str(name).casefold(): str(name) for name in combined.columns}
        if self.survey == "lsst":
            lsst_columns = {
                "band": "band_name",
                "flux": "psfflux",
                "flux_error": "psffluxerr",
            }
            for logical, folded_physical in lsst_columns.items():
                physical = columns_by_name.get(folded_physical)
                if physical is not None:
                    column_map[logical] = physical
        else:
            ztf_columns = {
                "band": "fid",
                "magnitude": "magpsf",
                "magnitude_error": "sigmapsf",
                "limiting_magnitude": "diffmaglim",
                "observation_id": "candid",
            }
            for logical, folded_physical in ztf_columns.items():
                physical = columns_by_name.get(folded_physical)
                if physical is not None:
                    column_map[logical] = physical
        normalized, resolved, warnings = normalize_photometry_frame(
            combined,
            column_map=column_map,
            default_survey=f"{self.survey}/ALeRCE",
        )
        now = datetime.now(UTC).isoformat()
        return IngestionBatch(
            observations=normalized,
            source="broker:alerce",
            retrieved_at=now,
            provenance={
                "adapter": "siderea.ingest.alerce.v4",
                "survey": self.survey,
                "classifier": self.classifier,
                "classifier_version": self.classifier_version,
                "observed_classifier_versions": (
                    sorted(set(objects["classifier_version"].dropna().astype(str)))
                    if self.survey == "lsst"
                    else []
                ),
                "photometry_policy": (
                    {
                        "measurement": "psfFlux",
                        "uncertainty": "psfFluxErr",
                        "passband": "band_name",
                        "bad_quality_flags": [
                            "psfFlux_flag",
                            "psfFlux_flag_edge",
                            "psfFlux_flag_noGoodPixels",
                            "pixelFlags",
                            "pixelFlags_bad",
                            "pixelFlags_cr",
                            "pixelFlags_crCenter",
                            "pixelFlags_edge",
                            "pixelFlags_nodata",
                            "pixelFlags_nodataCenter",
                            "pixelFlags_interpolated",
                            "pixelFlags_interpolatedCenter",
                            "pixelFlags_offimage",
                            "pixelFlags_saturated",
                            "pixelFlags_saturatedCenter",
                            "pixelFlags_suspect",
                            "pixelFlags_suspectCenter",
                            "pixelFlags_streak",
                            "pixelFlags_streakCenter",
                            "timeWithdrawnMjdTai_present",
                        ],
                        "injected_source_flags": [
                            "pixelFlags_injected",
                            "pixelFlags_injectedCenter",
                            "pixelFlags_injected_template",
                            "pixelFlags_injected_templateCenter",
                        ],
                        "injected_source_policy": "reject_from_scientific_features",
                        "signed_flux_preserved": True,
                        "isNegative_is_quality_flag": False,
                        "nondetections": "unsupported_by_upstream",
                    }
                    if self.survey == "lsst"
                    else {
                        "measurement": "magpsf",
                        "uncertainty": "sigmapsf",
                        "passband": "fid",
                        "positive_subtraction_required": True,
                        "corrected_fields_used": False,
                        "nondetection_quality": "accepted_when_contract_valid",
                    }
                ),
                "network_policy": {
                    "timeout_seconds": self.timeout_seconds,
                    "user_agent": self.user_agent,
                    "max_retries": self.max_retries,
                    "backoff_seconds": self.backoff_seconds,
                    "session_policy_enforced": self._network_policy_enforced,
                },
                "classes": list(query.classes),
                "query": {
                    "max_objects": query.max_objects,
                    "discovered_after_mjd": query.discovered_after_mjd,
                    "min_detections": query.min_detections,
                },
                "candidate_classes": classes,
                "candidate_count": len(set(normalized["source_id"])),
                "row_count": len(normalized),
                "column_map": {key: value for key, value in resolved.items() if value is not None},
            },
            warnings=warnings,
        )
