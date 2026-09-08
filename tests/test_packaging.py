"""Distribution-contract checks that also run from an editable checkout."""

import tomllib
from importlib.resources import files
from importlib.util import find_spec
from pathlib import Path

import siderea


def test_runtime_package_data_is_available() -> None:
    package_root = files("siderea")

    assert package_root.joinpath("default.toml").is_file()
    assert package_root.joinpath("py.typed").is_file()


def test_source_and_distribution_versions_match() -> None:
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())

    assert siderea.__version__ == project["project"]["version"]


def test_public_distribution_and_cli_use_only_the_siderea_identity() -> None:
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())

    assert project["project"]["name"] == "siderea-astronomy"
    assert project["project"]["scripts"] == {"siderea": "siderea.cli:main"}
    assert find_spec("iris") is None
