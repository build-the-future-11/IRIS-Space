"""Prospective-study and scientific-evaluation infrastructure."""

from siderea.research.benchmark import run_rolling_origin_benchmark
from siderea.research.cohort import CohortRegistry, CohortSelection, export_matured_cohort
from siderea.research.injection import run_injection_recovery
from siderea.research.preregistration import (
    Preregistration,
    freeze_preregistration,
    load_preregistration,
)

__all__ = [
    "CohortRegistry",
    "CohortSelection",
    "Preregistration",
    "export_matured_cohort",
    "freeze_preregistration",
    "load_preregistration",
    "run_injection_recovery",
    "run_rolling_origin_benchmark",
]
