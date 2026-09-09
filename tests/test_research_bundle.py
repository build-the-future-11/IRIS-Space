from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import re
import tarfile
from pathlib import Path

import pytest
import tomllib


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "tools" / "build_research_bundle.py"


def _load_bundle_module():
    spec = importlib.util.spec_from_file_location("build_research_bundle", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_public_bundle_metadata_and_manuscript_inputs_are_consistent() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]
    assert project["license"] == "LicenseRef-Proprietary"

    authors = {(entry["name"], entry["email"]) for entry in project["authors"]}
    assert authors == {
        ("Aadi Ajeesh Nair", "aadinair310@gmail.com"),
        ("Ryan Gomez", "ryangomez.hs@gmail.com"),
    }

    paper = (ROOT / "paper" / "siderea_transient_triage.tex").read_text(encoding="utf-8")
    assert (
        r"\title{\siderea: Evidence-Bound and Human-Supervised Triage of Optical Transient Alerts}"
        in paper
    )
    for name, email in authors:
        assert name in paper
        assert email in paper

    assert r"\section*{Data Availability}" in paper
    assert "intentionally untracked" in paper
    assert "cannot be independently reconstructed from the repository alone" in paper
    assert r"\bibliography{references}" in paper
    assert (ROOT / "paper" / "references.bib").is_file()
    assert (ROOT / "paper" / "siderea_transient_triage.bbl").is_file()
    assert (ROOT / "paper" / "arxivrefined.sty").is_file()

    figure_refs = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", paper)
    assert figure_refs
    missing = [ref for ref in figure_refs if not (ROOT / "paper" / ref).is_file()]
    assert missing == []

    release_scope = (ROOT / "docs" / "RESEARCH_ALPHA_RELEASE.md").read_text(encoding="utf-8")
    assert "LicenseRef-Proprietary" in release_scope
    assert "public visibility must not be described as permission" in release_scope
    assert "copyright owners' explicit license decision" in release_scope


def test_research_bundle_builder_is_deterministic_allowlisted_and_self_describing(
    tmp_path: Path,
) -> None:
    module = _load_bundle_module()
    first = tmp_path / "bundle-a.tar.gz"
    second = tmp_path / "bundle-b.tar.gz"
    source_revision = "a74e8ad3412d628c0ca23523f1d42e67f984cf9e"

    first_manifest = module.build_bundle(ROOT, first, source_revision)
    second_manifest = module.build_bundle(ROOT, second, source_revision)

    assert _sha256(first) == _sha256(second)
    assert first_manifest["archive_sha256"] == second_manifest["archive_sha256"]
    assert first_manifest["source_revision"] == source_revision
    assert first_manifest["license_status"] == "LicenseRef-Proprietary"
    assert (
        first_manifest["redistribution_status"]
        == "blocked_pending_explicit_copyright_owner_license_decision"
    )

    with (
        gzip.open(first, "rb") as compressed,
        tarfile.open(fileobj=compressed, mode="r:") as archive,
    ):
        names = archive.getnames()
        assert len(names) == len(set(names))
        assert "RESEARCH_BUNDLE_MANIFEST.json" in names
        assert "paper/siderea_transient_triage.tex" in names
        assert "paper/references.bib" in names
        assert "paper/siderea_transient_triage.bbl" in names
        assert "paper/figures/make_figures.py" in names
        assert "paper/research/experiment-reconstruction.json" in names
        assert "paper/research/claim-source-ledger.md" in names
        assert "src/siderea/__init__.py" in names
        assert "tests/test_research_bundle.py" in names
        assert "tools/build_research_bundle.py" in names

        forbidden_parts = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
        assert ".coverage" not in names
        assert all(not forbidden_parts.intersection(Path(name).parts) for name in names)

        manifest_member = archive.extractfile("RESEARCH_BUNDLE_MANIFEST.json")
        assert manifest_member is not None
        manifest = json.loads(manifest_member.read())
        assert manifest["source_revision"] == source_revision
        assert manifest["license_status"] == "LicenseRef-Proprietary"
        manifest_paths = {entry["path"] for entry in manifest["files"]}
        assert "paper/siderea_transient_triage.tex" in manifest_paths
        assert "paper/references.bib" in manifest_paths
        assert "tools/build_research_bundle.py" in manifest_paths


def test_research_bundle_excludes_preexisting_output_from_its_input_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_bundle_module()
    root = tmp_path / "repo"
    source = root / "README.md"
    output = root / "tools" / "bundle.tar.gz"
    source.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
    source.write_text("source\n", encoding="utf-8")
    output.write_bytes(b"stale archive that must not be re-ingested")
    monkeypatch.setattr(module, "iter_bundle_files", lambda _root: [source, output])

    manifest = module.build_bundle(root, output, "0" * 40)

    assert {entry["path"] for entry in manifest["files"]} == {"README.md"}
    with (
        gzip.open(output, "rb") as compressed,
        tarfile.open(fileobj=compressed, mode="r:") as archive,
    ):
        assert "README.md" in archive.getnames()
        assert "tools/bundle.tar.gz" not in archive.getnames()


def test_research_bundle_rejects_movable_or_malformed_revision_names(tmp_path: Path) -> None:
    module = _load_bundle_module()
    output = tmp_path / "bundle.tar.gz"

    for revision in ("", "main", "HEAD", "A" * 40, "deadbeef"):
        with pytest.raises(ValueError, match="exact lowercase 40-hex Git commit SHA"):
            module.build_bundle(ROOT, output, revision)
