# AAS249 SIDEREA software presentation

This package prepares a software-focused late iPoster proposal. It contains an
abstract below the 2,250-character limit, a poster PDF and an exhaustive arithmetic
illustration executed against the repository's actual ranking function. It is
unsubmitted and the containing GitHub pull request remains unmerged.

## Materials

- [Abstract](abstract.txt).
- [Offline poster asset](SIDEREA_AAS249_Poster.pdf).
- [All 192 executed evaluations and exact rational summaries](../../docs/evidence/aas249-tie-demonstration-2026-10-07.json).
- [Reproduction script](../../scripts/aas249_tie_demonstration.py).
- [Existing local software walkthrough](../../docs/FIRST_RUN.md).

The poster is a prepared asset for constructing the meeting's native iPoster
after acceptance. It has not been uploaded to iPosterSessions or accepted by AAS.
The existing manuscript credits Aadi Ajeesh Nair and Ryan Gomez; that attribution
is retained without inventing institutions or a presenting-author assignment.

## What was executed

All 24 permutations of the retained four-row constructed fixture were evaluated
for two score columns and four budgets. The 192 evaluations have identical
tie-aware point metrics within each model/budget condition. Expected precision
and recall agree with independent exact rational averages of the corresponding
row-order selections. This is a fully enumerated arithmetic example, not a new
astronomical cohort or an empirical improvement claim.

Threshold-grouped average precision is a separate declared metric. It is not
the average of arbitrary rank-by-rank AP values over tie permutations. The
example's two score columns are labels in a constructed fixture, not trained
systems whose quality has been compared on sky data.

```bash
PYTHONPATH=src python scripts/aas249_tie_demonstration.py /tmp/aas249-ties-new.json
python submission/aas249/build_poster.py
```

## Current AAS route

The [AAS249 abstract page](https://aas.org/meetings/aas249/abstracts), checked on
7 October 2026, gives the late window as 13-26 October 2026. The meeting is
10-14 January 2027 in Salt Lake City. The page does not provide a cutoff clock;
no timezone conversion is invented here.

The [AAS meeting rules](https://aas.org/meetings/aas-meeting-sessions-content)
limit abstracts to 2,250 characters and restrict late abstracts to iPosters.
The first/presenting author must submit. Membership, Full Member sponsorship
where applicable, registration and presenter availability remain to be settled.
Native iPoster creation uses the meeting-specific link after abstract approval.

## Claim and completion boundaries

No model was trained, no protected held-out campaign was run and no external
catalogue request or discovery report was made. This package claims executed
software/arithmetic behaviour. It does not claim real-sky precision, purity,
recall, discovery yield or institutional validation. Historical object-accounting
and manuscript reconciliation gaps documented elsewhere remain open.

Author review of contribution and fit, a confirmed presenting author and eligible
sponsor/membership route, reviewed GitHub integration, a submission instruction
and an actual portal receipt are still required. Preparing a poster is not whole-
project completion, conference acceptance or registration.
