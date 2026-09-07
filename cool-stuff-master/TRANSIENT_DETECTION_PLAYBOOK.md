# Transient Detection Playbook

This is the exact workflow to find, validate, and decide whether a ZTF/ALeRCE candidate should be considered for TNS reporting.

## Goal

Find an object that looks like a real astrophysical transient, not a known variable star, moving Solar System object, image artifact, or already-reported TNS source.

Use this sentence when explaining the pipeline:

> I search public ZTF/ALeRCE alert data for objects with transient-like light curves, then reject candidates that match known variables, moving objects, old long-lived variability, image artifacts, or existing TNS objects.

## Step 1: Run A Non-Overlapping Candidate Search

From the project folder:

```bash
cd /Users/aadinair/projects/helio
env PYTHONPYCACHEPREFIX=/private/tmp/helio_pycache .venv/bin/python astronomy/run_1000_candidate_hunt.py
```

Even though the filename says `run_1000_candidate_hunt.py`, the wrapper is currently configured for a 350-candidate non-overlap run.

The command should include these ideas:

- `--max-objects 350`: search 350 broker objects.
- `--exclude-previous-runs`: avoid objects already scanned in previous runs.
- `--fresh-days 60`: prefer recent candidates.
- `--early-veto-age-days 45`: down-rank old first detections.
- `--early-veto-detections 40`: down-rank objects with many detections.
- `--early-veto-baseline-days 90`: down-rank long-lived variability.

Use this sentence while it is running:

> The pipeline is fetching a fresh non-overlapping ALeRCE/ZTF dataset, scoring the light curves, and writing shortlists for manual review.

## Step 2: Open The Newest Run Folder

After the run finishes, find the newest output folder:

```bash
ls -td /Users/aadinair/projects/helio/astronomy/ai_hunter_runs/run_* | head -1
```

Important files:

- `summary.json`: counts of fetched objects, ranked candidates, vetoed candidates, and shortlist size.
- `high_priority_shortlist.csv`: best candidates to inspect first.
- `fresh_shortlist.csv`: recent candidates that survived early filters.
- `ai_ranked_candidates.csv`: all ranked candidates.
- `early_veto_rejected.csv`: candidates rejected as old, long-lived, dense, or likely variable/AGN-like.

Use this sentence:

> I first inspect `high_priority_shortlist.csv` and `fresh_shortlist.csv`; if they are empty, there is probably nothing reportable in that run.

## Step 3: Pick A Candidate To Inspect

A candidate is worth opening in ALeRCE if it has:

- `classification = new_transient_candidate`
- `review_tier = high_priority`
- `early_veto = False`
- Low or moderate `ndetections`
- Short `detection_baseline_days`
- No obvious catalog rejection yet

Use this sentence:

> A good first-look candidate should be recent, not long-lived, not detection-heavy, and not already vetoed by the pipeline.

## Step 4: Inspect The ALeRCE Page

Open:

```text
https://alerce.online/object/OBJECT_ID
```

Replace `OBJECT_ID` with the candidate internal name, for example:

```text
https://alerce.online/object/ZTF26abayrka
```

On the ALeRCE page, check these panels in this order:

1. Object information
2. Difference magnitude light curve
3. Finding chart
4. Science/template/difference stamps
5. LC classifier
6. Magnitude statistics
7. Crossmatch section

In the Object information panel, write down:

- Object/internal name
- RA and Dec
- Discovery date
- Last detection date
- Number of detections
- Number of non-detections
- Whether ALeRCE marks it as stellar
- Whether ALeRCE marks it as corrected

Use this sentence:

> I am checking whether the alert is a one-time transient-like event or repeated variability from an existing source.

## Step 5: Read The Light Curve

Good transient signs:

- The object appears after previous non-detections.
- The last detection is recent enough that the source may still be follow-up observable.
- The light curve has a rise, decline, or clear flare-like evolution.
- The detections cluster over days to weeks, not years.
- It is not randomly bouncing forever at similar brightness.
- There are enough real detections to trust it.

