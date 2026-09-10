"""Robustness candidates for the preregistered transient-search v2 study.

These helpers are research-only. They do not alter ``siderea.transient_search.v1``
outputs, reportability, or any evidence gate. Statistics from this module require
empirical calibration under the frozen v2 protocol and must not be interpreted as
Gaussian sigma, chi-square, probability, or an astrophysical classification.
"""

from __future__ import annotations

from typing import Any

from siderea.research.transients import TransientBank


def selected_template_loo_stability(bank: TransientBank, flux: Any) -> dict[str, Any]:
    """Return the preregistered selected-template leave-one-out stability statistic.

    The full search chooses one template exactly as v1 does. The existing influence
    diagnostic then deletes each observation in turn, refits the constant background
    on the retained covariance marginal, and evaluates that *same* selected template.
    V2 uses the minimum retained statistic as a conservative support requirement.

    If any deletion makes the selected template unidentifiable, the research
    statistic fails closed to zero. The template is deliberately not reselected
    after deletion; re-selection would create another multiple-template search and
    would require a separately calibrated protocol.
    """

    if not isinstance(bank, TransientBank):
        raise TypeError("bank must be a TransientBank")

    fit = bank.fit(flux)
    influence = fit["influence"]
    minimum_remaining = influence["minimum_remaining_local_z"]
    unidentifiable = int(influence["unidentifiable_deletions"])

    if minimum_remaining is None or unidentifiable:
        statistic = 0.0
        status = "unidentifiable_deletion"
    else:
        statistic = min(float(fit["max_local_z"]), float(minimum_remaining))
        status = "evaluated"

    return {
        "schema": "siderea.selected_template_loo_stability.v1",
        "mode": "research_only",
        "status": status,
        "statistic": statistic,
        "raw_max_local_z": float(fit["max_local_z"]),
        "selected_template": fit["template"],
        "minimum_remaining_selected_template_statistic": minimum_remaining,
        "unidentifiable_deletions": unidentifiable,
        "most_influential_row": influence["most_influential_row"],
        "most_influential_mjd": influence["most_influential_mjd"],
        "bank_digest": fit["bank_digest"],
        "score_semantics": "empirical_search_statistic_not_sigma_probability_or_chi_square",
        "changes_v1_detection_rule": False,
        "qualifies_reportability": False,
    }
