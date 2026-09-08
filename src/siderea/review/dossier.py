"""Generate a portable, evidence-first candidate review dossier."""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Mapping, Sequence
from hashlib import sha256
from html import escape
from pathlib import Path
from typing import Any
from uuid import uuid4

from siderea.atomic import atomic_write_text
from siderea.provenance import stable_json
from siderea.review.evidence import light_curve_html


def _table(title: str, payload: Mapping[str, Any]) -> str:
    rows = "".join(
        f"<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>"
        for key, value in payload.items()
    )
    return f"<section><h2>{escape(title)}</h2><table>{rows}</table></section>"


def _directory_name(candidate_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", candidate_id).strip("._")
    normalized = normalized[:100] or "candidate"
    if normalized != candidate_id:
        suffix = sha256(candidate_id.encode("utf-8")).hexdigest()[:8]
        normalized = f"{normalized}-{suffix}"
    return normalized


def _atomic_text(path: Path, content: str) -> None:
    atomic_write_text(path, content)


def _canonical_json(value: Any) -> str:
    return stable_json(value)


def _version_token(candidate_version: str) -> str:
    normalized = candidate_version.strip().casefold()
    if re.fullmatch(r"[0-9a-f]{12,}", normalized):
        return normalized[:16]
    return sha256(candidate_version.encode("utf-8")).hexdigest()[:16]


def write_candidate_dossier(
    output_dir: Path,
    *,
    candidate: Mapping[str, Any],
    features: Mapping[str, Any],
    checks: Sequence[Mapping[str, Any]],
    neighbors: Sequence[Mapping[str, Any]] = (),
    lightcurve_image: str = "",
    stamp_images: Sequence[str] = (),
) -> Path:
    candidate_id = str(candidate.get("candidate_id") or candidate.get("source_id") or "candidate")
    core_payload = {
        "schema": "siderea.review_dossier.v2",
        "candidate": dict(candidate),
        "features": dict(features),
        "checks": [dict(item) for item in checks],
        "neighbors": [dict(item) for item in neighbors],
        "lightcurve_image": lightcurve_image,
        "stamp_images": list(stamp_images),
    }
    candidate_version = str(candidate.get("candidate_version", "")).strip()
    if not candidate_version:
        candidate_version = sha256(_canonical_json(core_payload).encode("utf-8")).hexdigest()
    dossier_digest = sha256(_canonical_json(core_payload).encode("utf-8")).hexdigest()
    payload = {
        **core_payload,
        "candidate_version": candidate_version,
        "dossier_digest": dossier_digest,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    directory_name = f"{_directory_name(candidate_id)}--{_version_token(candidate_version)}"
    destination = output_dir / directory_name
    if destination.exists():
        raise FileExistsError(f"dossier already exists and will not be overwritten: {destination}")
    staging = output_dir / f".{directory_name}.{os.getpid()}.{uuid4().hex}.tmp"
    staging.mkdir()

    checks_html = "".join(_table(str(item.get("service", "check")), item) for item in checks)
    neighbor_rows = (
        "".join(
            "<li>"
            f"{escape(str(item.get('candidate_id', '')))} — similarity "
            f"{escape(str(item.get('similarity', '')))} — "
            f"{escape(str(item.get('label', '')))}</li>"
            for item in neighbors
        )
        or "<li>No analogues indexed.</li>"
    )
    media = ""
    if lightcurve_image:
        media += f'<h2>Light curve</h2><img src="{escape(lightcurve_image)}" alt="Light curve">'
    if stamp_images:
        media += "<h2>Image stamps</h2>" + "".join(
            f'<img src="{escape(path)}" alt="Candidate stamp">' for path in stamp_images
        )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'">
<title>SIDEREA review — {escape(candidate_id)}</title>
<style>
body{{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033}}
table{{border-collapse:collapse;width:100%}}
th,td{{text-align:left;border-bottom:1px solid #d8deea;padding:.55rem;vertical-align:top}}
th{{width:30%}}section{{margin:2rem 0}}
img{{max-width:100%;margin:.5rem;border:1px solid #ccd3df}}
svg{{width:100%;height:auto;max-width:760px;font:12px system-ui}}figure{{margin:1rem 0}}
td,code{{overflow-wrap:anywhere}}
.warning{{background:#fff4cf;padding:1rem;border-left:5px solid #d89b00}}
</style></head>
<body><h1>SIDEREA candidate {escape(candidate_id)}</h1>
<p class="warning">Decision support only. External reporting requires fail-closed checks
and independent reviewer approval.</p>
<p>Candidate version: <code>{escape(candidate_version)}</code><br>
Dossier digest: <code>{escape(dossier_digest)}</code></p>
<section><h2>Observed light curves</h2>{light_curve_html(candidate.get("observations"))}</section>
{_table("Candidate", candidate)}{_table("Scientific features", features)}
<section><h2>Verification evidence</h2>{checks_html}</section>
<section><h2>Nearest analogues</h2><ul>{neighbor_rows}</ul></section>{media}
</body></html>"""
    try:
        _atomic_text(
            staging / "dossier.json",
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        )
        _atomic_text(staging / "index.html", html)
        staging.replace(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination / "index.html"
