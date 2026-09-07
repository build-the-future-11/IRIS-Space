from __future__ import annotations

import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from iris.data import create_snapshot
from iris.manifest import RUN_MANIFEST_SCHEMA, RunManifest, _source_digest


class ReproducibilityTests(unittest.TestCase):
    def test_snapshot_content_digest_is_independent_of_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = root / "one" / "observations.csv"
            second = root / "two" / "observations.csv"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("id,value\nA,1\n", encoding="utf-8")
            second.write_text("id,value\nA,1\n", encoding="utf-8")
            one = create_snapshot("sample", [first], label_policy="none")
            two = create_snapshot("sample", [second], label_policy="none")
            self.assertEqual(one.digest, two.digest)

    def test_finished_manifest_rejects_late_mutation(self) -> None:
        manifest = RunManifest.create({"test": True})
        manifest.finish(status="completed")
        with self.assertRaisesRegex(RuntimeError, "already finished"):
            manifest.finish(status="failed")

    def test_source_digest_ignores_runtime_bytecode_caches(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = root / "src" / "iris"
            package.mkdir(parents=True)
            (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            before = _source_digest(root)
            cache = package / "__pycache__"
            cache.mkdir()
            (cache / "module.cpython-999.pyc").write_bytes(b"runtime-dependent bytecode")

            self.assertEqual(before, _source_digest(root))

    def test_source_digest_falls_back_to_an_installed_package_tree(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = root / "installed" / "iris"
            package.mkdir(parents=True)
            module = package / "module.py"
            module.write_text("VALUE = 1\n", encoding="utf-8")

            first = _source_digest(root / "empty-prefix", package_root=package)
            module.write_text("VALUE = 2\n", encoding="utf-8")
            second = _source_digest(root / "empty-prefix", package_root=package)

            self.assertNotEqual(first, sha256(b"").hexdigest())
            self.assertNotEqual(first, second)

    def test_installed_source_digest_ignores_an_unrelated_lookalike_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            active_package = root / "installed" / "iris"
            active_package.mkdir(parents=True)
            active_module = active_package / "module.py"
            active_module.write_text("ACTIVE = 1\n", encoding="utf-8")
            lookalike = root / "working" / "src" / "iris"
            lookalike.mkdir(parents=True)
            lookalike_module = lookalike / "module.py"
            lookalike_module.write_text("UNRELATED = 1\n", encoding="utf-8")

            first = _source_digest(root / "working", package_root=active_package)
            lookalike_module.write_text("UNRELATED = 2\n", encoding="utf-8")
            self.assertEqual(
                first,
                _source_digest(root / "working", package_root=active_package),
            )
            active_module.write_text("ACTIVE = 2\n", encoding="utf-8")
            self.assertNotEqual(
                first,
                _source_digest(root / "working", package_root=active_package),
            )

    def test_manifest_records_the_iris_distribution_version_slot(self) -> None:
        manifest = RunManifest.create({"test": True})
        self.assertIn("iris-astronomy", manifest.environment)

    def test_manifest_has_a_versioned_schema_and_fsyncs_publication(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "manifest.json"
            manifest = RunManifest.create({"test": True})
            manifest.finish(status="completed")
            with patch("iris.atomic.os.fsync") as fsync:
                manifest.write(path)

            self.assertGreaterEqual(fsync.call_count, 2)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["schema"],
                RUN_MANIFEST_SCHEMA,
            )

    def test_manifest_rejects_lossy_stringification_of_unknown_values(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "manifest.json"
            manifest = RunManifest.create({"test": True})
            manifest.metrics["unsupported"] = object()

            with self.assertRaises(TypeError):
                manifest.write(path)

            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
