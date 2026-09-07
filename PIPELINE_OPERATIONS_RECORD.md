# I SPY — Pipeline Operations Record

**Program:** I SPY optical transient search — TNS reporting group `204`
**Prepared by:** Aadi Ajeesh Nair
**Record compiled:** 2026-08-09
**Campaign period:** 2026-04-07 → 2026-07-30
**Source data:** Public ZTF alert stream, brokered via ALeRCE
**Governing documents:** [`ISPY_SUBMISSION_PROTOCOL.md`](ISPY_SUBMISSION_PROTOCOL.md) · [`TRANSIENT_DETECTION_PLAYBOOK.md`](TRANSIENT_DETECTION_PLAYBOOK.md)

---

## 1. Purpose

The operating record of the search: how many objects were screened, how many survived
each filter, why the rest were rejected, and what was submitted. Every figure traces to a
`summary.json` in this tree.

It serves as evidence of process for telescope-time and partnership applications, as an
onboarding reference for new contributors, and as the group's audit trail.

---

## 2. Method

The pipeline queries ALeRCE for ZTF objects with transient-like classifier probabilities,
pulls full light curves, and scores each on freshness, detection count, and detection
baseline. Long-lived variability is vetoed early. Survivors reach a manual shortlist, then
two automated rejection stages — SkyBoT moving-object and TNS known-object checks, then
SIMBAD/VSX known-variable crossmatching. Anything still standing is inspected by eye:
light curve, difference stamps date-by-date, classifier warnings. Only then is a report
packet generated, reviewed, and submitted. Note that both submissions to date predate
the creation of group 204 on 2026-07-09 and carry TNS Reporting Group *None*; see §5.

Successive runs use an exclusion ledger, so objects are not re-screened.

---

## 3. Campaign statistics

31 run folders exist; 24 were productive. Seven returned zero objects due to DNS
resolution failures against `api.alerce.online` and are excluded from all figures below.

| Run | Objects | Detection rows | Clean rows | Sources | Ranked | Early veto | Shortlist |
|---|---|---|---|---|---|---|---|
| run_20260605T095611Z | 40 | 2,473 | 1,485 | 28 | 12 | — | — |
| run_20260605T100242Z | 40 | 2,348 | 1,259 | 26 | 11 | — | 7 |
| run_20260613T190623Z | 80 | 7,915 | 4,772 | 49 | 30 | — | 2 |
| run_20260613T190934Z | 20 | 556 | 273 | 10 | 3 | — | 2 |
| run_20260613T193116Z | 120 | 12,605 | 6,828 | 82 | 49 | — | 5 |
| run_20260613T193417Z | 30 | 2,049 | 1,548 | 24 | 15 | — | 2 |
| run_20260613T193647Z | 30 | 2,110 | 1,609 | 24 | 16 | — | 2 |
| run_20260614T012050Z | 50 | 2,424 | 1,807 | 32 | 19 | 27 | 2 |
| run_20260614T013847Z | 150 | 14,387 | 7,750 | 97 | 58 | 87 | 5 |
| run_20260614T014019Z † | 150 | 14,387 | 7,750 | 97 | 58 | 87 | 5 |
| run_20260614T020207Z | 225 | 40,790 | 22,427 | 199 | 125 | 191 | 5 |
| run_20260614T022514Z | 350 | 64,679 | 30,835 | 310 | 213 | 302 | 1 |
| run_20260614T051705Z | 350 | 30,825 | 20,354 | 195 | 128 | 186 | 1 |
| run_20260614T090412Z | 350 | 50,599 | 27,843 | 309 | 168 | 302 | 3 |
| run_20260702T052210Z | 1,000 | 20,761 | 6,423 | 109 | 57 | 109 | 0 |
| run_20260702T135242Z | 350 | 9,305 | 3,007 | 77 | 34 | 73 | 1 |
| run_20260704T085705Z | 350 | 59,695 | 27,348 | 323 | 185 | 316 | 0 |
| run_20260705T050105Z | 350 | 79,319 | 44,467 | 330 | 233 | 329 | 0 |
| run_20260705T161401Z | 350 | 6,012 | 3,391 | 260 | 85 | 24 | 72 |
| run_20260706T051558Z | 350 | 5,611 | 4,033 | 323 | 35 | 3 | 35 |
| run_20260707T130026Z | 253 | 3,093 | 2,271 | 217 | 28 | 1 | 25 |
| run_20260709T062409Z | 110 | 1,256 | 717 | 77 | 12 | 3 | 10 |
| run_20260721T160207Z | 311 | 3,601 | 2,307 | 236 | 53 | 8 | 47 |
| run_20260730T021531Z | 157 | 1,810 | 1,184 | 117 | 25 | 2 | 24 |