Bad signs:

- Many detections over hundreds of days.
- First detection is old but the last detection is recent, which can mean long-lived variability.
- The first-to-last detection baseline is very long.
- Similar brightness repeated over long periods.
- Obvious periodic behavior.
- Alternating detections and non-detections around the same magnitude.
- Light curve looks like a variable star, AGN, eclipsing binary, LPV, YSO, or RR Lyrae.

Use this sentence for a good candidate:

> The light curve shows a recent appearance with a compact detection window and no long historical baseline, so it is worth deeper validation.

Use this sentence for a bad candidate:

> The light curve looks like repeated variability rather than a one-time transient, so I should not report it yet.

## Step 6: Check The Last Known Detection

The last known detection is not a rejection by itself. It tells you whether the candidate is still active and whether the object behaves like a short transient or long-lived variability.

Write down:

- Discovery date
- Last detection date
- First-to-last detection baseline
- Detection count
- Non-detection count
- Whether detections continue to the present

Good signs:

- Last detection is recent.
- Discovery-to-last-detection baseline is days to weeks.
- Brightness changes smoothly over the detection window.
- Earlier non-detections exist before the first detection.

Risky signs:

- Last detection is recent but the first detection is hundreds of days or years old.
- The source keeps returning at similar brightness.
- The baseline is too long for a normal one-time transient.
- The object has many detections and looks continuously active.

Use this sentence:

> The last detection shows whether the object is still active, while the first-to-last detection baseline tells me whether it is transient-like or long-lived variability.

## Step 7: Inspect Difference Stamps Date-By-Date

Use the date selector in ALeRCE and move through every available detection date.

For each date, check:

- Is the positive residual at the same sky position?
- Is it compact and point-like?
- Is it separated from subtraction streaks?
- Is it not just a bright-star halo?
- Is it not a cosmic ray or one-frame artifact?
- Does it appear on multiple dates?

Good signs:

- Clean residual at the same position on multiple dates.
- Residual strength changes smoothly over time.
- Science image has a plausible source/host nearby.
- Template does not already show an equally bright variable point source at the same position.

Bad signs:

- Residual changes shape wildly.
- Residual appears only once.
- Residual sits on a subtraction edge, spike, ghost, or saturated star.
- Difference image shows positive-negative dipole artifacts.

Use this sentence:

> I am looking for repeated compact positive residuals at the same position, not one noisy subtraction artifact.

## Step 8: Check ALeRCE Classifier Warnings

Look at both classifier panels.

Good classes for transient reporting:

- `SNIa`
- `SNII`
- `SNIbc`
- `SLSN`
- `TDE`
- `CV/Nova`, only if the image and catalog checks support it
- `AGN`, only if reporting as possible nuclear/AGN-like transient, not as a supernova

Risky classes:

- `VS`
- `Periodic-Other`
- `LPV`
- `RRL`
- `CEP`
- `DSCT`
- `YSO`
- `AGN`, if the object is old or long-lived
- `QSO`
- `bogus`

Use this sentence:

> If ALeRCE strongly favors `VS`, `LPV`, `YSO`, `RRL`, or `Periodic-Other`, I treat the candidate as risky unless the images and catalogs strongly disagree.

## Step 9: Run Verification

For the newest run folder, run verification on the high-priority shortlist:

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/helio_pycache .venv/bin/python astronomy/verify_candidates.py \
  --ranked-csv /Users/aadinair/projects/helio/astronomy/ai_hunter_runs/RUN_FOLDER/high_priority_shortlist.csv \
  --only-new-class \
  --disable-tns \
  --output-dir /Users/aadinair/projects/helio/astronomy/verification/RUN_FOLDER_high_priority
