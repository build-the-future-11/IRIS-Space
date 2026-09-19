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
from siderea.research.space_jepa_v2_benchmark import (
    extrapolation_forecast,
    run_space_jepa_v2_benchmark,
    verify_complete_grid,
)
from siderea.research.space_jepa_v2_campaign import (
    run_space_jepa_v2_campaign,
    verify_space_jepa_v2_campaign,
)
from siderea.research.space_jepa_v2_pipeline import assemble_space_jepa_v2_shadow_evidence
from siderea.research.space_jepa_v2_protocol import (
    SpaceJEPAV2Protocol,
    freeze_space_jepa_v2_protocol,
    load_space_jepa_v2_protocol,
)

__all__ = [
    "CohortRegistry",
    "CohortSelection",
    "Preregistration",
    "SpaceJEPAV2Protocol",
    "assemble_shadow_evidence",
    "build_integrated_shadow_queue",
    "assemble_space_jepa_v2_shadow_evidence",
    "extrapolation_forecast",
    "export_matured_cohort",
    "freeze_preregistration",
    "freeze_space_jepa_v2_protocol",
    "load_preregistration",
    "inspect_jepa_dataset_contract",
    "load_shadow_run_spec",
    "load_space_jepa_v2_protocol",
    "run_injection_recovery",
    "run_rolling_origin_benchmark",
    "run_space_jepa_v2_benchmark",
    "run_space_jepa_v2_campaign",
    "run_shadow_pilot",
    "verify_complete_grid",
    "verify_space_jepa_v2_campaign",
]
