from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_REPORTERS = (
    PROJECT_ROOT / "build_tns_report.py",
    PROJECT_ROOT / "cool-stuff-master" / "build_tns_report.py",
)


class LegacyReportingQuarantineTests(unittest.TestCase):
    def invoke(self, script: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, str(script), *arguments],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_every_legacy_reporter_refuses_single_and_bulk_output(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix=".legacy-report-quarantine-", dir=PROJECT_ROOT
        ) as temporary:
            temporary_path = Path(temporary)
            invocations = (
                [
                    "--candidate-id",
                    "ZTF-test",
                    "--verification-csv",
                    str(temporary_path / "verification.csv"),
                    "--output-dir",
                    str(temporary_path / "single-output"),
                ],
                [
                    "--bulk",
                    "--candidates",
                    "ZTF-test:PSN",
                    "--output-dir",
                    str(temporary_path / "bulk-output"),
                ],
                ["--help"],
            )

            for script in LEGACY_REPORTERS:
                for arguments in invocations:
                    with self.subTest(script=script, arguments=arguments):
                        result = self.invoke(script, arguments)
                        self.assertEqual(result.returncode, 78)
                        self.assertEqual(result.stdout, "")
                        self.assertIn("legacy TNS report generation is disabled", result.stderr)
                        self.assertIn("provides no TNS report builder", result.stderr)

            self.assertFalse((temporary_path / "single-output").exists())
            self.assertFalse((temporary_path / "bulk-output").exists())

    def test_historical_implementation_is_non_executable_reference(self) -> None:
        archive = PROJECT_ROOT / "legacy_build_tns_report_historical.md"
        source = archive.read_text(encoding="utf-8")

        self.assertTrue(source.startswith("# Archived historical source"))
        self.assertIn("```python", source)
        self.assertTrue(source.rstrip().endswith("```"))
        self.assertNotIn(archive, LEGACY_REPORTERS)


if __name__ == "__main__":
    unittest.main()
