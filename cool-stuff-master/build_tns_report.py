#!/usr/bin/env python3
"""Fail-closed tombstone for the archived legacy TNS report builder."""

from __future__ import annotations

import sys
from collections.abc import Sequence

EXIT_REPORTING_DISABLED = 78
DISABLED_MESSAGE = """\
ERROR: legacy TNS report generation is disabled.

This archived script predates version-bound IRIS evidence, independent review,
and the current reporting_preflight. It will not read candidate data, contact
services, create output directories, or emit Markdown/JSON report material.

Use the canonical `iris` workflow to verify and review an exact candidate
version. IRIS currently provides no TNS report builder or submission endpoint.
Historical source is retained only as non-executable Markdown at
`../legacy_build_tns_report_historical.md`.
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Refuse every invocation before processing arguments or writing files."""

    del argv
    print(DISABLED_MESSAGE, file=sys.stderr)
    return EXIT_REPORTING_DISABLED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
