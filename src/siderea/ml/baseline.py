"""Leakage-resistant supervised baseline for candidate prioritisation.

The baseline deliberately keeps three concepts separate:

* the classifier is fitted only on the earliest chronological partition;
* optional sigmoid calibration is fitted only on a later, held-out partition;
* all reported diagnostics are computed on the latest partition.

The returned values are called *scores* unless held-out calibration was
successfully fitted.  This avoids presenting an uncalibrated classifier output
as a calibrated scientific probability.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
from numpy.typing import NDArray

from siderea.atomic import atomic_write_text
from siderea.evaluation import ranking_metrics

SKLEARN_AVAILABLE = importlib.util.find_spec("sklearn") is not None

AnyArray = NDArray[Any]
FloatArray = NDArray[np.float64]
IndexArray = NDArray[np.int64]
LabelArray = NDArray[np.int8]
ObjectArray = NDArray[np.object_]
FeatureInput = Sequence[Sequence[float | None]] | AnyArray


class MissingOptionalDependency(RuntimeError):
    """Raised when supervised-model functionality is used without scikit-learn."""


@dataclass(frozen=True, slots=True)
class BaselineConfig:
    """Configuration for a chronological logistic-regression baseline."""

    train_fraction: float = 0.70
    calibration_fraction: float = 0.15
    calibration: str = "sigmoid"
    min_calibration_per_class: int = 5
    regularization_c: float = 1.0
    max_iterations: int = 2_000
    random_state: int = 2026
    evaluation_review_budget: int = 10

    def __post_init__(self) -> None:
        integer_fields = {
            "min_calibration_per_class": self.min_calibration_per_class,
            "max_iterations": self.max_iterations,
            "random_state": self.random_state,
            "evaluation_review_budget": self.evaluation_review_budget,
        }
        if any(
            isinstance(value, bool) or not isinstance(value, (int, np.integer))
            for value in integer_fields.values()
        ):
            raise ValueError("baseline count, iteration, seed, and budget fields must be integers")
        for name, value in integer_fields.items():
            object.__setattr__(self, name, int(value))
        if (
            isinstance(self.train_fraction, bool)
            or not math.isfinite(self.train_fraction)
            or not 0.0 < self.train_fraction < 1.0
        ):
            raise ValueError("train_fraction must be between zero and one")
        if (
            isinstance(self.calibration_fraction, bool)
            or not math.isfinite(self.calibration_fraction)
            or not 0.0 < self.calibration_fraction < 1.0
        ):
            raise ValueError("calibration_fraction must be between zero and one")
        if self.train_fraction + self.calibration_fraction >= 1.0:
            raise ValueError("train and calibration fractions must leave a test partition")
        if self.calibration not in {"sigmoid", "none"}:
            raise ValueError("calibration must be 'sigmoid' or 'none'")
        if self.min_calibration_per_class < 1:
            raise ValueError("min_calibration_per_class must be positive")
        if (
            isinstance(self.regularization_c, bool)
            or not math.isfinite(self.regularization_c)
            or self.regularization_c <= 0.0
        ):
            raise ValueError("regularization_c must be finite and positive")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        if self.random_state < 0:
            raise ValueError("random_state must be non-negative")
        if self.evaluation_review_budget < 1:
            raise ValueError("evaluation_review_budget must be positive")
        for name in ("train_fraction", "calibration_fraction", "regularization_c"):
            object.__setattr__(self, name, float(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class ChronologicalSplit:
    """Indices for strictly ordered train, calibration, and test partitions."""

    train: IndexArray
    calibration: IndexArray
    test: IndexArray
    purged_rows: int = 0

    def __post_init__(self) -> None:
        for name in ("train", "calibration", "test"):
            values: IndexArray = np.asarray(getattr(self, name), dtype=np.int64)
            if values.ndim != 1:
                raise ValueError(f"{name} indices must be one-dimensional")
            object.__setattr__(self, name, values)
        if self.purged_rows < 0:
            raise ValueError("purged_rows must be non-negative")


@dataclass(frozen=True, slots=True)
class BaselineMetadata:
    """JSON-serialisable provenance and semantics for one fitted baseline."""

    schema_version: int
    model_family: str
    sklearn_version: str
    trained_at_utc: str
    dataset_sha256: str
    feature_names: tuple[str, ...]
    training_config: dict[str, float | int | str]
    random_state: int
    entity_purging_applied: bool
    entity_policy: str
    split_sha256: str
    train_rows: int
    calibration_rows: int
    test_rows: int
    purged_rows: int
    train_time_range: tuple[float, float]
    calibration_time_range: tuple[float, float]
    test_time_range: tuple[float, float]
    train_class_counts: dict[str, int]
    calibration_requested: bool
    calibration_method: str | None
    calibration_applied: bool
    calibration_reason: str
    score_semantics: str
    test_diagnostics: dict[str, float | int | str]

    def to_dict(self) -> dict[str, Any]:
        """Return metadata composed only of JSON-compatible values."""

        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        """Serialise the metadata deterministically for manifests and audits."""

        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def write_json(self, path: str | Path) -> Path:
        """Atomically write metadata without serialising executable model code."""

        destination = Path(path)
        atomic_write_text(destination, self.to_json())
        return destination


@dataclass(slots=True)
class SupervisedBaseline:
    """Fitted classifier plus an optional independently fitted calibrator."""

    estimator: Any
    calibrator: Any | None
    metadata: BaselineMetadata

    def __post_init__(self) -> None:
        if (self.calibrator is not None) != self.metadata.calibration_applied:
            raise ValueError("calibrator and metadata.calibration_applied disagree")

    @property
    def is_calibrated(self) -> bool:
        """Whether scores have held-out calibration and may be read as probabilities."""

        return self.metadata.calibration_applied

    def predict_scores(self, values: FeatureInput) -> FloatArray:
        """Return bounded scores, calibrated only when metadata says they are."""

        matrix = _feature_matrix(values, expected_columns=len(self.metadata.feature_names))
        base_scores = _positive_class_scores(self.estimator, matrix)
        if self.calibrator is None:
            return base_scores
        logits = _logit(base_scores).reshape(-1, 1)
        return _positive_class_scores(self.calibrator, logits)

    def predict_feature_records(
        self,
        records: Sequence[Mapping[str, float | None]],
    ) -> FloatArray:
        """Score named feature records in the exact fitted feature order.

        Missing values must be explicit ``None``/NaN values. Missing or extra
        keys are rejected so a reordered or changed feature contract cannot be
        consumed silently.
        """

        if not records:
            raise ValueError("feature records must be non-empty")
        expected = set(self.metadata.feature_names)
        rows: list[list[float | None]] = []
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                raise TypeError(f"feature record {index} must be a mapping")
            supplied = set(record)
            missing = sorted(expected - supplied)
            extra = sorted(supplied - expected)
            if missing or extra:
                raise ValueError(
                    f"feature record {index} does not match the fitted contract; "
                    f"missing={missing}, extra={extra}"
                )
            rows.append([record[name] for name in self.metadata.feature_names])
        return self.predict_scores(rows)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_baseline_bundle(path: str | Path, model: SupervisedBaseline) -> Path:
    """Atomically save a fitted baseline with a hash and readable metadata.

    The estimator file uses joblib/pickle and must therefore be loaded only from
    a trusted bundle. The adjacent JSON is safe to inspect without executing
    serialized Python objects.
    """

    try:
        import joblib  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - installed with scikit-learn.
        raise MissingOptionalDependency("joblib is required to save a baseline bundle") from exc
    destination = Path(path).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"baseline bundle already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    temporary.mkdir()
    try:
        model_path = temporary / "model.joblib"
        joblib.dump(model, model_path)
        manifest = {
            "format": "siderea.supervised_baseline.v1",
            "model_file": model_path.name,
            "model_sha256": _file_sha256(model_path),
            "metadata": model.metadata.to_dict(),
            "security": "joblib is executable serialization; load only trusted bundles",
        }
        (temporary / "bundle.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def load_baseline_bundle(
    path: str | Path,
    *,
    trusted: bool = False,
) -> SupervisedBaseline:
    """Load and hash-check a baseline bundle after explicit trust consent."""

    if not trusted:
        raise ValueError(
            "baseline bundles contain executable joblib data; pass trusted=True only "
            "for a bundle whose origin you trust"
        )
    try:
        import joblib
    except ImportError as exc:  # pragma: no cover - installed with scikit-learn.
        raise MissingOptionalDependency("joblib is required to load a baseline bundle") from exc
    source = Path(path).expanduser().resolve()
    manifest_path = source / "bundle.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read baseline bundle manifest: {manifest_path}") from exc
    if manifest.get("format") != "siderea.supervised_baseline.v1":
        raise ValueError("unsupported baseline bundle format")
    model_path = source / str(manifest.get("model_file", ""))
    if not model_path.is_file() or _file_sha256(model_path) != manifest.get("model_sha256"):
        raise ValueError("baseline model is missing or its SHA-256 does not match")
    model = joblib.load(model_path)
    if not isinstance(model, SupervisedBaseline):
        raise ValueError("bundle does not contain an SIDEREA SupervisedBaseline")
    readable_metadata = json.loads(model.metadata.to_json())
    if readable_metadata != manifest.get("metadata"):
        raise ValueError("serialized model metadata does not match bundle.json")
    return model


def _require_sklearn() -> tuple[Any, Any, Any, Any, str]:
    try:
        import sklearn  # type: ignore[import-untyped]
        from sklearn.impute import SimpleImputer  # type: ignore[import-untyped]
        from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
        from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
        from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - installation dependent.
        raise MissingOptionalDependency(
            "scikit-learn is required for siderea.ml.baseline; install the ML optional dependencies"
        ) from exc
    return SimpleImputer, LogisticRegression, Pipeline, StandardScaler, str(sklearn.__version__)


def _one_dimensional(values: Sequence[Any] | AnyArray, name: str) -> AnyArray:
    result = np.asarray(values)
    if result.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return result


def _feature_matrix(
    values: FeatureInput,
    *,
    expected_columns: int | None = None,
) -> FloatArray:
    matrix: FloatArray = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("features must be a non-empty two-dimensional matrix")
    if expected_columns is not None and matrix.shape[1] != expected_columns:
        raise ValueError(f"features contain {matrix.shape[1]} columns; expected {expected_columns}")
    if np.isinf(matrix).any():
        raise ValueError("features may contain NaN for missing values, but not infinity")
    if not np.isfinite(matrix).any():
        raise ValueError("features contain no finite measurements")
    return matrix


def chronological_split(
    timestamps: Sequence[float] | AnyArray,
    *,
    train_fraction: float = 0.70,
    calibration_fraction: float = 0.15,
    entity_ids: Sequence[str] | AnyArray | None = None,
) -> ChronologicalSplit:
    """Split by timestamp blocks and optionally purge cross-partition entities.

    Equal timestamps always remain in the same partition.  When ``entity_ids``
    is supplied, an entity present in a later partition is removed from every
    earlier partition, preventing repeated observations of the same source from
    leaking forward-looking identity information into training.
    """

    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between zero and one")
    if not 0.0 < calibration_fraction < 1.0:
        raise ValueError("calibration_fraction must be between zero and one")
    if train_fraction + calibration_fraction >= 1.0:
        raise ValueError("split fractions must leave a test partition")

    times = _one_dimensional(timestamps, "timestamps").astype(float)
    if len(times) < 3 or not np.isfinite(times).all():
        raise ValueError("timestamps require at least three finite rows")
    unique_times = np.unique(times)
    if len(unique_times) < 3:
        raise ValueError("at least three distinct timestamp blocks are required")

    train_blocks = int(np.floor(len(unique_times) * train_fraction))
    train_blocks = min(max(train_blocks, 1), len(unique_times) - 2)
    calibration_blocks = int(np.floor(len(unique_times) * calibration_fraction))
    calibration_blocks = max(calibration_blocks, 1)
    calibration_blocks = min(calibration_blocks, len(unique_times) - train_blocks - 1)

    train_cut = unique_times[train_blocks]
    test_cut = unique_times[train_blocks + calibration_blocks]
    order = np.argsort(times, kind="stable")
    train = order[times[order] < train_cut]
    calibration = order[(times[order] >= train_cut) & (times[order] < test_cut)]
    test = order[times[order] >= test_cut]

    purged_rows = 0
    if entity_ids is not None:
        entities = _one_dimensional(entity_ids, "entity_ids")
        if len(entities) != len(times):
            raise ValueError("entity_ids and timestamps must have equal lengths")
        normalized = np.asarray([str(value) for value in entities], dtype=object)
        test_entities = set(normalized[test].tolist())
        keep_calibration = np.asarray(
            [value not in test_entities for value in normalized[calibration]], dtype=bool
        )
        purged_rows += int((~keep_calibration).sum())
        calibration = calibration[keep_calibration]
        later_entities = test_entities | set(normalized[calibration].tolist())
        keep_train = np.asarray(
            [value not in later_entities for value in normalized[train]], dtype=bool
        )
        purged_rows += int((~keep_train).sum())
        train = train[keep_train]

    if not len(train) or not len(calibration) or not len(test):
        raise ValueError("chronological split is empty after timestamp grouping/entity purging")
    if not (
        times[train].max() < times[calibration].min()
        and times[calibration].max() < times[test].min()
    ):
        raise RuntimeError("chronological partition invariant was violated")
    return ChronologicalSplit(train, calibration, test, purged_rows)


def _positive_class_scores(estimator: Any, matrix: FloatArray) -> FloatArray:
    classes = np.asarray(estimator.classes_)
    positive = np.flatnonzero(classes == 1)
    if len(positive) != 1:
        raise RuntimeError("estimator does not expose exactly one positive class labelled 1")
    scores = np.asarray(estimator.predict_proba(matrix), dtype=float)[:, int(positive[0])]
    if not np.isfinite(scores).all():
        raise RuntimeError("estimator returned non-finite scores")
    bounded: FloatArray = np.clip(scores, 0.0, 1.0)
    return bounded


def _logit(probabilities: FloatArray) -> FloatArray:
    clipped = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1.0 - 1e-6)
    logits: FloatArray = np.log(clipped / (1.0 - clipped))
    return logits


def _time_range(times: FloatArray, indices: IndexArray) -> tuple[float, float]:
    return float(times[indices].min()), float(times[indices].max())


def _dataset_digest(
    matrix: FloatArray,
    labels: LabelArray,
    timestamps: FloatArray,
    feature_names: Sequence[str],
    entity_ids: ObjectArray | None,
) -> str:
    """Hash every input column that can affect fitting or partition purging."""

    digest = hashlib.sha256()
    header = {
        "matrix_shape": list(matrix.shape),
        "labels_shape": list(labels.shape),
        "timestamps_shape": list(timestamps.shape),
        "feature_names": list(feature_names),
        "entity_ids": None if entity_ids is None else [str(value) for value in entity_ids],
    }
    digest.update(
        json.dumps(header, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    digest.update(b"\0features\0")
    digest.update(np.ascontiguousarray(matrix, dtype=np.float64).tobytes())
    digest.update(b"\0labels\0")
    digest.update(np.ascontiguousarray(labels, dtype=np.int8).tobytes())
    digest.update(b"\0timestamps\0")
    digest.update(np.ascontiguousarray(timestamps, dtype=np.float64).tobytes())
    return digest.hexdigest()


def _split_digest(split: ChronologicalSplit) -> str:
    """Hash exact row membership for reproducible split and purge auditing."""

    digest = hashlib.sha256()
    for name in ("train", "calibration", "test"):
        digest.update(name.encode("ascii"))
        digest.update(np.ascontiguousarray(getattr(split, name), dtype=np.int64).tobytes())
    return digest.hexdigest()


def _ranking_diagnostics(
    labels: LabelArray,
    scores: FloatArray,
    *,
    review_budget: int,
    include_calibration_metrics: bool,
    calibration_bins: int = 10,
) -> dict[str, float | int | str]:
    """Evaluate ranking always and calibration only for calibrated scores."""

    metrics = ranking_metrics(
        labels,
        scores,
        review_budget=review_budget,
        calibration_bins=calibration_bins,
        calibrated_probabilities=include_calibration_metrics,
    )
    diagnostics: dict[str, float | int | str] = {
        "precision_at_k": metrics.precision_at_k,
        "recall_at_k": metrics.recall_at_k,
        "average_precision": metrics.average_precision,
        "positives": metrics.positives,
        "reviewed": metrics.reviewed,
        "boundary_tie_policy": metrics.boundary_tie_policy,
    }
    if include_calibration_metrics:
        if metrics.brier_score is None or metrics.expected_calibration_error is None:
            raise RuntimeError("calibration metrics were requested but not returned")
        diagnostics["brier_score"] = metrics.brier_score
        diagnostics["expected_calibration_error"] = metrics.expected_calibration_error
    return diagnostics


def fit_baseline(
    features: FeatureInput,
    labels: Sequence[int | bool] | AnyArray,
    timestamps: Sequence[float] | AnyArray,
    *,
    feature_names: Sequence[str] | None = None,
    entity_ids: Sequence[str] | AnyArray | None = None,
    unique_entities_asserted: bool = False,
    config: BaselineConfig | None = None,
) -> SupervisedBaseline:
    """Fit the baseline and return test-only diagnostics with explicit semantics."""

    settings = config or BaselineConfig()
    if not isinstance(unique_entities_asserted, bool):
        raise TypeError("unique_entities_asserted must be boolean")
    matrix = _feature_matrix(features)
    raw_labels = _one_dimensional(labels, "labels")
    try:
        numeric_labels = raw_labels.astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("labels must contain only binary values 0 and 1") from exc
    if not np.isfinite(numeric_labels).all() or not np.isin(numeric_labels, [0.0, 1.0]).all():
        raise ValueError("labels must contain only binary values 0 and 1")
    y = numeric_labels.astype(np.int8)
    times = _one_dimensional(timestamps, "timestamps").astype(float)
    if len(y) != len(matrix) or len(times) != len(matrix):
        raise ValueError("features, labels, and timestamps must have equal row counts")
    if not np.isfinite(times).all():
        raise ValueError("timestamps must be finite")
    if entity_ids is None and not unique_entities_asserted:
        raise ValueError(
            "entity_ids are required unless the caller explicitly asserts that every row "
            "represents a unique entity"
        )

    entities: ObjectArray | None = None
    if entity_ids is not None:
        raw_entities = _one_dimensional(entity_ids, "entity_ids")
        if len(raw_entities) != len(matrix):
            raise ValueError("entity_ids and features must have equal row counts")
        normalized_entities = [str(value).strip() for value in raw_entities]
        if any(
            not value or value.casefold() in {"none", "nan", "null"}
            for value in normalized_entities
        ):
            raise ValueError("entity_ids must contain non-empty source identifiers")
        entities = np.asarray(normalized_entities, dtype=object)

    selected_names = (
        (f"feature_{index}" for index in range(matrix.shape[1]))
        if feature_names is None
        else feature_names
    )
    names = tuple(str(name) for name in selected_names)
    if len(names) != matrix.shape[1] or len(set(names)) != len(names):
        raise ValueError("feature_names must be unique and match the matrix width")
    if any(not str(name).strip() for name in names):
        raise ValueError("feature_names must be non-empty")

    split = chronological_split(
        times,
        train_fraction=settings.train_fraction,
        calibration_fraction=settings.calibration_fraction,
        entity_ids=entities,
    )
    train_labels = y[split.train]
    if len(np.unique(train_labels)) != 2:
        raise ValueError("the chronological training partition must contain both classes")
    unsupported_columns = np.flatnonzero(~np.isfinite(matrix[split.train]).any(axis=0))
    if len(unsupported_columns):
        unsupported_names = ", ".join(names[int(index)] for index in unsupported_columns)
        raise ValueError(
            "the chronological training partition has no finite measurements for "
            f"feature(s): {unsupported_names}"
        )

    SimpleImputer, LogisticRegression, Pipeline, StandardScaler, sklearn_version = (
        _require_sklearn()
    )
    estimator = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    C=settings.regularization_c,
                    class_weight="balanced",
                    max_iter=settings.max_iterations,
                    random_state=settings.random_state,
                    solver="lbfgs",
                ),
            ),
        ]
    )
    estimator.fit(matrix[split.train], train_labels)

    calibrator: Any | None = None
    calibration_requested = settings.calibration == "sigmoid"
    calibration_reason: str
    calibration_labels = y[split.calibration]
    calibration_counts = np.bincount(calibration_labels, minlength=2)
    if not calibration_requested:
        calibration_reason = "disabled by configuration; outputs are uncalibrated model scores"
    elif int(calibration_counts.min()) < settings.min_calibration_per_class:
        calibration_reason = (
            "not applied: the held-out calibration partition needs at least "
            f"{settings.min_calibration_per_class} examples of each class"
        )
    else:
        calibration_inputs = _logit(
            _positive_class_scores(estimator, matrix[split.calibration])
        ).reshape(-1, 1)
        calibrator = LogisticRegression(
            C=1_000_000.0,
            max_iter=settings.max_iterations,
            random_state=settings.random_state,
            solver="lbfgs",
        )
        calibrator.fit(calibration_inputs, calibration_labels)
        calibration_reason = "sigmoid fitted on a strictly later held-out partition"

    calibration_applied = calibrator is not None
    semantics = (
        "held_out_sigmoid_calibrated_probability"
        if calibration_applied
        else "uncalibrated_model_score"
    )
    provisional = BaselineMetadata(
        schema_version=3,
        model_family="median-imputed-standard-logistic-regression",
        sklearn_version=sklearn_version,
        trained_at_utc=datetime.now(UTC).isoformat(),
        dataset_sha256=_dataset_digest(matrix, y, times, names, entities),
        feature_names=names,
        training_config=asdict(settings),
        random_state=settings.random_state,
        entity_purging_applied=entities is not None,
        entity_policy=(
            "purged_by_entity_id"
            if entities is not None
            else "caller_asserted_each_row_is_a_unique_entity"
        ),
        split_sha256=_split_digest(split),
        train_rows=len(split.train),
        calibration_rows=len(split.calibration),
        test_rows=len(split.test),
        purged_rows=split.purged_rows,
        train_time_range=_time_range(times, split.train),
        calibration_time_range=_time_range(times, split.calibration),
        test_time_range=_time_range(times, split.test),
        train_class_counts={
            "negative": int((train_labels == 0).sum()),
            "positive": int((train_labels == 1).sum()),
        },
        calibration_requested=calibration_requested,
        calibration_method="sigmoid" if calibration_requested else None,
        calibration_applied=calibration_applied,
        calibration_reason=calibration_reason,
        score_semantics=semantics,
        test_diagnostics={},
    )
    fitted = SupervisedBaseline(estimator, calibrator, provisional)
    test_scores = fitted.predict_scores(matrix[split.test])
    diagnostics = _ranking_diagnostics(
        y[split.test],
        test_scores,
        review_budget=settings.evaluation_review_budget,
        include_calibration_metrics=calibration_applied,
    )
    fitted.metadata = replace(provisional, test_diagnostics=diagnostics)
    return fitted


__all__ = [
    "SKLEARN_AVAILABLE",
    "BaselineConfig",
    "BaselineMetadata",
    "ChronologicalSplit",
    "MissingOptionalDependency",
    "SupervisedBaseline",
    "chronological_split",
    "fit_baseline",
    "load_baseline_bundle",
    "save_baseline_bundle",
]
