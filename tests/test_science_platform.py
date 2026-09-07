from __future__ import annotations

import unittest
from datetime import UTC, datetime

import numpy as np

from iris.anomaly import RobustAnomalyDetector
from iris.campaigns import CampaignProfile, get_campaign
from iris.evaluation import chronological_indices, ranking_metrics
from iris.followup import (
    FollowupFactors,
    explain_followup_priority,
    followup_priority,
    hours_since,
)


class EvaluationTests(unittest.TestCase):
    def test_review_budget_metrics(self):
        metrics = ranking_metrics([1, 0, 1, 0], [0.9, 0.8, 0.7, 0.1], review_budget=2)
        self.assertEqual(metrics.reviewed, 2)
        self.assertAlmostEqual(metrics.precision_at_k, 0.5)
        self.assertAlmostEqual(metrics.recall_at_k, 0.5)

    def test_ranking_metrics_are_invariant_to_equal_score_row_order(self):
        first = ranking_metrics([1, 0], [0.5, 0.5], review_budget=1)
        reversed_rows = ranking_metrics([0, 1], [0.5, 0.5], review_budget=1)

        self.assertAlmostEqual(first.average_precision, 0.5)
        self.assertAlmostEqual(first.precision_at_k, 0.5)
        self.assertAlmostEqual(first.recall_at_k, 0.5)
        self.assertEqual(first, reversed_rows)
        self.assertEqual(
            first.boundary_tie_policy,
            "expected_uniform_within_equal_score_cutoff",
        )

    def test_chronological_split_has_no_future_in_train(self):
        train, validation, test = chronological_indices(
            [4, 1, 3, 2, 5], train_fraction=0.6, validation_fraction=0.2
        )
        self.assertLess(
            max(np.array([4, 1, 3, 2, 5])[train]), min(np.array([4, 1, 3, 2, 5])[validation])
        )
        self.assertLess(
            max(np.array([4, 1, 3, 2, 5])[validation]), min(np.array([4, 1, 3, 2, 5])[test])
        )

    def test_chronological_split_keeps_equal_times_in_one_partition(self):
        timestamps = np.array([1, 1, 2, 2, 3, 3, 4, 4], dtype=float)
        train, validation, test = chronological_indices(
            timestamps, train_fraction=0.5, validation_fraction=0.25
        )
        partitions = [set(timestamps[index]) for index in (train, validation, test)]
        self.assertFalse(partitions[0] & partitions[1])
        self.assertFalse(partitions[1] & partitions[2])

    def test_fractional_labels_are_not_silently_truncated(self):
        with self.assertRaisesRegex(ValueError, "binary"):
            ranking_metrics([0.5, 1.0], [0.1, 0.9], review_budget=1)

    def test_calibration_attestation_must_be_an_explicit_boolean(self):
        with self.assertRaisesRegex(ValueError, "explicit boolean"):
            ranking_metrics(
                [0, 1],
                [0.2, 0.8],
                review_budget=1,
                calibrated_probabilities="false",  # type: ignore[arg-type]
            )

    def test_numeric_evaluation_inputs_reject_booleans(self):
        with self.assertRaisesRegex(ValueError, "timestamps.*booleans"):
            chronological_indices([False, 1.0, 2.0])
        with self.assertRaisesRegex(ValueError, "scores.*booleans"):
            ranking_metrics([0, 1], [False, 0.8], review_budget=1)


