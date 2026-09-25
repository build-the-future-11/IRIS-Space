# IRIS 2026–27 — 90-Second Video Script Draft

**Status:** evidence-bound draft.  
**Intro line requires the final IRIS entrant(s) and grade(s).**  
**Do not state school name, city, or state unless the current 2026–27 portal explicitly requires it.**

## Script

Hi, I’m **[student researcher name]**, in Grade **[grade]**.

Astronomy surveys can generate huge numbers of alerts, but a computer ranking an alert highly does not prove that the object is new, real, or ready to report. My project asks a different question: how can we make transient-search software fail safely when evidence is incomplete?

I built and audited SIDEREA, a human-supervised workflow that separates ranking from reportability. Every candidate version is tied to the evidence checked for it. If a required registry or catalog query fails, is stale, or is malformed, the system records that evidence as unknown and blocks report preparation instead of treating the missing result as a clear.

The design came from auditing a historical campaign containing 24 productive runs and 3,824 distinct broker objects. The audit found existing registered transients and known or suspected variables at downstream stages, and it also exposed configuration changes and missing historical evidence that prevent us from claiming completeness or classifier accuracy.

I then tested the current software invariants through deterministic replay and controlled synthetic experiments. Importantly, the synthetic search also showed severe false alarms when the noise model was wrong.

So the result is not “AI discovers every transient.” The result is a reproducible framework for keeping ranking, evidence, human review, and scientific claims separate—and a clear protocol for what must be validated next on prospective sky data.

## Visual sequence

- 0–10 s: one-sentence problem + alert-stream graphic.
- 10–32 s: SIDEREA evidence flow: rank → external checks → human review → reportability.
- 32–52 s: historical audit counts, clearly labeled as stage-specific.
- 52–70 s: deterministic/software verification + synthetic recovery and adverse false-alarm result.
- 70–90 s: supported conclusion + explicit limitation/future cohort.

## On-screen claim guardrails

Do not show:
- “accuracy,” “precision,” “recall,” “purity,” or “completeness” for real-sky performance;
- “AI discovery rate”;
- venue/competition acceptance not yet received;
- any locked held-out result.

If a figure is shown, its final video caption must include the exact source artifact listed in the claim ledger.
