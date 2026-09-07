from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.atomic import atomic_create_binary, atomic_write_bytes, atomic_write_text


class AtomicWriteTests(unittest.TestCase):
    def test_precreated_symlink_temp_is_never_followed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            destination = root / "result.json"
            victim = root / "victim.txt"
            victim.write_text("SAFE", encoding="utf-8")
            predictable = root / ".result.json.predictable.tmp"
            predictable.symlink_to(victim)

            with patch(
                "iris.atomic.secrets.token_hex",
                side_effect=("predictable", "exclusive"),
            ):
                atomic_write_text(destination, '{"ok": true}\n')

            self.assertEqual(victim.read_text(encoding="utf-8"), "SAFE")
            self.assertTrue(predictable.is_symlink())
            self.assertEqual(destination.read_text(encoding="utf-8"), '{"ok": true}\n')

    def test_failed_replace_cleans_the_exclusive_temporary(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            destination = root / "result.bin"
            destination.write_bytes(b"old")
            temporary = root / ".result.bin.exclusive.tmp"

            with (
                patch("iris.atomic.secrets.token_hex", return_value="exclusive"),
                patch("iris.atomic.os.replace", side_effect=OSError("injected failure")),
                self.assertRaisesRegex(OSError, "injected failure"),
            ):
                atomic_write_bytes(destination, b"new")

            self.assertEqual(destination.read_bytes(), b"old")
            self.assertFalse(temporary.exists())

    def test_create_binary_refuses_to_overwrite_an_existing_name(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "model.bin"
            destination.write_bytes(b"trusted")

            with self.assertRaises(FileExistsError):
                atomic_create_binary(destination, lambda handle: handle.write(b"replacement"))

            self.assertEqual(destination.read_bytes(), b"trusted")


if __name__ == "__main__":
    unittest.main()
