"""Dependency-free evidence summaries and channel-local light-curve previews."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from html import escape
from typing import Any


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except OverflowError:
        return None


def light_curve_html(observations: Any) -> str:
    """Render measured values/error bars and magnitude limits without pooling channels.

    This is a review preview, not a publication figure. The underlying complete
    observations remain available in the evidence payload and portable dossier.
    """

    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        return "<p>No observation series is available.</p>"
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in observations:
        if isinstance(row, Mapping) and _finite(row.get("mjd")) is not None:
            groups[
                (str(row.get("survey") or "unspecified"), str(row.get("band") or "unknown"))
            ].append(row)
    sections: list[str] = []
    for (survey, band), rows in sorted(groups.items()):
        for value_key, error_key in (("magnitude", "magnitude_error"), ("flux", "flux_error")):
            points: list[tuple[float, float, float, bool]] = []
            for row in rows:
                measured = _finite(row.get(value_key))
                limit = False
                if value_key == "magnitude" and row.get("is_detection") is False:
                    measured = _finite(row.get("limiting_magnitude"))
                    limit = True
                if measured is None:
                    continue
                error = _finite(row.get(error_key)) or 0.0
                points.append((float(row["mjd"]), measured, max(0.0, error), limit))
            if not points:
                continue
            points.sort()
            omitted = max(0, len(points) - 500)
            points = points[-500:]
            tmin, tmax = min(p[0] for p in points), max(p[0] for p in points)
            low, high = min(p[1] - p[2] for p in points), max(p[1] + p[2] for p in points)
            if high == low:
                low, high = low - 0.5, high + 0.5
            span = max(tmax - tmin, 1e-9)
            label = f"{survey} / {band} — {value_key}"
            if (
                not all(math.isfinite(number) for number in (low, high, span, high - low))
                or high <= low
            ):
                sections.append(
                    f"<p>{escape(label)} exceeds the preview's numeric range. "
                    "Inspect the complete observation evidence below.</p>"
                )
                continue
            marks = []
            for time, value, error, is_limit in points:
                x = 65 + 570 * ((time - tmin) / span)
                fraction = (value - low) / (high - low)
                if value_key == "flux":
                    fraction = 1 - fraction
                y = 25 + 150 * fraction
                delta = 150 * (error / (high - low))
                title = escape(
                    f"MJD {time:.6f}: {value:.5g}" + (" limit" if is_limit else f" ± {error:.4g}")
                )
                if is_limit:
                    shape = (
                        f'<path d="M{x - 4:.2f},{y - 3:.2f} L{x + 4:.2f},{y - 3:.2f} '
                        f'L{x:.2f},{y + 4:.2f} Z" fill="#a34b00"/>'
                    )
                else:
                    shape = (
                        f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y - delta:.2f}" '
                        f'y2="{y + delta:.2f}" stroke="#245c9c"/>'
                        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="#245c9c"/>'
                    )
                marks.append(f"<g><title>{title}</title>{shape}</g>")
            top, bottom = (high, low) if value_key == "flux" else (low, high)
            sections.append(
                f"<figure><figcaption>{escape(label)}</figcaption>"
                f'<svg viewBox="0 0 680 215" role="img" aria-label="{escape(label)}">'
                '<rect x="65" y="25" width="570" height="150" fill="#f5f7fa" stroke="#b8c3d0"/>'
                f'<text x="3" y="32">{top:.4g}</text><text x="3" y="175">{bottom:.4g}</text>'
                f'<text x="65" y="202">{tmin:.3f}</text><text x="560" y="202">{tmax:.3f}</text>'
                '<text x="315" y="202">MJD</text>' + "".join(marks) + "</svg>"
                f"<p>{len(points)} points. Circles show measurements; "
                "triangles show magnitude limits. "
                + (f"{omitted} older points omitted from this preview. " if omitted else "")
                + (
                    "Brighter magnitudes appear higher."
                    if value_key == "magnitude"
                    else "Flux is shown in the supplied input units."
                )
                + "</p></figure>"
            )
    return "".join(sections) or "<p>No finite measurements or magnitude limits are available.</p>"


def evidence_summary(payload: Mapping[str, Any]) -> str:
    gate = payload.get("gate", {})
    quality = payload.get("quality", {})
    score = payload.get("score", {})
    gate = gate if isinstance(gate, Mapping) else {}
    quality = quality if isinstance(quality, Mapping) else {}
    score = score if isinstance(score, Mapping) else {}
    rows = [
        ("Priority (not probability)", score.get("priority_score", "unavailable")),
        ("Evidence gate", gate.get("decision", "unavailable")),
        ("Quality", "passed" if quality.get("passed") is True else "not passed"),
        ("Human approval", payload.get("approval_reason", "see review history")),
    ]
    reasons = gate.get("reasons", [])
    reasons = reasons if isinstance(reasons, (list, tuple)) else []
    return (
        '<section aria-label="Evidence summary"><h2>Decision evidence</h2><dl>'
        + "".join(f"<dt>{escape(label)}</dt><dd>{escape(str(value))}</dd>" for label, value in rows)
        + "</dl><ul>"
        + "".join(f"<li>{escape(str(reason))}</li>" for reason in reasons)
        + "</ul></section>"
    )
