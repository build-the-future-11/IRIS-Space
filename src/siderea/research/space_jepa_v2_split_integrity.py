"""Read-only provenance verification for prepared Space JEPA 2 splits."""

from siderea.research._space_jepa_v2_split_files import check_split_files
from siderea.research._space_jepa_v2_split_manifest import load_bound_manifest
from siderea.research._space_jepa_v2_split_source import expected_splits


def verify_prepared_splits(prepared, source, protocol):
    root, _, manifest, stored = load_bound_manifest(prepared, source)
    frozen, expected = expected_splits(source, protocol)
    if manifest.get("horizons_days") != list(frozen.horizons_days):
        raise ValueError("prepared horizons differ from frozen protocol")
    return {
        "schema": "siderea.space_jepa_v2_split_integrity.v1",
        "status": "PASS",
        "protocol_digest": frozen.protocol_digest,
        "prepared_manifest_digest": stored,
        "pairwise_entity_disjoint": True,
        "splits": check_split_files(root, manifest, expected),
        "scope": "integrity_only_no_model_execution",
    }
