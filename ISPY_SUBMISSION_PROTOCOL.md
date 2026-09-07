# I SPY — Transient Submission Protocol

**Version:** 1.0
**Effective:** 2026-08-09
**Owner:** Aadi Ajeesh Nair
**TNS reporting group:** I Spy (group ID `204`)

This is the binding procedure for taking a candidate from the alert stream to a TNS
submission under the I SPY name. The scientific vetting logic lives in
[`TRANSIENT_DETECTION_PLAYBOOK.md`](TRANSIENT_DETECTION_PLAYBOOK.md); this document
governs **who may do what, in what order, and what must be recorded**.

If the playbook and this protocol disagree, this protocol wins.

---

## 0. Standing configuration — do not vary per submission

Every I SPY submission uses these exact strings. Inconsistent attribution splits the
group's credit across identities and is the single easiest way to waste the reputation
the group has already built.

| Field | Value |
|---|---|
| Reporting group | `I Spy` |
| TNS group ID | `204` |
| Reporter string | `Aadi Ajeesh Nair (I Spy)` |
| Data source | `ZTF` |
| Discovery type (default) | `AT` |

Additional reporters are appended to the reporter string; the group name stays.
**Never** submit under a bare personal name or an ad-hoc affiliation.

> Historical note: earlier packets used `Ajeesh PU / Amateur astronomer of oakridge
> laboratory` and `Aadi Nair / Independent Optical Transient Search`. Both are
> deprecated. Do not reuse them.

---

## 1. Roles

| Role | May do | Requirement |
|---|---|---|
| **Screener** | Run the pipeline, inspect candidates, prepare a packet | Has read this protocol and the playbook |
| **Reviewer** | Second-eyes signoff on a packet | Has completed ≥5 supervised screenings |
| **Submitter** | Push a report to TNS | Holds TNS credentials for group 204 — currently Aadi only |

**No one submits their own candidate without a Reviewer signoff.** The Screener and
Reviewer must be different people. Until a second trained Reviewer exists, this rule
means every submission waits on Aadi — that is the intended bottleneck, not a bug.

---

## 2. Environment

All commands run from the project root:

```bash
cd /Users/aadinair/projects/helio
```

The interpreter is the project virtualenv, `.venv/bin/python`. Every command below sets
`PYTHONPYCACHEPREFIX` to keep bytecode out of the repository.

---

## 3. Stage 1 — Candidate search

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/helio_pycache .venv/bin/python astronomy/run_1000_candidate_hunt.py
```

The wrapper is configured for a 350-object non-overlapping pull. It applies:
`--exclude-previous-runs`, `--fresh-days 60`, `--early-veto-age-days 45`,
`--early-veto-detections 40`, `--early-veto-baseline-days 90`.

**Gate 1 — the run must be productive.** Open the new run folder's `summary.json` and
confirm `broker_objects > 0`. Seven runs in the campaign to date returned zero objects
because `api.alerce.online` failed to resolve. A zero-object run is a network failure,
not a null result — re-run it, and do not record it as a screening.

Locate the newest run folder:

```bash
ls -td /Users/aadinair/projects/helio/astronomy/ai_hunter_runs/run_* | head -1
```

---

## 4. Stage 2 — Shortlist triage

Open `high_priority_shortlist.csv` and `fresh_shortlist.csv`. If both are empty, the run
produced nothing reportable. Record the run in the log and stop — **an empty run is a
valid, complete outcome and must still be logged.**

A candidate proceeds only if all of:

- `classification = new_transient_candidate`
- `review_tier = high_priority`
- `early_veto = False`
- low-to-moderate `ndetections`
- short `detection_baseline_days`

---

## 5. Stage 3 — Automated rejection

Both stages are mandatory. Substitute the real run folder name for `RUN_FOLDER`.

**Moving objects and known TNS entries:**

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/helio_pycache .venv/bin/python astronomy/verify_candidates.py \
  --ranked-csv astronomy/ai_hunter_runs/RUN_FOLDER/high_priority_shortlist.csv \
  --output-dir astronomy/verification/RUN_FOLDER_high_priority
```

**Known variable stars:**

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/helio_pycache .venv/bin/python astronomy/catalog_validation_engine.py \
  --candidates-csv astronomy/ai_hunter_runs/RUN_FOLDER/high_priority_shortlist.csv \
  --output-dir astronomy/catalog_validation/RUN_FOLDER_high_priority
