# Public cadence cohort contract, version 1

This is the bounded cross-file input checkpoint for issue #11, built on the
TESS SPOC source adapter in PR #37. It assembles native cadence identities from
explicitly supplied local FITS files and acquisition receipts. It does not select
astronomical candidates, measure detector performance, read protected research
outcomes, or authorize a scientific run.

The only supported source schema and public fixture remain those in
[the source contract](PUBLIC_CADENCE_SOURCE_CONTRACT.md). There is no new source
family, external acquisition, flux extraction, time conversion, or quality filter.
The official 100-row Lightkurve fixture remains a selected parser test subset;
neither its rows nor derived artificial fixtures represent a population study.

## Exact source and cohort identity

Every input is a `(raw FITS path, source receipt path)` pair. The implementation
reparses exact raw bytes through the existing versioned source adapter. Previously
generated report JSON is not accepted as an alternate input. Its source report
digest is recomputed and recorded alongside the full acquisition receipt, native
time metadata, and original per-source input/accepted/rejected counts.

Raw SHA-256 identifies a source artifact. Repeating that artifact with the exact
same receipt contributes one source and one set of rows. Repeating its bytes with
a different acquisition identity, including a changed retrieval timestamp,
fails with `source_provenance_conflict`; the assembler does not choose or repair
provenance. Every supplied pair is hash-checked before duplicate elimination.

The content-addressed cohort key is SHA-256 of the canonical JSON object:

```json
{
  "adapter_version": "tess-spoc-cadence/1",
  "cohort_schema_version": "siderea-public-cadence-cohort/1",
  "raw_sha256": ["sorted distinct raw SHA-256 identities"],
  "source_report_schema_version": "siderea-public-cadence/1"
}
```

Canonical JSON uses sorted keys, two-space indentation, UTF-8, finite JSON
numbers, and a final newline, matching the existing source-report encoding.
Literal adapter and schema versions are part of the key. Input request order,
local filenames, and repeat requests are not. The acquisition receipts remain
part of the artifact content: a later provenance change under the same source
set reaches the same key and fails the exact-byte replay check.

## Cross-file row identity and overlap policy

Identity remains `(TICID, SECTOR, CAMERA, CCD, CADENCENO)`, rendered as the
existing `tess:TICID:SECTOR:CAMERA:CCD:CADENCENO` row ID. Native `TIME` stays
BTJD/TDB in days. The adapter's TDB, Solar System reference, BJD reference,
time-position semantics and unchanged quality bitmask remain binding.

The deterministic policy is:

1. Preserve malformed source rows in quarantine with their original reason.
   Missing times and identities are never reconstructed or imputed.
2. Carry each valid row identity and its `(raw SHA-256, one-based source row)`
   reference into the cohort. Include identical within-source duplicates in
   this accounting, without treating them as new identities.
3. If an identity was already quarantined as conflicting within any source,
   quarantine **all** its cohort references. A valid value in another file
   cannot revive that conflicted identity.
4. Otherwise require exact agreement of native time, quality bitmask and
   header `TIMEDEL` for all references to an identity. Any disagreement
   quarantines every reference as `conflicting_cadence`. There is no tolerance,
   preferred source, interpolation, average, or winner selection.
5. For identical values, retain one representative chosen by the smallest
   `(raw SHA-256, source row)` pair. Keep every reference in its `provenance`
   array; classify the remaining source rows as `duplicate_cadence` in the
   overlap audit. This representative rule is independent of request order.

Each source retains its own `TIMEDEL`. Distinct cadence identities with different
interval metadata may coexist; the cohort invents no common exposure interval
or globally uniform time grid. Rows are sorted by stable row ID, which is not a
claim of global chronological ordering.

## Counts and conservation

Counts are named for what they measure:

| Field | Meaning |
| --- | --- |
| `distinct_raw_sources` | Distinct raw byte identities after exact-source deduplication |
| `input_rows_across_distinct_sources` | Sum of raw rows in those distinct sources; overlaps remain included here |
| `accepted_unique_cadence_identities` | Number of nonconflicting retained row identities |
| `quarantined_source_rows` | Malformed, conflicting and duplicate source-row references excluded as representatives |
| `duplicate_source_rows` | Identical extra source-row references, not additional accepted cadence identities |
| `overlapping_cadence_identities` | Valid identities that occur more than once, within or across distinct source artifacts |
| `conflicting_cadence_identities` | Identities for which all references were quarantined |

Every source row appears exactly once as an accepted representative or in the
quarantine audit. Thus `input_rows_across_distinct_sources` equals
`accepted_unique_cadence_identities + quarantined_source_rows`. Provenance arrays
also retain duplicate references, so their lengths must not be added to accepted
counts. Original source-report counts are recorded under `counts_before_assembly`
and remain separate from cohort identity counts.

For example, the 100-row public fixture plus a derived six-row identical overlap
has 106 source rows and 100 accepted cadence identities. Repeating the exact
100-row source itself contributes only 100 source rows. These are input-accounting
checks, not discovered objects, independent observations or scientific results.

## Publication, replay and limits

The sole output is `<cohort SHA-256>.cohort.json`, published with the repository's
atomic create-without-replacement primitive. A repeated request or reordered
source set reuses byte-identical content and returns `new_artifacts=0`. An altered
artifact, changed provenance or incompatible existing path fails closed. There
is no force, overwrite or re-bless option.

All raw inputs, receipts and existing replay artifacts must be regular files.
The shared bounded reader rejects final symlinks and special files without
blocking on FIFOs. Ancestor directories remain caller-trusted; this interface
is not a filesystem sandbox. Validation finishes before any output is published.

Limits are 1–16 supplied source pairs, 16 MiB of supplied raw bytes including
repeated requests, 2 MiB and 10,000 rows per individual source, 40,000 total rows
across distinct sources, and a 32 MiB encoded cohort report. Invalid or excessive
inputs do not create a cohort artifact. No path is fetched over the network.

Every stored cohort and successful CLI response carries `input_only=true` and
`scientific_execution_authorized=false`. Successful assembly does not release
any protected study, candidate-promotion gate, experiment or frozen protocol.

## Reproduce the input checkpoint

```sh
python -m pip install -e '.[dev]' 'astropy>=6'
python -m pytest -q tests/test_public_cadence.py tests/test_public_cadence_cohort.py
python -m siderea.public_cadence_cohort --input tests/fixtures/public_cadence/tess-pimen-100.fits tests/fixtures/public_cadence/source.json --input tests/fixtures/public_cadence/tess-pimen-100.fits tests/fixtures/public_cadence/source.json --output-dir /tmp/siderea-public-cohort
python -m siderea.public_cadence_cohort --input tests/fixtures/public_cadence/tess-pimen-100.fits tests/fixtures/public_cadence/source.json --output-dir /tmp/siderea-public-cohort
```

The first cohort command reports one distinct source, 100 input rows, 100
accepted cadence identities and one repeated supplied pair. The second reports
reuse with zero new artifacts. Dedicated CI runs both parser modules and these
commands. Tests use only the pinned public fixture and explicitly labelled
artificial parser mutations for overlaps, conflicts, malformed rows and drift.

## Remaining gates

This completes the bounded same-schema input assembly component. It does not
complete broader archive intake, another product release or schema, acquisition
licensing, a real observing-cohort selection contract, catalogue interpretation,
or any detector/model qualification. Those remain separate source-specific
decisions. Exact-source CI and independent input-only review still precede merge.