† Reports figures identical to `run_20260614T013847Z` — a re-processing of the same
150-object pull, not an independent screening.

Note the regime change from 2026-07-05: early-veto counts collapse (329 → 24 → 3) while
shortlist sizes jump (0 → 72 → 35). The search was retuned toward a larger, less
aggressively pre-filtered shortlist, moving the rejection burden downstream to catalog
validation. §4 reflects both regimes.

### Headline figures

| Quantity | Value | Basis |
|---|---|---|
| Productive runs | 24 | of 31 folders |
| **Distinct objects screened** | **3,824** | cached light-curve files — the defensible unique count |
| Exclusion ledger at final run | 6,270 | broker-returned OIDs marked seen; exceeds fetched count |
| Detection rows processed | ~438,600 | sum across productive runs |
| Rows surviving quality cuts | ~231,700 | sum across productive runs |
| Candidates ranked | ~1,652 | sum across productive runs |
| Early-veto rejections | ~2,050 | where early-veto was enabled |
| Reached manual shortlist | 256 high-priority / 239 fresh | sum across productive runs |
| Report packets generated | 3 individual + 1 bulk draft | see §5 |
| **Submitted and designated** | **2 — AT 2026pcz, AT 2026rsp** | TNS report 308376; objid 212592 |

Sums marked "~" double-count objects re-screened across reruns. Quote **3,824** for
unique objects examined.

---

## 4. The rejection funnel

The pipeline is built to reject. Counts below are deduplicated across reruns of the same
candidate set.

```
  3,824  distinct objects, light curves retrieved
     │
     ▼  automated scoring + early veto
     │   (long baselines, high detection counts, old first-detections, periodicity)
    ~256 reached manual high-priority shortlist
     │
     ▼  verification — SkyBoT + TNS   (200 candidate-checks)
     │   30  rejected: already a known TNS object
     │    0  rejected: moving Solar System object
     │    3  unresolved: TNS query errored twice (run_20260721T160207Z)
     │
     ▼  catalog validation — SIMBAD + VSX   (193 candidate-checks)
     │   55  rejected: known or suspected variable star   (28% of those checked)
     │   30  flagged: needs manual review
     │    7  flagged: possible host galaxy / extragalactic counterpart
     │  101  passed catalog checks
     │
     ▼  manual inspection — light curve, difference stamps, classifier, wording gate
     │
      3  report packets  →  2 submitted  →  AT 2026pcz, AT 2026rsp
```

**The figure to cite: 28% of candidates reaching catalog validation were rejected as
known or suspected variable stars.** Those 55 records quantify a stage-specific veto
among objects that reached catalog validation. The available operations record does not
establish that every one would otherwise have been submitted to TNS.

A further 30 were rejected as objects already on TNS — real transients, but not I SPY's
to claim.

Moving-object rejections were zero throughout. Upstream broker classes and freshness
criteria may have reduced Solar System contamination before SkyBoT, but this record does
not identify the cause of the zero count or establish a zero contamination rate. SkyBoT
is retained as a mandatory safety check.

**End-to-end selectivity: 2 submissions from 3,824 screened objects — 0.052%.**

---

## 5. Candidates reaching report stage

### 5.1 ZTF26abdqbqw → AT 2026rsp — SUBMITTED

| Field | Value |
|---|---|
| TNS designation | **AT 2026rsp** (objid 212592) |
| TNS page | https://www.wis-tns.org/object/2026rsp |
| Position (J2000) | 22:22:35.931 +04:44:17.77 |
| First detection | 2026-06-19 10:11:12 UTC |
| Last detection | 2026-07-03 10:35:13 UTC |
| Detections | 23, in g/r/i over 14 nights, no negative subtractions |
| Pre-detection non-detections | 36, best limit 20.551 mag |
| Peak | r ~ 19.8 around 2026-07-01/04; rose ~1.3 mag in 10 days |
| Host | WISEA J222235.91+044418.8 |
| Classifier | ALeRCE LC classifiers favour Type Ia |
| Submitted | 2026-07-05 — TNS Reporting Group **None** (group 204 was not created until 2026-07-09, four days later) |
| AstroNote | 2026-210, published 2026-07-08 |