```

**Gate 2 — no unresolved TNS queries.** Check `verification_summary.json`. If
`tns_query_errors > 0` or `needs_tns_check > 0`, the TNS check did not complete. Re-run
the verification against the affected rows before proceeding. A candidate whose TNS
status is unknown is **not** cleared — it is unchecked.

This has bitten the project twice: `run_20260707T130026Z` needed a retry pass to clear
4 errored queries, and `run_20260721T160207Z` errored on all 3 candidates across two
attempts and was never resolved. Those 3 remain unadjudicated.

**Gate 3 — catalog rejections are final.** Anything in
`catalog_rejected_known_variables.csv` is dead. Do not appeal it on the strength of a
nice-looking light curve. Roughly 28% of candidates reaching this stage are rejected
here; that rejection rate is the group's main evidence of rigour.

Rows in `catalog_needs_review.csv` require explicit written adjudication in the packet.

---

## 6. Stage 4 — Manual inspection

Open `https://alerce.online/object/OBJECT_ID` and work through playbook steps 4–8:
object info, difference-magnitude light curve, finding chart, science/template/difference
stamps date-by-date, LC classifier, magnitude statistics, crossmatch.

**Gate 4 — the stamps must hold up across multiple dates.** A compact positive residual
at a consistent position on ≥2 dates. Reject on: single-date residuals, shape instability,
subtraction edges, ghosts, saturated-star halos, or positive-negative dipoles.

**Gate 5 — classifier veto.** If the LC classifier strongly favours `VS`, `LPV`, `RRL`,
`CEP`, `DSCT`, `YSO`, `Periodic-Other`, `QSO`, or `bogus`, stop unless the images and
catalogs both actively contradict it. Record the contradiction in writing.

---

## 7. Stage 5 — Classification wording

This gate decides what the object is *called*, and it is where a careless group destroys
its credibility.

| Situation | Required wording |
|---|---|
| Clean transient, no host coincidence | Unclassified optical transient candidate (`AT`) |
| Coincident with galaxy nucleus, or AGN probability elevated | **Possible nuclear/AGN-like optical transient** — never "supernova" |
| Catalog variable warning present | Do not submit |

The threshold that matters: **a counterpart within ~1″ plus an elevated AGN probability
forces nuclear/AGN-like wording.** `ZTF26abayrka` is the reference case — a NED galaxy at
0.4″ with AGN probability 0.815. It was correctly held back from supernova wording.

Claiming a type the data does not support is the fastest way to lose group standing.
TNS acceptance means a report was inserted as a transient candidate. It is not a
classification, and it must never be described as one.

---

## 8. Stage 6 — Packet, review, submission

Generate the packet:

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/helio_pycache .venv/bin/python astronomy/build_tns_report.py
```

The packet must contain: `tns_report_draft.md`, `tns_report_draft.json`,
`photometry_recent.csv`, and the verification and catalog-validation summaries it relies on.

**Gate 6 — Reviewer signoff.** A Reviewer who is not the Screener confirms in writing,
in the packet, that Gates 1–5 all passed. Unsigned packets are not submitted.

The Submitter then confirms the §0 strings are correct in the JSON, re-checks TNS
immediately before sending (registry state changes), and submits — single report via the
TNS form, or several via the bulk-report API with group ID 204.

---

## 9. Stage 7 — Record the outcome

**This is the step the project has historically skipped, and it is not optional.**

Append a `## Submission Outcome` section to the packet's `tns_report_draft.md`
recording: submission date (UTC), reporter, reporting group, data source, the assigned
TNS designation, the TNS objid, the object URL, and how the designation was confirmed.

`ZTF26abdqbqw` is the model — it records submission on 2026-07-05 and designation
**AT 2026rsp** (objid 212592), confirmed by TNS API search on the internal name.

Then add one line to `SUBMISSION_LOG.md` in this folder:

```
| date | internal name | designation | wording used | screener | reviewer | outcome |
```

Without this log the group cannot state its own track record, and every application it
writes has to reconstruct history from JSON files.

---

## 10. Stage 8 — After the designation

Two follow-ups convert a bare designation into scientific standing:

1. **AstroNote** — if the object is near peak and worth spectroscopic attention, publish
   one requesting classification. The precedent is AstroNote 2026-210 for AT 2026rsp.
   This is what makes other groups aware I SPY exists.
2. **Classification request** — email the relevant follow-up programs directly while the
   target is still bright. See `reports/ZTF26abdqbqw/classification_request_email.md`.

Log the AstroNote number and any resulting classification against the object.

---

## 11. Amending this protocol

Changes are made by the Owner, the version number increments, and the reason is recorded.
Anyone following an outdated copy is following a document that no longer binds — always
work from the copy in `/Users/aadinair/projects/helio/astronomy/`.

> **Repository note.** A second copy of this tree exists under
> `~/Documents/discovering astronomical gaps/astronomy/`. It is a stale snapshot
> (last run 2026-07-04) and must not be used for operations. Treat `projects/helio`
> as authoritative.
