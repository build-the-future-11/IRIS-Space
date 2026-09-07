"""Distribution-contract checks that also run from an editable checkout."""

import tomllib
from importlib.resources import files
from pathlib import Path

import iris


def test_runtime_package_data_is_available() -> None:
    package_root = files("iris")

    assert package_root.joinpath("default.toml").is_file()
    assert package_root.joinpath("py.typed").is_file()


def test_source_and_distribution_versions_match() -> None:
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())

    assert iris.__version__ == project["project"]["version"]