The complete case: discovery, submission, designation, and a published AstroNote
requesting spectroscopic classification while near peak. This is the template every
future candidate should follow.

### 5.2 ZTF26aascgfc — packet prepared, not submitted

| Field | Value |
|---|---|
| Position (J2000) | 16:48:49.398 +09:37:25.47 |
| Detection window | 2026-04-07 → 2026-04-10 (3.0 days) |
| Detections | 7 |
| Pre-detection non-detections | 61, best limit 20.734 mag |
| Brightest | 19.947 mag (g), 2026-04-09 |
| Checks | No SkyBoT match; no TNS match; passed catalog validation |
| Quality | Strong `rb`/`drb`; stamp classifier top class SN |
| Decision | `likely_new_candidate` |

A 3-day window against 61 prior non-detections to 20.7 mag — a textbook transient
signature that was never submitted. Worth a retrospective check of whether it was
independently reported by another group.

### 5.3 ZTF26abayrka — correctly held back

| Field | Value |
|---|---|
| Position (J2000) | 15:38:55.353 +10:27:15.72 |
| Detection window | 2026-06-04 → 2026-06-14 (9.9 days) |
| Detections | 13 |
| Pre-detection non-detections | 50, best limit 20.851 mag |
| Counterpart | NED galaxy WISEA J153855.35+102716.1 at ~0.4″ |
| Also | Gaia DR3 + Pan-STARRS faint source at ~0.4″; no VSX match |
| Classifier | AGN probability ~0.815 |
| Decision | Nuclear/AGN-like wording required — not a supernova |

The best training case in the record: the protocol caught a classification trap that a
careless report would have walked straight into.

### 5.4 Bulk draft, 2026-07-10 — not submitted

Two candidates prepared under group 204: `ZTF26abbkkey` (`PSN`, 40 detections) and
`ZTF26abboood` (`NUC`, 20 detections). Both `likely_new_candidate`, neither matched on
TNS at draft time. Status unresolved — if they are to be submitted, TNS must be
re-checked first, as month-old registry state is not reliable.

---

## 6. Known gaps

1. **Three candidates remain unadjudicated.** `run_20260721T160207Z` errored on all three
   TNS queries across two attempts. Their status is unknown, not clear.
2. **The 2026-07-10 bulk draft is stale.** Two prepared candidates, no decision recorded.
3. **No submission log exists.** §9 of the protocol now requires one; it has not been
   backfilled for the four packets above.
4. **Single-operator.** Every judgement here was made by one person. No second-reviewer
   signoff is recorded for any packet. The protocol's Reviewer role is currently unfilled.
5. **Seven runs failed on DNS with no retry or alerting.** A failed run is discoverable
   only by reading `summary.json` afterwards.
6. **The July retune is undocumented.** Early-veto behaviour changed sharply on
   2026-07-05 with no recorded rationale, which makes pre- and post-retune runs hard to
   compare.
7. **A stale duplicate tree exists** at `~/Documents/discovering astronomical gaps/astronomy/`
   (last run 2026-07-04). It should be removed or clearly marked to prevent operating
   from the wrong copy.

---

## 7. Defensible claims

For applications and outreach:

- I SPY is a registered TNS reporting group (ID 204) operating a documented, versioned
  vetting protocol.
- 3,824 distinct ZTF objects screened across 24 productive runs, 2026-04 to 2026-07.
- 28% of candidates reaching catalog validation were rejected as known variables;
  a further 30 were rejected as already-known TNS objects.
- 1 confirmed discovery: **AT 2026rsp**, submitted 2026-07-05, with published
  **AstroNote 2026-210** requesting spectroscopic classification.
- One candidate was correctly downgraded from supernova to nuclear/AGN-like wording on a
  0.4″ host coincidence.
- End-to-end selectivity of 0.026% — the group reports roughly one object in four
  thousand screened.

What this record does **not** support: any claim of a spectroscopic classification.
AT 2026rsp is a designated transient candidate awaiting classification.
