from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from siderea.host import (
    HostCandidate,
    angular_separation_arcsec,
    associate_hosts,
    chance_coincidence_association,
)
from siderea.ml.baseline import (
    SKLEARN_AVAILABLE,
    BaselineConfig,
    chronological_split,
    fit_baseline,
    load_baseline_bundle,
    save_baseline_bundle,
)
from siderea.ranking import QueueCandidate, build_nightly_queue


class ChronologicalSplitTests(unittest.TestCase):
    def test_timestamp_ties_never_cross_partitions(self) -> None:
        timestamps = np.repeat(np.arange(5, dtype=float), 2)
        split = chronological_split(
            timestamps,
            train_fraction=0.4,
            calibration_fraction=0.2,
        )
        partitions = [split.train, split.calibration, split.test]
        for timestamp in np.unique(timestamps):
            containing = [
                index
                for index, partition in enumerate(partitions)
                if np.any(timestamps[partition] == timestamp)
            ]
            self.assertEqual(len(containing), 1)
        self.assertLess(timestamps[split.train].max(), timestamps[split.calibration].min())
        self.assertLess(timestamps[split.calibration].max(), timestamps[split.test].min())

    def test_repeated_entities_are_purged_from_earlier_partitions(self) -> None:
        timestamps = np.arange(12, dtype=float)
        entities = np.asarray(["repeated", *[f"source-{index}" for index in range(10)], "repeated"])
        split = chronological_split(
            timestamps,
            train_fraction=0.5,
            calibration_fraction=0.25,
            entity_ids=entities,
        )
        train_entities = set(entities[split.train])
        calibration_entities = set(entities[split.calibration])
        test_entities = set(entities[split.test])
        self.assertFalse(train_entities & calibration_entities)
        self.assertFalse(train_entities & test_entities)
        self.assertFalse(calibration_entities & test_entities)
        self.assertEqual(split.purged_rows, 1)


