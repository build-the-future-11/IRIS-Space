#!/usr/bin/env python3
"""Fail-closed tombstone for the retired legacy TNS report builder.

SIDEREA deliberately provides no report-construction or TNS submission transport
through this script. Historical source is retained as non-executable Markdown
in ``legacy_build_tns_report_historical.md``.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

EXIT_REPORTING_DISABLED = 78
DISABLED_MESSAGE = """\
ERROR: legacy TNS report generation is disabled.

This script predates version-bound SIDEREA evidence, independent review, and the
current reporting_preflight. It will not read candidate data, contact services,
create output directories, or emit Markdown/JSON report material.

Use the canonical `siderea` workflow to verify and review an exact candidate
version. SIDEREA currently provides no TNS report builder or submission endpoint.
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Refuse every invocation before processing arguments or writing files."""

    del argv
    print(DISABLED_MESSAGE, file=sys.stderr)
    return EXIT_REPORTING_DISABLED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
