# TNS testing execution checklist

Scope: controlled read-only registry testing. No report submission or claim of
scientific discovery readiness. Operating instructions: docs/TNS_TESTING.md.

- [x] Inspect the current search client, two-stage clearance contract and offline fixture runner.
- [x] Check runtime credential presence without displaying values: all three TNS variables absent.
- [x] Add `tns-qualify` to isolate TNS testing from other catalogue dependencies.
- [x] Require complete environment credentials before requests; use one attempt per stage and a bounded timeout.
- [x] Require independently selected expected names for a match; a service failure cannot qualify as success.
- [x] Save an immutable report with query, expected/observed results, timestamp and code/response digests; redact upstream error text.
- [x] Test name match, clear two-stage search, wrong identity, malformed cone response, failed transport, invalid expectations, missing credentials and immutable output.
- [x] Document exact case preparation, commands, return codes and scope limitations.
- [x] Run full repository checks after implementation and record results below.
- [ ] Live known-name match — blocked: TNS_API_KEY, TNS_BOT_ID and TNS_BOT_NAME absent; supply credentials in the execution environment and independently inspected case data.
- [ ] Live known-position match after empty internal-name result — same credential blocker; select a verified TNS object position and unused internal name.
- [ ] Live empty-name/empty-cone test — same credential blocker; independently verify the chosen field before execution.
- [ ] Compare live reports against TNS and retain case-selection notes — depends on the three live cases.

## Separate science work (not established by these search checks)

- [ ] Assemble a frozen labelled real-sky benchmark with compatible survey photometry and null sources; no such qualified cohort is supplied for this test.
- [ ] Evaluate sensitivity and false alarms under real noise; preserve previously observed noise-misspecification failures.
- [ ] If direct TNS photometry is required, implement and qualify the separate object endpoint and unit/error conversion before detector ingestion. Current scope uses registry search only.

## Validation evidence

- Targeted qualification suite: **18 tests passed**, including simulated transport tests.
- `make check PYTHON=.test-tmp/release-env/bin/python`: **PASS**, 416 tests,
  96 subtests, 78.43% coverage; Ruff lint/format (108 files), mypy (74 source files),
  and compilation passed. Log: `.test-tmp/tns-check.log`.
- Initial sandbox run: 414 passed, two HTTP tests failed solely at socket binding;
  complete rerun with localhost permission passed without code/test suppression.
- Isolated sdist/wheel build: **PASS**, artifacts in `.test-tmp/tns-testing-dist`.
  First nonisolated attempt lacked wheel; sandboxed isolated attempt could not
  resolve PyPI; retry with network access installed declared dependencies and passed.
- Source and built-wheel `tns-qualify --help`: **PASS**. The pre-existing installed
  older wheel lacks this new command; reinstall the current checkout before use.
- `pip check` and `git diff --check`: **PASS**.
- Existing unrelated `.coverage` modification preserved; validation uses a separate
  `.test-tmp/tns-qualification.coverage` file.

These tests are not live-origin evidence. No live TNS requests made because
credentials are absent. No detector-performance or paper-result claims changed.
