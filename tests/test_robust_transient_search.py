from __future__ import annotations

import numpy as np
import pytest

from siderea.research.robust_transients import selected_template_loo_stability
from siderea.research.transients import TransientBank, transient_template


def test_stability_rejects_single_epoch_outlier():
    times = np.arange(20.0)
    bank = TransientBank(times, np.ones(20), centers=[10], widths=[2], families=["gaussian"])
    flux = np.zeros(20)
    flux[10] = 20

    result = selected_template_loo_stability(bank, flux)

    assert result["raw_max_local_z"] > 0
    assert result["statistic"] == pytest.approx(0, abs=1e-10)
    assert result["most_influential_row"] == 10
    assert result["score_semantics"] == "empirical_search_statistic_not_sigma_probability_or_chi_square"
    assert result["changes_v1_detection_rule"] is False
    assert result["qualifies_reportability"] is False


def test_stability_retains_multi_epoch_supported_pulse():
    times = np.arange(20.0)
    bank = TransientBank(times, np.ones(20), centers=[10], widths=[2], families=["gaussian"])
    flux = 8 * transient_template(times, center=10, width=2, family="gaussian")

    result = selected_template_loo_stability(bank, flux)

    assert result["status"] == "evaluated"
    assert 0 < result["statistic"] <= result["raw_max_local_z"]
    assert result["statistic"] > 0.8 * result["raw_max_local_z"]


def test_stability_uses_retained_covariance_marginal():
    times = np.arange(20.0)
    correlation = 0.6 ** np.abs(times[:, None] - times)
    bank = TransientBank(
        times,
        np.ones(20),
        centers=[10],
        widths=[2],
        families=["gaussian"],
        correlation=correlation,
    )
    flux = np.zeros(20)
    flux[10] = 20

    result = selected_template_loo_stability(bank, flux)

    assert result["statistic"] == pytest.approx(0, abs=1e-10)
    assert result["most_influential_row"] == 10


def test_stability_is_zero_for_constant_curve():
    times = np.arange(20.0)
    bank = TransientBank(times, np.ones(20), centers=[10], widths=[2], families=["gaussian"])

    result = selected_template_loo_stability(bank, np.full(20, 100.0))

    assert result["raw_max_local_z"] == pytest.approx(0)
    assert result["statistic"] == pytest.approx(0)


def test_stability_rejects_wrong_bank_type():
    with pytest.raises(TypeError, match="TransientBank"):
        selected_template_loo_stability(object(), np.zeros(4))  # type: ignore[arg-type]
