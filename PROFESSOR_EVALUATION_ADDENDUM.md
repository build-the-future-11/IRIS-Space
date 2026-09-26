# Professor-guided astronomy evaluation addendum

This addendum turns two external methodological recommendations into executable, falsifiable evaluation code without changing the frozen model after outcomes.

## Primary shift: source population

Following Steven Dillmann's recommendation, the primary representation stress test is a **change in source population**.

The evaluator in `siderea.shift_evaluation.population_transfer_report` requires population membership and the in-population/held-population assignment to be supplied explicitly. It refuses:
- overlapping in/held declarations;
- observed populations without a declared role;
- declared populations absent from the evaluation set.

This is deliberate: the evaluator must not inspect model results and then choose whichever population looks hardest.

Report the same frozen model's per-population AUROC and average precision, plus macro in-population vs held-population deltas. If scores are truly held-out calibrated probabilities, calibration can be explicitly enabled; it is not assumed from arbitrary ranking scores.

## Operational endpoint: time to detection

Following Umaa Rebbapragada's recommendation, transient evaluation should include **time to first qualifying detection relative to annotated onset** in addition to ranking / ROC / precision-recall metrics.

`time_to_detection_report` reports:
- annotated count;
- detected and undetected counts;
- detection rate;
- signed median / P90 delay;
- post-onset median / P90 delay;
- pre-onset alert count;
- the same diagnostics per source population.

Undetected events are **not** assigned a made-up large delay. Timing summaries are conditional on detection, and detection rate is always reported beside them. Negative delays are retained and flagged rather than silently clamped because they can reveal an annotation/alarm-semantics issue.

## Claim boundary

A degradation on the held source population is evidence about transfer under the predeclared shift. It is not proof that the population is intrinsically harder, and it does not by itself establish a causal or astrophysical explanation.

A method with a short delay only among detected objects must not be called "earlier" overall if its detection rate is materially worse.
