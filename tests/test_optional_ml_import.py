"""Exercise the supported installation profile without the optional ML extra."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_pure_prequential_utilities_import_when_torch_is_unavailable() -> None:
    code = """
import importlib.abc
import sys

class ExcludeTorch(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'torch' or fullname.startswith('torch.'):
            raise ModuleNotFoundError('optional torch intentionally unavailable')

sys.meta_path.insert(0, ExcludeTorch())
from siderea.ml import TORCH_AVAILABLE, LightCurveDataset
from siderea.ml.prequential import build_prequential_examples
assert TORCH_AVAILABLE is False
assert build_prequential_examples([]) == []
try:
    LightCurveDataset([])
except RuntimeError as exc:
    assert 'requires PyTorch' in str(exc)
else:
    raise AssertionError('tensor entry point did not reject missing torch')
"""
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, PYTHONPATH=str(root / "src"))
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