```

Replace `RUN_FOLDER` with the actual run folder name, such as:

```text
run_20260702T135242Z
```

This checks:

- SkyBoT moving-object matches
- ALeRCE class probabilities
- Whether it still needs TNS authentication check

Use this sentence:

> Verification rejects moving objects and known matches before I even consider TNS reporting.

## Step 10: Run Catalog Validation

Run:

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/helio_pycache .venv/bin/python astronomy/catalog_validation_engine.py \
  --candidates-csv /Users/aadinair/projects/helio/astronomy/ai_hunter_runs/RUN_FOLDER/high_priority_shortlist.csv \
  --output-dir /Users/aadinair/projects/helio/astronomy/catalog_validation/RUN_FOLDER_high_priority
```

This checks:

- SIMBAD
- VSX
- Known variable-star matches
- Cataloged stellar or extragalactic counterparts

Use this sentence:

> Catalog validation is the step that prevents us from reporting known variable stars as new transients.

## Step 11: Interpret SIMBAD And VSX

If SIMBAD or VSX says the source is a known or suspected variable, be cautious.

Strong rejection signs:

- `EB`
- `EB?`
- `LPV`
- `RRL`
- `CEP`
- `YSO`
- `Variable Star`
- Gaia DR3 variable source
- VSX named variable

Possible host/AGN signs:

- galaxy
- QSO
- AGN
- X-ray source
- radio source

Use this sentence for a variable match:

> This is probably not a new transient because the position matches a known or suspected variable source.

Use this sentence for a galaxy/nuclear match:

> This may be a nuclear or AGN-like optical transient, but it should not be reported as a supernova without stronger evidence.

## Step 12: Decide Whether To Report

Report only if most of these are true:

- No existing TNS match.
- No SkyBoT moving-object match.
- No VSX variable-star match.
- No SIMBAD variable-star match.
- Difference stamps are clean on multiple dates.
- Light curve has transient-like evolution.
- Candidate is recent.
- Last detection supports a short active window or useful follow-up, not years-long variability.
- Detection baseline is not too long.
- Classifier is not strongly `VS`, `LPV`, `YSO`, `RRL`, or `Periodic-Other`.

Do not report if:

- It matches SIMBAD `EB?`, `LPV`, `YSO`, `RRL`, or a known variable.
- It looks like long-term repeated variability.
- It is already in TNS.
- It is probably a moving object.
- The difference stamps are noisy or single-frame only.
- The source is old and detection-heavy.

Use this sentence:

> TNS acceptance means the report was inserted as an astronomical transient candidate; it does not automatically prove the physical type.

## Step 13: If Reporting To TNS

Use cautious wording.

For a possible supernova-like candidate:

> Candidate detected in ZTF/ALeRCE difference imaging with compact positive residuals on multiple dates. No known TNS or SkyBoT moving-object match found. Submitted as an unclassified optical transient candidate pending follow-up.

For a possible nuclear/AGN-like candidate:

> Candidate detected in ZTF/ALeRCE difference imaging with repeated compact positive residuals. No known TNS or SkyBoT moving-object match found. The source is coincident with or near a cataloged galaxy/nuclear source, so this is submitted as a possible nuclear/AGN-like optical transient candidate, not as a supernova classification.

For a risky candidate with variable-star warning:

> Do not report yet. Candidate has variable-star-like warnings or catalog matches and needs manual review before TNS submission.

## Step 14: What To Say In A Discovery Summary

Use this wording:

> I identified the candidate by running a pipeline over public ZTF/ALeRCE alert data. The pipeline ranked objects by light-curve behavior, freshness, and rejection tests, then I manually checked the light curve, difference images, moving-object matches, TNS status, and catalog crossmatches before deciding whether it was reportable.

If the object is accepted by TNS:

> The object was accepted by the Transient Name Server as an astronomical transient candidate. Its physical nature still requires follow-up or catalog review.

If the object later turns out to be a known variable:

> The TNS report identified a candidate at that position, but later catalog evidence suggests it may be a known or suspected variable source rather than a new explosive transient.

## Final Rule

Use this as the final decision rule:

> If the light curve looks transient-like, the difference stamps are clean, and catalog checks do not identify a known variable, moving object, or existing TNS source, then the candidate is worth considering for TNS. If any of those checks fail, do not report yet.