@unittest.skipUnless(SKLEARN_AVAILABLE, "scikit-learn is an optional dependency")
class SupervisedBaselineTests(unittest.TestCase):
    @staticmethod
    def _data() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        timestamps = np.arange(40, dtype=float)
        labels = (np.arange(40) % 2).astype(int)
        features = np.column_stack(
            (
                labels * 2.0 - 1.0 + np.linspace(-0.2, 0.2, 40),
                np.sin(timestamps / 3.0),
            )
        )
        features[5, 1] = np.nan
        return features, labels, timestamps

    def test_calibration_and_diagnostics_use_later_held_out_partitions(self) -> None:
        features, labels, timestamps = self._data()
        model = fit_baseline(
            features,
            labels,
            timestamps,
            feature_names=("shape", "cadence"),
            unique_entities_asserted=True,
            config=BaselineConfig(
                train_fraction=0.6,
                calibration_fraction=0.2,
                min_calibration_per_class=2,
                evaluation_review_budget=4,
            ),
        )
        metadata = model.metadata
        self.assertTrue(model.is_calibrated)
        self.assertTrue(metadata.calibration_applied)
        self.assertEqual(metadata.score_semantics, "held_out_sigmoid_calibrated_probability")
        self.assertLess(metadata.train_time_range[1], metadata.calibration_time_range[0])
        self.assertLess(metadata.calibration_time_range[1], metadata.test_time_range[0])
        self.assertIn("brier_score", metadata.test_diagnostics)
        self.assertIn("expected_calibration_error", metadata.test_diagnostics)
        self.assertEqual(
            metadata.test_diagnostics["boundary_tie_policy"],
            "expected_uniform_within_equal_score_cutoff",
        )
        scores = model.predict_scores(features[-3:])
        self.assertTrue(bool(np.isfinite(scores).all()))
        self.assertTrue(bool(((scores >= 0.0) & (scores <= 1.0)).all()))
        named_scores = model.predict_feature_records(
            [{"cadence": float(row[1]), "shape": float(row[0])} for row in features[-3:]]
        )
        np.testing.assert_allclose(named_scores, scores)
        with self.assertRaisesRegex(ValueError, "fitted contract"):
            model.predict_feature_records([{"shape": 1.0}])

        with tempfile.TemporaryDirectory() as temporary_directory:
            output = metadata.write_json(Path(temporary_directory) / "metadata.json")
            loaded = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(loaded["feature_names"], ["shape", "cadence"])
        self.assertEqual(len(loaded["dataset_sha256"]), 64)
        self.assertEqual(len(loaded["split_sha256"]), 64)
        self.assertEqual(loaded["training_config"]["train_fraction"], 0.6)
        self.assertFalse(loaded["entity_purging_applied"])

    def test_entity_ids_are_part_of_reproducibility_metadata(self) -> None:
        features, labels, timestamps = self._data()
        first_entities = np.asarray([f"source-{index}" for index in range(len(labels))])
        second_entities = first_entities.copy()
        second_entities[0] = "different-source"
        config = BaselineConfig(
            train_fraction=0.6,
            calibration_fraction=0.2,
            calibration="none",
        )

        first = fit_baseline(
            features,
            labels,
            timestamps,
            entity_ids=first_entities,
            config=config,
        )
        second = fit_baseline(
            features,
            labels,
            timestamps,
            entity_ids=second_entities,
            config=config,
        )

        self.assertTrue(first.metadata.entity_purging_applied)
        self.assertNotEqual(first.metadata.dataset_sha256, second.metadata.dataset_sha256)

    def test_uncalibrated_scores_are_not_given_calibration_metrics(self) -> None:
        features, labels, timestamps = self._data()
        model = fit_baseline(
            features,
            labels,
            timestamps,
            unique_entities_asserted=True,
            config=BaselineConfig(
                train_fraction=0.6,
                calibration_fraction=0.2,
                calibration="none",
            ),
        )
        self.assertFalse(model.metadata.calibration_applied)
        self.assertFalse(model.is_calibrated)
        self.assertEqual(model.metadata.score_semantics, "uncalibrated_model_score")
        self.assertNotIn("brier_score", model.metadata.test_diagnostics)
        self.assertNotIn("expected_calibration_error", model.metadata.test_diagnostics)

    def test_fractional_labels_are_rejected_instead_of_truncated(self) -> None:
        features, labels, timestamps = self._data()
        fractional = labels.astype(float)
        fractional[3] = 0.9
        with self.assertRaisesRegex(ValueError, "binary values"):
            fit_baseline(
                features,
                fractional,
                timestamps,
                config=BaselineConfig(
                    train_fraction=0.6,
                    calibration_fraction=0.2,
                    calibration="none",
                ),
            )

    def test_training_requires_entity_purging_or_explicit_unique_row_assertion(self) -> None:
        features, labels, timestamps = self._data()
        with self.assertRaisesRegex(ValueError, "entity_ids are required"):
            fit_baseline(
                features,
                labels,
                timestamps,
                config=BaselineConfig(
                    train_fraction=0.6,
                    calibration_fraction=0.2,
                    calibration="none",
                ),
            )

    def test_training_rejects_features_unsupported_in_the_training_partition(self) -> None:
        features, labels, timestamps = self._data()
        features[:24, 1] = np.nan
        with self.assertRaisesRegex(ValueError, "no finite measurements.*cadence"):
            fit_baseline(
                features,
                labels,
                timestamps,
                feature_names=np.asarray(["shape", "cadence"]),
                unique_entities_asserted=True,
                config=BaselineConfig(
                    train_fraction=0.6,
                    calibration_fraction=0.2,
                    calibration="none",
                ),
            )

    def test_nonfinite_baseline_configuration_is_rejected(self) -> None:
        for keyword in ("train_fraction", "calibration_fraction", "regularization_c"):
            with self.subTest(keyword=keyword), self.assertRaises(ValueError):
                BaselineConfig(**{keyword: float("nan")})

        for keyword in ("train_fraction", "calibration_fraction", "regularization_c"):
            with self.subTest(keyword=keyword), self.assertRaises(ValueError):
                BaselineConfig(**{keyword: True})

    def test_noninteger_baseline_count_configuration_is_rejected(self) -> None:
        for keyword in (
            "min_calibration_per_class",
            "max_iterations",
            "random_state",
            "evaluation_review_budget",
        ):
            with self.subTest(keyword=keyword), self.assertRaisesRegex(ValueError, "integers"):
                BaselineConfig(**{keyword: 1.5})

    def test_bundle_is_hashed_and_requires_explicit_trust(self) -> None:
        features, labels, timestamps = self._data()
        model = fit_baseline(
            features,
            labels,
            timestamps,
            unique_entities_asserted=True,
            config=BaselineConfig(
                train_fraction=0.6,
                calibration_fraction=0.2,
                calibration="none",
            ),
        )
        with tempfile.TemporaryDirectory() as folder:
            bundle = save_baseline_bundle(Path(folder) / "baseline", model)
            with self.assertRaisesRegex(ValueError, "trusted=True"):
                load_baseline_bundle(bundle)
            loaded = load_baseline_bundle(bundle, trusted=True)
            np.testing.assert_allclose(
                loaded.predict_scores(features[-3:]),
                model.predict_scores(features[-3:]),
            )


