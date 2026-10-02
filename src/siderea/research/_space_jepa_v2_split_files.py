"""Check manifest entity identity and prepared tensor bytes."""

from pathlib import Path

from siderea.provenance import digest_file

NAMES = ("train", "validation", "test")


def check_split_files(root: Path, manifest, expected):
    splits = manifest.get("splits")
    if not isinstance(splits, dict) or set(splits) != set(NAMES):
        raise ValueError("prepared split manifest differs")
    seen = set()
    receipt = {}
    for name in NAMES:
        entities = splits[name].get("entities")
        if not isinstance(entities, list) or tuple(entities) != expected[name]:
            raise ValueError(f"prepared {name} entities differ")
        if seen & set(entities):
            raise ValueError("prepared split entity overlap")
        seen.update(entities)
        actual = digest_file(root / f"{name}.pt")
        if splits[name].get("sha256") != actual:
            raise ValueError(f"prepared {name}.pt digest differs")
        receipt[name] = {"entity_count": len(entities), "sha256": actual}
    return receipt
