# Public cadence input contract, version 1

This is the source-contract checkpoint for issue #11. It authorizes an offline
input adapter and parser tests only. It does not authorize any research outcome
access, experiment, scoring, ranking, catalogue clearance, or discovery claim.

## Bound public input

The first retained input is Lightkurve's existing 100-cadence TESS test fixture:

- Publisher of the FITS product: NASA/Ames, as recorded in `ORIGIN`.
- Mirror and retrieval identity: `lightkurve/lightkurve`, commit
  `dc0dfa20313af527bc74d5fbabbd0d8abe54fb95`.
- Exact upstream file:
  `tests/data/test-lc-tess-pimen-100-cadences.fits`.
- Canonical pinned URL:
  <https://github.com/lightkurve/lightkurve/blob/dc0dfa20313af527bc74d5fbabbd0d8abe54fb95/tests/data/test-lc-tess-pimen-100-cadences.fits>.
- Raw size: 40,320 bytes. SHA-256:
  `7577c14d6eef06d5c09c0f3d9521e8e756eea584bcc91ac407fd3d090e5979a1`.
- Git blob SHA-1: `0381f5bd0628fdf9047547383996463a0423a19b`.
- Header identity: TESS, SPOC data release 42, file version 1.0,
  pipeline `spoc-5.0.10-20200904`, TIC 261136679, sector 1, camera 4, CCD 2.
- This is a hand-selected upstream test subset, not an untouched complete archive
  product, population, observing campaign, or qualification dataset. Its headers
  retain full-product observation bounds; those bounds do not describe the span
  of the 100 retained rows.
- Reuse: the pinned Lightkurve repository supplies this fixture under its MIT
  license. The complete upstream notice is retained alongside the fixture. This
  does not establish terms for a future archive download. No bulk acquisition is
  part of this change.

The local raw fixture and its source receipt are in
`tests/fixtures/public_cadence/`. The receipt is bound to the exact bytes before
parsing. Future files require their own acquisition identity and matching SHA-256;
a receipt does not waive the versioned parser's independent schema checks.

## Native time and row contract

The adapter reads only `TIME`, `CADENCENO`, and `QUALITY` from the `LIGHTCURVE`
binary table. It checks the full ordered column names, FITS formats and units
against this specific SPOC schema. It does not read flux, classification,
catalogue-match, or model-performance values.

The source explicitly records `TIMESYS=TDB`, `TIMEREF=SOLARSYSTEM`,
`TIMEUNIT=d`, `BJDREFI=2457000`, `BJDREFF=0`, and `TIMEPIXR=0.5`.
`TIME` is preserved as native BTJD in days; no UTC conversion, time-scale guess,
interpolation, imputation, quality-mask selection, or change to a research cadence
generator occurs. `TIMEDEL` is retained as header metadata, not used to invent
missing exposures. The adapter rejects absent, contradictory, or changed time
semantics. It never uses the UTC `DATE-OBS` string to reinterpret TDB measurements.

The `LIGHTCURVE` header's `TIMEOFFS` and legacy `TIMEZERO` must each be absent
or occur exactly once with a numeric zero value. Nonzero offsets, booleans,
strings, undefined values and repeated cards fail with `schema_drift` before
row extraction. Opposite offsets are not assumed to cancel. This adapter
performs no offset correction: absent offsets and explicit numeric zeros keep
the same native row/time semantics, and the pinned fixture's report is unchanged.
The same admission applies when a source enters a multi-file cohort, so an
unsupported offset cannot be mistaken for an identical overlapping cadence.

This boundary follows the time-offset meaning in
[FITS 4.0, section 9.4.1](https://fits.gsfc.nasa.gov/standard40/fits_standard40aa-le.pdf)
for `TIMEOFFS` and the NASA FITS User's Guide's
[legacy `TIMEZERO` example](https://fits.gsfc.nasa.gov/users_guide/users_guide/node114.html).
It does not add another time representation or source schema.

Clean rows identify `(TICID, SECTOR, CAMERA, CCD, CADENCENO)` and carry the native
time and unchanged quality bitmask. The source hash plus one-based raw row number
maps a clean or quarantined row back to its input. Identical rows for one cadence
retain the earliest raw row and quarantine later copies. Conflicting observations
with the same identity quarantine the entire identity group, without selecting a
preferred value. Missing/non-finite time and invalid cadence/quality integers have
stable reason codes.

This per-source adapter emits independent source reports. Their counts must not
be summed as distinct observations. The separate offline
[cohort input checkpoint](PUBLIC_CADENCE_COHORT_CONTRACT.md) reparses exact raw
sources, reconciles overlapping identities, and retains its own input-only
contract and review gate. The per-source adapter does not invoke that assembly.

## Output and replay contract

One deterministic JSON envelope contains provenance, the raw-to-clean field
mapping, accepted rows, quarantine records, and input/accepted/rejected counts.
It is published atomically without overwriting an existing path, under the raw
SHA-256. An exact replay reuses identical bytes and reports zero new artifacts.
Changed provenance or an altered existing report fails closed; there is no force
or re-bless flag. The adapter reads only explicitly supplied local paths, has no
network client, and accepts at most 2 MiB and 10,000 rows per input.
Raw files, receipts, and existing artifacts must be regular files; symlinks and
special files fail closed. Receipt JSON rejects repeated keys and is limited to
64 KiB, so conflicting acquisition identities cannot be silently discarded.

Source receipts describe an upstream public fixture, a local input, or an explicit
synthetic parser fixture. Every report remains `input_only=true` and
`scientific_execution_authorized=false`, irrespective of receipt type.

## Reproduce

From a clean checkout with Python 3.11 or newer:

```sh
python -m pip install -e '.[dev]' 'astropy>=6'
python -m siderea.public_cadence tests/fixtures/public_cadence/tess-pimen-100.fits --source tests/fixtures/public_cadence/source.json --output-dir /tmp/siderea-public-cadence
python -m pytest -q tests/test_public_cadence.py tests/test_public_cadence_cohort.py tests/test_public_cadence_time_offsets.py
```

Repeating the adapter command must report `reused` and `new_artifacts=0`. The
dedicated public-cadence workflow runs these commands from a clean checkout.
The normal repository quality and test workflows also continue to apply. Before
merge, retain the exact-head clean-run receipt and an input-only review.

No robust-search-v2 development, calibration, locked evaluation, generalization,
or compound-probe outcomes are inputs to these commands. All existing research
freezes, negative evidence, trial allocations, seeds, promotion rules, and holds
remain in force. This scaffold alone does not complete issue #11's broader
multi-source readiness work.
