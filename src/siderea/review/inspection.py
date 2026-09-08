"""Read-only version comparison and bounded light-curve controls."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping
from html import escape
from typing import Any
from urllib.parse import quote

from siderea.ledger import OutcomeLedger
from siderea.provenance import stable_json
from siderea.review.evidence import light_curve_html


def plot_panel(observations: Any, candidate_id: str, filters: Mapping[str, str]) -> str:
    allowed = {"start", "end", "survey", "band"}
    if set(filters) - allowed:
        raise ValueError("unknown plot filter")
    bounds: dict[str, float] = {}
    for name in ("start", "end"):
        if filters.get(name):
            bounds[name] = float(filters[name])
            if not math.isfinite(bounds[name]):
                raise ValueError("plot bounds must be finite MJD values")
    if bounds.get("start", -math.inf) > bounds.get("end", math.inf):
        raise ValueError("plot start must not exceed end")
    rows = (
        [row for row in observations if isinstance(row, Mapping)]
        if isinstance(observations, list)
        else []
    )
    selected = []
    for row in rows:
        if any(
            filters.get(key) and str(row.get(key, "")) != filters[key] for key in ("survey", "band")
        ):
            continue
        time = row.get("mjd")
        if bounds:
            if (
                isinstance(time, bool)
                or not isinstance(time, (int, float))
                or not math.isfinite(time)
            ):
                continue
            if time < bounds.get("start", -math.inf) or time > bounds.get("end", math.inf):
                continue
        selected.append(row)
    url = "/candidate/" + quote(candidate_id, safe="")
    controls = (
        f'<form method="get" action="{url}"><fieldset><legend>Plot range (preview only)</legend>'
    )
    for name in ("start", "end"):
        controls += (
            f'<label>{name.title()} MJD<input type="number" step="any" name="{name}" '
            f'value="{escape(filters.get(name, ""))}"></label>'
        )
    for name in ("survey", "band"):
        values = sorted({str(row.get(name, "")) for row in rows} | {filters.get(name, "")})
        controls += f'<label>{name.title()}<select name="{name}"><option value="">All</option>'
        for value in values:
            if value:
                selected_attribute = " selected" if value == filters.get(name) else ""
                controls += (
                    f'<option value="{escape(value)}"{selected_attribute}>{escape(value)}</option>'
                )
        controls += "</select></label>"
    controls += (
        '<button type="submit">Apply plot range</button> '
        f'<a href="{url}">Reset plot</a></fieldset></form>'
    )
    return (
        controls
        + f"<p>{len(selected)} of {len(rows)} observations match these filters. "
        + "Stored evidence is unchanged.</p>"
        + light_curve_html(selected)
    )


def version_comparison(ledger: OutcomeLedger, candidate_id: str, submitted_version: str) -> str:
    previous = ledger.candidate_version(candidate_id, submitted_version)
    current = ledger.candidate(candidate_id)
    if previous is None or current is None:
        return (
            "<p>The submitted version is unavailable; "
            "an evidence comparison cannot be reconstructed.</p>"
        )
    old, new = previous["payload"], current["payload"]
    if previous["version_digest"] == current["version_digest"]:
        return "<p>The evidence version is unchanged; correct the submission error above.</p>"

    def observations(payload: Mapping[str, Any]) -> Counter[str]:
        rows = payload.get("observations", [])
        return (
            Counter(stable_json(row) for row in rows if isinstance(row, Mapping))
            if isinstance(rows, list)
            else Counter()
        )

    before, after = observations(old), observations(new)
    added, removed = after - before, before - after
    changes = ""
    for label, values in (
        ("Added observations", added),
        ("Removed or replaced observations", removed),
    ):
        changes += f"<h3>{label}: {sum(values.values())}</h3>"
        for content, count in list(values.items())[:20]:
            changes += f"<pre>{escape(content)} (count {count})</pre>"
        if len(values) > 20:
            changes += (
                "<p>Preview limited to 20 distinct records; "
                "download both versions for the full difference.</p>"
            )
    for key in sorted((set(old) | set(new)) - {"observations"}):
        if old.get(key) != new.get(key):
            changes += f"<details><summary>Changed: {escape(key)}</summary>"
            for label, payload in (("Submitted", old), ("Current", new)):
                text = json.dumps(payload.get(key), ensure_ascii=False, sort_keys=True)
                changes += f"<p>{label}</p><pre>{escape(text[:12000])}</pre>"
                if len(text) > 12000:
                    changes += "<p>Display truncated; use the complete version download.</p>"
            changes += "</details>"
    links = ""
    for label, version in (
        ("submitted", submitted_version),
        ("current", str(current["version_digest"])),
    ):
        url = f"/evidence/{quote(candidate_id, safe='')}?version={quote(version, safe='')}"
        links += f'<p><a href="{url}">Download {label} evidence</a></p>'
    return (
        '<section aria-label="Evidence changes"><h2>Evidence changed</h2>'
        + links
        + changes
        + "</section>"
    )


def evidence_inbox(ledger: OutcomeLedger, *, page: int = 1) -> dict[str, Any]:
    """A read-only page of actual current-version preflight blockers."""
    from siderea.provenance import CheckProvenance
    from siderea.reporting import reporting_preflight

    if type(page) is not int or not 1 <= page <= 100000:
        raise ValueError("invalid inbox page")
    candidates = ledger.list_candidates(limit=51, offset=(page - 1) * 50)
    items = []
    for candidate in candidates[:50]:
        payload = candidate["payload"]
        try:
            checks = tuple(CheckProvenance.from_dict(item) for item in payload["external_checks"])
            quality = payload["quality"]["passed"]
            manual = payload["manual_review_required"]
            if type(quality) is not bool or type(manual) is not bool:
                raise ValueError("invalid evidence flags")
            result = reporting_preflight(
                candidate["candidate_id"],
                checks=checks,
                quality_passed=quality,
                manual_review_required=manual,
                ledger=ledger,
                candidate_version=candidate["version_digest"],
            )
            reasons = list(result.reasons)
            if result.ready:
                continue
        except (KeyError, TypeError, ValueError):
            reasons = [
                "Candidate has incomplete or malformed preflight inputs; reconstruct its evidence."
            ]
        items.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_version": candidate["version_digest"],
                "reasons": reasons,
                "next_action": (
                    "Inspect exact-version evidence and complete the listed checks or reviews."
                ),
            }
        )
    return {
        "schema": "siderea.evidence_inbox.v1",
        "page": page,
        "has_next": len(candidates) > 50,
        "examined_candidates": min(50, len(candidates)),
        "items": items,
        "scope": "read_only_current_preflight; no dismiss action can clear evidence",
    }


def inbox_html(report: Mapping[str, Any]) -> str:
    body = (
        '<p><a href="/">Review queue</a></p><p>These are current preflight blockers. '
        "This view cannot dismiss or clear them.</p>"
    )
    for item in report["items"]:
        url = "/candidate/" + quote(item["candidate_id"], safe="")
        body += f'<section><h2><a href="{url}">{escape(item["candidate_id"])}</a></h2>'
        body += f"<p>Evidence version: <code>{escape(item['candidate_version'])}</code></p><ul>"
        body += "".join(f"<li>{escape(reason)}</li>" for reason in item["reasons"])
        body += "</ul><p>" + escape(item["next_action"]) + "</p></section>"
    if not report["items"]:
        body += "<p>No blockers found among the candidates examined on this page.</p>"
    body += (
        f'<p>{report["examined_candidates"]} candidates examined.</p><nav aria-label="Inbox pages">'
    )
    page = report["page"]
    if page > 1:
        body += f'<a href="/inbox?page={page - 1}">Previous</a> '
    if report["has_next"]:
        body += f'<a href="/inbox?page={page + 1}">Next</a>'
    return body + "</nav>"