class FollowupTests(unittest.TestCase):
    def test_low_reality_caps_anomaly_route(self):
        factors = FollowupFactors(0.1, 1, 1, 1, 1, 1)
        self.assertLess(followup_priority(factors, anomaly_score=1), 0.2)

    def test_followup_priority_exposes_routes_and_non_probability_semantics(self):
        factors = FollowupFactors(0.8, 0.0, 1.0, 1.0, 1.0, 1.0)
        result = explain_followup_priority(factors, anomaly_score=1.0)

        self.assertEqual(result.selected_route, "anomaly_reserve")
        self.assertEqual(result.priority, result.anomaly_route_score)
        self.assertEqual(result.score_semantics, "heuristic_priority_not_probability")
        self.assertEqual(followup_priority(factors, anomaly_score=1.0), result.priority)

    def test_campaign_exists(self):
        profile = get_campaign("ispy")
        self.assertGreater(profile.suggested_review_budget_per_night, 0)
        self.assertEqual(profile.operational_status, "advisory_only_not_enforced")
        self.assertFalse(hasattr(profile, "minimum_calibrated_reality_probability"))

    def test_campaign_advice_rejects_fractional_or_boolean_budgets(self):
        common = {
            "name": "test",
            "description": "test profile",
            "recommended_services": ("service",),
            "research_target_labels": ("target",),
        }
        for budget in (True, 1.5):
            with self.subTest(budget=budget), self.assertRaisesRegex(ValueError, "integer"):
                CampaignProfile(
                    suggested_review_budget_per_night=budget,  # type: ignore[arg-type]
                    **common,
                )

    def test_non_finite_followup_inputs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            followup_priority(FollowupFactors(float("nan"), 1, 1, 1, 1, 1))
        with self.assertRaisesRegex(ValueError, "timezone"):
            hours_since(60_000.0, now=datetime(2026, 1, 1))
        with self.assertRaisesRegex(ValueError, "future"):
            hours_since(70_000.0, now=datetime(2026, 1, 1, tzinfo=UTC))


class AnomalyTests(unittest.TestCase):
    def test_missing_row_is_visible_and_does_not_gain_anomaly_priority(self):
        detector = RobustAnomalyDetector(use_isolation_forest=False).fit(
            np.array([[0.0, 1.0], [1.0, 2.0]])
        )
        result = detector.score(np.array([[np.nan, np.nan], [10.0, 10.0]]))
        self.assertEqual(result.observed_fraction[0], 0.0)
        self.assertFalse(result.score_valid[0])
        self.assertTrue(result.score_valid[1])
        self.assertEqual(result.score_semantics, "heuristic_anomaly_rank_not_probability")
        self.assertEqual(result.combined_score[0], 0.0)
        self.assertGreater(result.combined_score[1], 0.0)

    def test_infinite_features_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "not infinite"):
            RobustAnomalyDetector(use_isolation_forest=False).fit(np.array([[0.0], [np.inf]]))
        with self.assertRaisesRegex(ValueError, "two finite measurements"):
            RobustAnomalyDetector(use_isolation_forest=False).fit(
                np.array([[np.nan, 1.0], [np.nan, np.nan]])
            )

    def test_features_unseen_during_fit_cannot_create_fake_anomalies(self):
        detector = RobustAnomalyDetector(use_isolation_forest=False).fit(
            np.array([[0.0, np.nan], [1.0, np.nan], [2.0, np.nan]])
        )

        result = detector.score(np.array([[1.0, 1.0e12], [np.nan, 1.0e12]]))

        self.assertEqual(result.supported_feature_fraction, 0.5)
        self.assertEqual(result.observed_fraction.tolist(), [1.0, 0.0])
        self.assertEqual(result.score_valid.tolist(), [True, False])
        self.assertEqual(result.combined_score.tolist(), [0.0, 0.0])

    def test_minimum_feature_coverage_abstains_instead_of_imputing_priority(self):
        detector = RobustAnomalyDetector(
            use_isolation_forest=False,
            minimum_observed_fraction=0.75,
        ).fit(np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]))

        result = detector.score(np.array([[100.0, np.nan, np.nan], [100.0, 2.0, 3.0]]))

        self.assertEqual(result.observed_fraction.tolist(), [1 / 3, 1.0])
        self.assertEqual(result.score_valid.tolist(), [False, True])
        self.assertEqual(result.combined_score[0], 0.0)
        self.assertGreater(result.combined_score[1], 0.0)

        for threshold in (float("nan"), -0.1, 1.1):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                RobustAnomalyDetector(minimum_observed_fraction=threshold)

    def test_extreme_finite_features_remain_numerically_defined(self):
        detector = RobustAnomalyDetector(use_isolation_forest=False).fit(
            np.array([[-1.0e308], [1.0e308]])
        )

        with np.errstate(all="raise"):
            result = detector.score(np.array([[1.0e308], [-1.0e308], [0.0]]))

        self.assertTrue(np.isfinite(result.combined_score).all())
        self.assertTrue(((result.combined_score >= 0.0) & (result.combined_score <= 1.0)).all())


if __name__ == "__main__":
    unittest.main()
