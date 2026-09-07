# Archived historical duplicate

This directory is an archived duplicate of the original root-level I SPY
workflow. It is retained for provenance and comparison during the IRIS migration.

Do not develop or run new production work from this directory. The canonical new
platform is `../src/iris/`; the canonical retained legacy scripts are at the
repository root. The executable `build_tns_report.py` copy is a fail-closed
tombstone: it always exits without reading inputs, contacting services, or writing
report material. Its historical source is preserved as non-executable Markdown in
`../legacy_build_tns_report_historical.md`.

For current status and migration rules, read `../README.md` and
`../docs/MIGRATION.md`.

---

# I SPY — Optical Transient Detection Pipeline

Search public ZTF alert data (brokered via [ALeRCE](https://alerce.online/)) for
real astrophysical transients, reject the things that only look like one, and
prepare a submission draft for the
[Transient Name Server](https://www.wis-tns.org/).

Candidates are rejected if they match known variable stars, moving Solar System
objects, long-lived variability, image artifacts, or sources already reported to
TNS. What survives is ranked for manual inspection — the pipeline proposes, a
human decides.

Reporting group: **I Spy** (TNS group ID `204`).

## Scope of this repository

Source only. Run outputs, the ALeRCE light-curve cache, candidate shortlists,
generated TNS report packages and correspondence are deliberately untracked —
see [`.gitignore`](.gitignore). Every result is reproducible by re-running the
pipeline against the live alert stream.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

TNS submission requires bot credentials, passed as flags (never committed):

```bash
.venv/bin/python verify_candidates.py \
  --tns-api-key "$TNS_API_KEY" \
  --tns-bot-id "$TNS_BOT_ID" \
  --tns-bot-name "$TNS_BOT_NAME"
```

## Pipeline stages

| Stage | Script | Role |
|---|---|---|
| 1. Sweep | `run_1000_candidate_hunt.py` | Wrapper over the hunter with vetted defaults for a non-overlapping ~350-object run |
| 1a. Intake | `ai_candidate_hunter.py` | Uses ALeRCE broker classifications as ML intake, then scores light-curve features to rank objects |
| 1b. Fetch | `fetch_alerce_detections.py` | Pulls live ALeRCE/ZTF detections into a CSV for the pipeline |
| 2. Features | `optical_transient_pipeline.py` | End-to-end run for a single target: ZTF light curves from IRSA (or local CSV), cleaning, variability statistics, periodicity |
| 3. Screen | `catalog_validation_engine.py` | Conservative pre-report screen against stellar and variable-star catalogs |
| 4. Verify | `verify_candidates.py` | SkyBoT moving-object rejection, ALeRCE cross-check, TNS duplicate search |
| 5. Gate | `final_candidate_filter.py` | Last safety gate; marks a candidate reportable only if every check passes |
| 6. Report | `build_tns_report.py` | Retired fail-closed tombstone; report generation is unavailable |

Two companion searches share the same feature machinery:

- `blackhole_candidate_hunter.py` — ranks TDE/AGN-flare-like behaviour for follow-up. It ranks candidates; it does not confirm black holes.
- `distant_reservoir_catalog.py` — builds a known-object catalogue of KBO/TNO, Centaur and long-period comet candidates from JPL SBDB orbital elements. It characterises known objects; it does not discover new ones.

## Quick start

```bash
.venv/bin/python run_1000_candidate_hunt.py
```

Then inspect the newest run directory: start with `high_priority_shortlist.csv`
and `fresh_shortlist.csv`. If both are empty, that run has nothing reportable.

## Documentation

- [`TRANSIENT_DETECTION_PLAYBOOK.md`](TRANSIENT_DETECTION_PLAYBOOK.md) — the scientific vetting workflow, step by step.
- [`ISPY_SUBMISSION_PROTOCOL.md`](ISPY_SUBMISSION_PROTOCOL.md) — the binding procedure for who may submit what, in what order. Where the two disagree, the protocol wins.
- [`PIPELINE_OPERATIONS_RECORD.md`](PIPELINE_OPERATIONS_RECORD.md) — screening counts and rejection reasons for the 2026-04-07 → 2026-07-30 campaign.

## Data sources

Public ZTF alert stream via ALeRCE · IRSA ZTF light curves · IMCCE SkyBoT ·
JPL Small-Body Database · TNS.
