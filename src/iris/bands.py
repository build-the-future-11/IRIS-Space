"""Canonical passband labels shared by feature and representation pipelines."""

from __future__ import annotations

import math
from typing import Any

_ZTF_NUMERIC_ALIASES = {
    "1": "g",
    "1.0": "g",
    "2": "r",
    "2.0": "r",
    "3": "i",
    "3.0": "i",
}

_TEXT_ALIASES = {
    "zg": "g",
    "zr": "r",
    "zi": "i",
    "ztfg": "g",
    "ztfr": "r",
    "ztfi": "i",
}


def normalize_passband(value: Any, *, map_ztf_numeric: bool = True) -> str | None:
    """Return a stable lower-case passband or ``None`` for missing values.

    With ``map_ztf_numeric=True``, identifiers 1/2/3 follow the ZTF/ALeRCE
    ``fid`` convention.  Set it false when a project-specific numeric filter
    vocabulary is authoritative.
    """

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip().casefold()
    # ``pandas.NA`` and ``pandas.NaT`` deliberately stringify instead of
    # supporting truth-value coercion.  Recognize their stable spellings here
    # without making this dependency-light module import pandas.
    if not text or text in {"<na>", "nan", "nat", "none", "null"}:
        return None
    compact = text.replace("_", "").replace("-", "")
    if map_ztf_numeric and compact in _ZTF_NUMERIC_ALIASES:
        return _ZTF_NUMERIC_ALIASES[compact]
    return _TEXT_ALIASES.get(compact, text)


__all__ = ["normalize_passband"]
