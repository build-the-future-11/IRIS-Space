"""Prospective-study and scientific-evaluation infrastructure."""

from siderea.research.benchmark import run_rolling_origin_benchmark
from siderea.research.cohort import CohortRegistry, CohortSelection, export_matured_cohort
from siderea.research.injection import run_injection_recovery
from siderea.research.pilot import assemble_shadow_evidence, build_integrated_shadow_queue
from siderea.research.preregistration import (
    Preregistration,
    freeze_preregistration,
    load_preregistration,
)
from siderea.research.run import (
    inspect_jepa_dataset_contract,
    load_shadow_run_spec,
    run_shadow_pilot,
)

__all__ = [
    "CohortRegistry",
    "CohortSelection",
    "Preregistration",
    "assemble_shadow_evidence",
    "build_integrated_shadow_queue",
    "export_matured_cohort",
    "freeze_preregistration",
    "load_preregistration",
    "inspect_jepa_dataset_contract",
    "load_shadow_run_spec",
    "run_injection_recovery",
    "run_rolling_origin_benchmark",
    "run_shadow_pilot",
]