class NightlyQueueTests(unittest.TestCase):
    def test_candidate_numeric_scores_and_eligibility_reject_booleans(self) -> None:
        with self.assertRaises(ValueError):
            QueueCandidate("candidate", True)
        with self.assertRaisesRegex(ValueError, "eligible must be boolean"):
            QueueCandidate("candidate", 0.5, eligible=1)  # type: ignore[arg-type]

    def test_budget_has_deduplicated_anomaly_reserve_and_stable_ties(self) -> None:
        candidates = [
            QueueCandidate("b", 0.9, 0.1),
            QueueCandidate("a", 0.9, 0.1),
            QueueCandidate("z-anomaly", 0.05, 0.99),
            QueueCandidate("c", 0.8, 0.2),
            QueueCandidate("excluded", 1.0, 1.0, False, "failed evidence gate"),
        ]
        queue = build_nightly_queue(
            candidates,
            budget=3,
            anomaly_slots=1,
            anomaly_threshold=0.8,
        )
        self.assertEqual([entry.candidate_id for entry in queue.entries], ["a", "b", "z-anomaly"])
        self.assertEqual(
            [entry.selection_route for entry in queue.entries],
            ["priority", "priority", "anomaly_reserve"],
        )
        self.assertEqual(queue.used_anomaly_slots, 1)
        self.assertEqual(queue.excluded_candidates, 1)

    def test_unused_anomaly_reserve_flows_back_to_priority(self) -> None:
        queue = build_nightly_queue(
            [QueueCandidate("first", 0.9), QueueCandidate("second", 0.8)],
            budget=2,
            anomaly_slots=1,
            anomaly_threshold=0.8,
        )
        self.assertEqual([entry.candidate_id for entry in queue.entries], ["first", "second"])
        self.assertEqual(queue.entries[-1].selection_route, "priority_fill")
        self.assertEqual(queue.unused_slots, 0)

    def test_random_audit_is_replayable_order_invariant_and_logs_propensity(self) -> None:
        candidates = [
            QueueCandidate(f"source-{index}", 1.0 - index / 10, index / 10) for index in range(6)
        ]
        first = build_nightly_queue(
            candidates,
            budget=4,
            anomaly_slots=1,
            anomaly_threshold=0.4,
            audit_slots=1,
            audit_seed="night-2026-09-06",
            selection_policy="triage_v1",
        )
        replay = build_nightly_queue(
            list(reversed(candidates)),
            budget=4,
            anomaly_slots=1,
            anomaly_threshold=0.4,
            audit_slots=1,
            audit_seed="night-2026-09-06",
            selection_policy="triage_v1",
        )

        self.assertEqual(first, replay)
        self.assertEqual(len(first.entries), 4)
        self.assertEqual(first.schema, "siderea.nightly_queue.v2")
        self.assertEqual(first.audit_population, 6)
        self.assertEqual(first.used_audit_slots, 1)
        self.assertAlmostEqual(first.audit_selection_probability or 0.0, 1.0 / 6.0)
        audit = [entry for entry in first.entries if entry.selection_route == "random_audit"]
        self.assertEqual(len(audit), 1)
        self.assertAlmostEqual(audit[0].selection_propensity or 0.0, 1.0 / 6.0)
        self.assertEqual(len({entry.candidate_id for entry in first.entries}), 4)

    def test_random_audit_requires_an_explicit_replay_seed(self) -> None:
        with self.assertRaisesRegex(ValueError, "audit_seed"):
            build_nightly_queue(
                [QueueCandidate("candidate", 0.5)],
                budget=1,
                audit_slots=1,
            )


