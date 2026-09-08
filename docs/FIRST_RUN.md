# First local run

Start in the repository root with Python 3.11 or newer. This walkthrough is offline
and uses synthetic examples. It needs no broker credentials and sends no reports.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m siderea doctor
```

Missing optional astronomy/ML dependencies are expected in a core-only install.
If the configured storage directory is unwritable, choose a writable `storage.root`
in a TOML configuration and pass `--config path/to/config.toml`. Do not use strict
doctor mode until installing the optional dependencies you actually intend to use.

## Analyze and review

```bash
siderea analyze examples/photometry.csv --output-dir runs/first-analysis --ledger runs/first-ledger.sqlite
siderea review-serve --ledger runs/first-ledger.sqlite
```

Open the local address printed by the review server. Inspect the queue, light curves,
complete evidence download and outcome dashboard. Stop the server with Ctrl-C.
The example produces two candidates with missing external evidence; zero reportable
candidates is the expected result. Local typed reviewer names are audit labels,
not authenticated identities. See `LOCAL_OPERATIONS.md` before requiring signed reviews.

## Try the separate shadow detector

```bash
siderea transient-search examples/transient_flux.csv runs/first-shadow-search.json --null-trials 999 --seed 20260908
```

The fixture contains a simulated Gaussian pulse and a constant source, both with
independent unit Gaussian measurement noise. It uses seed 20260908, 32 daily epochs,
a baseline of 10, and a pulse of amplitude 5, width 3 days, centered on epoch 16.
The units are arbitrary. This is an execution example, not an astronomical dataset.

Read each object's `status`, `evaluated_channels`, `object_pvalue` and
`threshold_resolvable` before interpreting `shadow_excess`. A false flag means
the requested rule was not satisfied; it does not prove the source is constant.
An unevaluated source has no p-value. More channels require more null simulations
to resolve the same corrected threshold. For example, two channels and 99 null
trials cannot resolve a 1% object-level threshold: the minimum is 2%.

Each output filename must be new. Rerunning a command against an existing output
is rejected to preserve provenance; choose another name. The shadow detector does
not update the review ledger or satisfy reporting gates. Its p-value is neither a
discovery probability nor a physical classification.

## Before real data

Verify units, time convention, survey/passband labels, uncertainties and duplicate
handling. The shadow search accepts measured signed flux, not censored limits or
automatically converted magnitudes. Validate the noise model on independent
background data. Inspect images and catalogue evidence before acting on candidates.
Use a frozen comparison cohort to measure real recovery and false alarms.
