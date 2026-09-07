# Research synthesis: positioning the I SPY manuscript

**Audience:** time-domain astronomy and astronomical-software researchers  
**Date:** 2026-09-06  
**Scope:** primary arXiv and publisher literature relevant to ZTF alert generation,
alert brokers, classification, catalog association, human vetting, and empirical pipeline
validation. The local source code and `PIPELINE_OPERATIONS_RECORD.md` remain authoritative
for claims about I SPY.

## Direct answer

The strongest defensible paper is not a claim that I SPY improves transient classification.
The present campaign has no closed labeled cohort, no injection/recovery experiment, and no
spectroscopic truth set from which to estimate completeness, purity, calibration, or false-negative
rate. Its publishable contribution is instead a rejection-first, human-in-the-loop decision layer
above an existing broker: it preserves explicit unresolved states, separates novelty checks from
phenomenological ranking, uses independent catalog vetoes, and constrains the wording of claims.

This positioning is consistent with the literature. ZTF distributes difference-image detections
of transients, variables, and moving objects at a scale that requires automated filtering. ALeRCE,
ANTARES, Fink, Lasair, and AMPEL all emphasize enrichment, classification, filtering, and
redistribution; AMPEL additionally emphasizes provenance and changing information states. I SPY
is smaller and offline/batch-oriented, but its explicit gate semantics are a legitimate systems
contribution if described without inflated performance claims.

## Consequential findings

1. **Alert and object are different units.** ZTF alert packets are per detection and carry prior
   history and image cutouts; I SPY works at the aggregated object level. Campaign counts must label
   whether they refer to detection rows, broker objects, distinct object identifiers, or candidate
   evaluations.
2. **Broker probabilities are model outputs, not discovery probabilities.** The original ALeRCE
   light-curve classifier is hierarchical and uses a balanced random forest with 152 features.
   Its performance varies with magnitude, number of detections, and band coverage, and the authors
   report material subclass confusion. I SPY's combined score must therefore be called a priority
   score, never a calibrated posterior.
3. **The I SPY stage totals do not form a closed survival cohort.** There are 200 verification
   evaluations and 193 catalog evaluations, with historical reruns and incomplete artifacts. They
   support stage-specific rejection fractions, not an end-to-end confusion matrix or completeness
   estimate.
4. **Fixed-radius crossmatching is a heuristic.** A 3-arcsec cone can be useful as a conservative
   veto, but association probability depends on astrometric uncertainties, local source density,
   and non-positional evidence. The future pipeline should compute a Bayes factor or chance-
   coincidence probability rather than treat every neighbor equivalently.
5. **A zero SkyBoT rejection count is not evidence of zero Solar System contamination.** The
   selected ALeRCE classes and multi-epoch/stationarity requirements precondition the sample. The
   95% Wilson upper bound for 0/200 is 1.88% even under an IID binomial model, which itself is only
   descriptive here.
6. **External-query failure is scientifically meaningful state.** Treating failed TNS calls as
   `unknown` rather than `no match` is a core safety property and closely matches AMPEL's emphasis
   on changing information states.
7. **Human review is established practice, but it needs reliability measurement.** The ALeRCE
   SN Hunter and ZTF Bright Transient Survey both couple automatic filtering to expert scanning.
   I SPY should add blinded duplicate review and Cohen's kappa or raw agreement on stamp decisions.
8. **Performance needs prospective or replay validation.** AMPEL compared more than 200 selection
   functions by reprocessing ZTF alerts. HiTS used injected transient light curves and empirical
   limiting-magnitude distributions. ZTF BTS built a magnitude-limited statistical sample with
   quantified spectroscopic completeness. I SPY should adopt one or more of these patterns.

## Statistical interpretation

The observed fractions are descriptive workload/yield measures:

- known-variable rejection: 55/193 = 28.5%, Wilson 95% interval 22.6--35.2%;
- known-TNS rejection: 30/200 = 15.0%, Wilson 95% interval 10.7--20.6%;
- SkyBoT rejection: 0/200, Wilson 95% upper bound 1.88%;
- submitted-and-designated: 2/3824 = 0.0523%, Wilson 95% interval 0.0143--0.1905%;
- credited case with complete provenance: 1/3824 = 0.0262%, Wilson 95% interval
  0.0046--0.1480%.

These intervals are not inferential confidence intervals for a stable alert population because the
pipeline configuration changed, observations are not necessarily independent, and stage counts do
not share a single denominator. They are useful only to communicate finite-count scale.

## Required manuscript changes

- Add a related-work section distinguishing survey, broker, decision layer, and registry.
- Define alert/detection/object/evaluation/packet/designation as separate accounting units.
- Describe the score as a non-probabilistic utility function and analyze its monotonic behavior.
- Explain non-detections and negative subtractions as evidence not represented by the simple score.
- Replace the implied sequential funnel with stage-specific accounting and explicit denominator
  caveats.
- Add Wilson descriptive intervals but state why they are not population inference.
- Add systematic-risk analysis: query censoring, catalog incompleteness, chance associations,
  configuration drift, cache staleness, manual-review bias, and missing negative labels.
- Add a concrete prospective validation protocol: frozen manifest, replay set, injection/recovery,
  ablations, reliability diagrams, precision-recall curves, decision latency, and dual review.
- Cite primary arXiv papers for all comparisons and retain cautious language around AT 2026rsp.

## Stop rationale

The search stopped after two bounded waves because each material section has primary support and
additional searches were returning duplicates or tangential classification papers. No additional
source is likely to alter the central conclusion that I SPY currently supports process/yield claims
but not classifier-performance or astrophysical-rate claims.
