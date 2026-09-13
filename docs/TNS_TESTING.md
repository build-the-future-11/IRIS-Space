# Controlled TNS search testing

This procedure tests registry cross-matching, not transient-detection sensitivity.
The client reads TNS search results; it cannot submit reports or download object
photometry. TNS object/photometry ingestion is a separate future integration.

## Before making requests

Install the current checkout in your project environment (`python -m pip install -e .`)
and confirm `siderea tns-qualify --help` is available. An older installed wheel will
not include the new command.

Choose cases independently from the TNS website and record the date, coordinates
(ICRS degrees), internal discovery name, and expected TNS name. A TNS object name
is not necessarily its internal discovery name. Use the exact returned display
name, including a prefix such as `SN`, for `--expected-name`.

Use a dedicated local query JSON with exactly these fields:
`internal_name` (nonblank string), `ra` (0 inclusive to 360 exclusive), `dec`
(-90 to 90), `radius_arcsec` (positive). Do not choose random coordinates and
assume the result must be clear. Check the chosen cone independently first.

Set `TNS_API_KEY`, `TNS_BOT_ID`, and `TNS_BOT_NAME` in the process environment using
your approved TNS bot credentials. Never put the key in query files, reports,
commits, or command arguments. The CLI checks all three before any network call.

## Execute one case at a time

```sh
siderea tns-qualify known-query.json known-report.json --expected-status match --expected-name 'SN 2021rf'
siderea tns-qualify clear-query.json clear-report.json --expected-status clear
```

The object name above demonstrates command syntax; prepare the actual query and
expected name from independent TNS inspection. These are not prequalified cases.
Each command uses the production HTTPS search endpoint, a 30-second timeout and
one attempt per stage (at most two requests). A name match ends the search; only
an empty name result proceeds to the cone. A clear result requires both stages.

Exit 0 means the expected status and requested names were observed; exit 3 means
mismatch or upstream failure. Exit 2 means invalid input/configuration or an output
error. Reports are created without overwriting prior files and include the query,
endpoint, time, response digest, parser-code digest and expected/observed outcomes.
Upstream error text is redacted. A report is a local evidence record, not a signed
attestation, candidate clearance, or a scientific performance estimate.

## Acceptance cases

1. Known internal name: expect a match with the independently checked TNS name.
2. Position match: use an independently checked unused internal name at a known
   object's coordinates; expect a cone match with the correct TNS name.
3. Empty name and independently checked empty cone: expect clear, with ordered
   `internal_name` and `cone` methods in the evidence.
4. Review every report against the website and preserve it with the case-selection
   notes. Investigate every mismatch; do not change expectations just to pass.

Exercise timeout, malformed responses, 429, 503 and authentication failures in
transport simulations/offline fixtures. Do not deliberately overload TNS or send
bad credentials to test rate limits. Existing `fixture-qualify-tns` supports exact
sanitized response replay (see LOCAL_OPERATIONS.md).

Live search qualification does not qualify real-sky noise assumptions. A detection
benchmark additionally needs a frozen independently labelled source cohort,
matched survey photometry and units/uncertainties, leakage-safe splits, null cases,
and measured false-alarm and sensitivity results. None is supplied by a successful
TNS search alone.