class HostAssociationTests(unittest.TestCase):
    def test_zero_background_density_is_rejected_as_false_certainty(self) -> None:
        with self.assertRaises(ValueError):
            HostCandidate("host", 10.0, 0.0, background_density_per_sq_deg=0.0)

    def test_angular_separation_handles_right_ascension_wrap(self) -> None:
        separation = angular_separation_arcsec(359.999, 0.0, 0.001, 0.0)
        self.assertAlmostEqual(separation, 7.2, places=5)

    def test_chance_statistic_is_bounded_and_explicitly_not_posterior(self) -> None:
        host = HostCandidate(
            "host-a",
            10.0001,
            -20.0,
            background_density_per_sq_deg=1_000.0,
            half_light_radius_arcsec=1.2,
            position_sigma_arcsec=0.1,
        )
        association = chance_coincidence_association(
            10.0,
            -20.0,
            host,
            transient_position_sigma_arcsec=0.2,
        )
        self.assertTrue(0.0 <= association.chance_coincidence_probability <= 1.0)
        self.assertFalse(association.statistic_is_posterior)
        self.assertTrue(association.uncertainty_complete)
        self.assertAlmostEqual(association.combined_position_sigma_arcsec, math.hypot(0.2, 0.1))

    def test_undefined_normalized_offset_is_none_and_extreme_scales_fail_cleanly(self) -> None:
        point_host = HostCandidate(
            "point-host",
            10.001,
            0.0,
            background_density_per_sq_deg=100.0,
        )
        association = chance_coincidence_association(10.0, 0.0, point_host)
        self.assertIsNone(association.normalized_offset)
        self.assertTrue(math.isfinite(association.chance_coincidence_probability))

        huge_host = HostCandidate(
            "huge-host",
            10.0,
            0.0,
            background_density_per_sq_deg=1.0,
            half_light_radius_arcsec=1.0e308,
        )
        with self.assertRaisesRegex(ValueError, "finite numeric range"):
            chance_coincidence_association(10.0, 0.0, huge_host)

    def test_missing_or_zero_uncertainty_blocks_automatic_acceptance(self) -> None:
        for position_sigma in (None, 0.0):
            with self.subTest(position_sigma=position_sigma):
                host = HostCandidate(
                    "only-host",
                    10.0,
                    0.0,
                    background_density_per_sq_deg=100.0,
                    position_sigma_arcsec=position_sigma,
                )
                result = associate_hosts(
                    10.0,
                    0.0,
                    [host],
                    transient_position_sigma_arcsec=0.2,
                )
                self.assertTrue(result.ambiguous)
                self.assertEqual(result.preferred_host_id, "only-host")
                self.assertIsNone(result.accepted_host_id)
                self.assertFalse(result.associations[0].uncertainty_complete)
                self.assertIn("explicit positive", result.reason)

        unknown_transient = associate_hosts(
            10.0,
            0.0,
            [
                HostCandidate(
                    "only-host",
                    10.0,
                    0.0,
                    background_density_per_sq_deg=100.0,
                    position_sigma_arcsec=0.1,
                )
            ],
        )
        self.assertIsNone(unknown_transient.accepted_host_id)
        self.assertIsNone(unknown_transient.associations[0].combined_position_sigma_arcsec)

    def test_ambiguous_hosts_are_ranked_but_not_accepted(self) -> None:
        hosts = [
            HostCandidate("a", 20.0 + 1.0 / 3_600.0, 0.0, 500.0, 0.5),
            HostCandidate("b", 20.0 - 1.1 / 3_600.0, 0.0, 500.0, 0.5),
        ]
        result = associate_hosts(20.0, 0.0, hosts, minimum_contrast_ratio=3.0)
        self.assertTrue(result.ambiguous)
        self.assertIsNotNone(result.preferred_host_id)
        self.assertIsNone(result.accepted_host_id)

    def test_distinct_low_chance_host_can_be_accepted(self) -> None:
        hosts = [
            HostCandidate("near", 30.0, 5.0, 100.0, 1.0, 0.1),
            HostCandidate("far", 30.01, 5.0, 100.0, 1.0, 0.1),
        ]
        result = associate_hosts(
            30.0,
            5.0,
            hosts,
            transient_position_sigma_arcsec=0.2,
        )
        self.assertFalse(result.ambiguous)
        self.assertEqual(result.accepted_host_id, "near")

    def test_density_uncertainty_bounds_can_be_required_for_acceptance(self) -> None:
        missing_density_error = HostCandidate(
            "host",
            30.0,
            5.0,
            100.0,
            1.0,
            0.1,
        )
        blocked = associate_hosts(
            30.0,
            5.0,
            [missing_density_error],
            transient_position_sigma_arcsec=0.2,
            require_density_uncertainty=True,
        )
        self.assertIsNone(blocked.accepted_host_id)
        self.assertIn("background-density", blocked.reason)

        measured_density_error = HostCandidate(
            "host",
            30.0,
            5.0,
            100.0,
            1.0,
            0.1,
            10.0,
        )
        accepted = associate_hosts(
            30.0,
            5.0,
            [measured_density_error],
            transient_position_sigma_arcsec=0.2,
            require_density_uncertainty=True,
        )
        association = accepted.associations[0]
        self.assertEqual(accepted.accepted_host_id, "host")
        self.assertTrue(association.density_uncertainty_complete)
        self.assertLess(
            association.chance_coincidence_probability_lower_bound,
            association.chance_coincidence_probability,
        )
        self.assertGreater(
            association.chance_coincidence_probability_upper_bound,
            association.chance_coincidence_probability,
        )


if __name__ == "__main__":
    unittest.main()
