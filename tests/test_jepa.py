"""CPU-small tests for the optional IRIS irregular-time TS-JEPA path."""

from __future__ import annotations

import contextlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import torch
except ImportError:  # pragma: no cover - makes the base test suite dependency-safe.
    torch = None

if torch is not None:
    from iris.cli import main as iris_main
    from iris.ml.dataset import (
        BAND_INDEX,
        DEFAULT_BAND_TO_ID,
        DELTA_TIME_INDEX,
        DETECTION_INDEX,
        ERROR_INDEX,
        TOKEN_DIM,
        VALUE_INDEX,
        VALUE_PRESENT_INDEX,
        LightCurveDataset,
        TokenizedLightCurve,
        collate_light_curves,
        pad_light_curves,
        tokenize_light_curve,
    )
    from iris.ml.evaluate import evaluate_jepa, extract_embeddings
    from iris.ml.jepa import TSJEPA, make_contiguous_target_mask, representation_diagnostics
    from iris.ml.train import TrainingConfig, load_checkpoint, save_checkpoint, train_jepa


@unittest.skipIf(torch is None, "PyTorch is an optional IRIS dependency")
class DatasetTests(unittest.TestCase):
    def test_tokenization_preserves_irregular_time_band_and_detection_state(self) -> None:
        curve = tokenize_light_curve(
            times=[4.0, 1.0, 2.0, 8.0],
            values=[12.0, 10.0, None, 14.0],
            errors=[0.2, 0.1, 0.3, 0.4],
            bands=["r", "g", "g", "unregistered-filter"],
            detections=[True, True, False, True],
            object_id="ZTF-test",
            value_kind="flux",
        )

        self.assertEqual(curve.object_id, "ZTF-test")
        self.assertEqual(tuple(curve.times.tolist()), (1.0, 2.0, 4.0, 8.0))
        self.assertEqual(tuple(curve.tokens.shape), (4, TOKEN_DIM))
        self.assertEqual(curve.tokens[:, DETECTION_INDEX].tolist(), [1.0, 0.0, 1.0, 1.0])
        self.assertEqual(curve.tokens[:, VALUE_PRESENT_INDEX].tolist(), [1.0, 0.0, 1.0, 1.0])
        self.assertEqual(int(curve.tokens[-1, BAND_INDEX]), DEFAULT_BAND_TO_ID["unknown"])
        self.assertEqual(curve.metadata["unknown_band_count"], 1)
        self.assertEqual(curve.metadata["unknown_bands"], ("unregistered-filter",))
        self.assertFalse(curve.metadata["detection_flags_inferred"])
        self.assertEqual(len(curve.metadata["token_contract_sha256"]), 64)
        deltas = curve.tokens[:, DELTA_TIME_INDEX].tolist()
        self.assertEqual(deltas[0], 0.0)
        self.assertGreater(deltas[-1], deltas[1])
        self.assertTrue(bool(torch.isfinite(curve.tokens).all()))

        shorter = tokenize_light_curve(
            [1.0, 3.0],
            [5.0, 7.0],
            [0.2, 0.2],
            ["g", "r"],
            [True, True],
            object_id="short",
        )
        batch = pad_light_curves([curve, shorter])
        self.assertEqual(tuple(batch.tokens.shape), (2, 4, TOKEN_DIM))
        self.assertEqual(batch.padding_mask.tolist(), [[True] * 4, [True, True, False, False]])
        self.assertEqual(batch.lengths.tolist(), [4, 2])

    def test_bad_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tokenize_light_curve([1.0], [2.0, 3.0], [0.1], ["g"])
        with self.assertRaises(ValueError):
            tokenize_light_curve([float("nan")], [2.0], [0.1], ["g"])
        with self.assertRaisesRegex(ValueError, "errors must be positive"):
            tokenize_light_curve([1.0], [2.0], [-0.1], ["g"], [True])
        with self.assertRaisesRegex(ValueError, "requires a finite value"):
            tokenize_light_curve([1.0], [None], [0.1], ["g"], [True])
        for field, arguments in {
            "observation time": ([True], [2.0], [0.1], ["g"]),
            "photometry value": ([1.0], [True], [0.1], ["g"]),
            "photometry error": ([1.0], [2.0], [True], ["g"]),
        }.items():
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(
                    ValueError,
                    f"{field}.*boolean",
                ),
            ):
                tokenize_light_curve(*arguments, [True])
        with self.assertRaisesRegex(ValueError, "passbands cannot be boolean"):
            tokenize_light_curve([1.0], [2.0], [0.1], [True], [True])
        with self.assertRaisesRegex(ValueError, "band IDs must be unique"):
            tokenize_light_curve(
                [1.0],
                [2.0],
                [0.1],
                ["g"],
                [True],
                band_to_id={"g": 0, "unknown": 0},
            )

    def test_extreme_finite_inputs_do_not_create_nonfinite_tokens(self) -> None:
        curve = tokenize_light_curve(
            [1.0, 2.0],
            [-1e308, 1e308],
            [1e307, 1e307],
            ["g", "g"],
            [True, True],
        )
        self.assertTrue(bool(torch.isfinite(curve.tokens).all()))
        self.assertTrue(math.isfinite(curve.metadata["value_center"]))
        self.assertTrue(math.isfinite(curve.metadata["value_scale"]))

        with self.assertRaisesRegex(ValueError, "time span.*rescale"):
            tokenize_light_curve(
                [-1e308, 1e308],
                [1.0, 2.0],
                [0.1, 0.1],
                ["g", "g"],
                [True, True],
            )

    def test_tokenization_is_invariant_to_finite_value_unit_rescaling(self) -> None:
        original = tokenize_light_curve(
            [1.0, 2.0, 4.0],
            [1.0, 2.0, 3.0],
            [0.1, 0.1, 0.1],
            ["g", "g", "g"],
            [True, True, True],
        )
        scaled = tokenize_light_curve(
            [1.0, 2.0, 4.0],
            [1.0e-12, 2.0e-12, 3.0e-12],
            [1.0e-13, 1.0e-13, 1.0e-13],
            ["g", "g", "g"],
            [True, True, True],
        )

        self.assertTrue(torch.allclose(original.tokens, scaled.tokens, atol=1e-6, rtol=1e-6))
        self.assertEqual(
            original.metadata["token_contract_sha256"],
            scaled.metadata["token_contract_sha256"],
        )

        with self.assertRaisesRegex(ValueError, "float32 numeric range.*rescale"):
            tokenize_light_curve(
                [1.0, 2.0],
                [0.0, 1.0],
                [1e308, 1e308],
                ["g", "g"],
                [True, True],
            )

    def test_flux_requires_detection_semantics_and_numeric_ztf_bands_are_normalized(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit detection flags"):
            tokenize_light_curve([1.0], [2.0], [0.1], ["1"])

        curve = tokenize_light_curve(
            [1.0, 2.0],
            [2.0, 3.0],
            [0.1, 0.1],
            ["1", "2.0"],
            [True, True],
        )
        self.assertEqual(
            curve.tokens[:, BAND_INDEX].tolist(),
            [float(DEFAULT_BAND_TO_ID["g"]), float(DEFAULT_BAND_TO_ID["r"])],
        )
        self.assertEqual(len(curve.metadata["band_vocabulary_sha256"]), 64)

    def test_custom_numeric_band_vocabulary_is_not_reinterpreted_as_ztf(self) -> None:
        curve = tokenize_light_curve(
            [1.0, 2.0],
            [2.0, 3.0],
            [0.1, 0.1],
            ["1", "2"],
            [True, True],
            band_to_id={"1": 0, "2": 1, "unknown": 2},
        )

        self.assertEqual(curve.tokens[:, BAND_INDEX].tolist(), [0.0, 1.0])

    def test_unknown_bands_can_fail_closed_and_equal_time_order_is_deterministic(self) -> None:
        with self.assertRaisesRegex(ValueError, "not in the configured vocabulary"):
            tokenize_light_curve(
                [1.0],
                [2.0],
                [0.1],
                ["unregistered-filter"],
                [True],
                allow_unknown_bands=False,
            )

        first = tokenize_light_curve(
            [1.0, 1.0, 2.0],
            [2.0, 1.0, 3.0],
            [0.2, 0.1, 0.3],
            ["r", "g", "i"],
            [True, True, True],
        )
        reordered = tokenize_light_curve(
            [1.0, 1.0, 2.0],
            [1.0, 2.0, 3.0],
            [0.1, 0.2, 0.3],
            ["g", "r", "i"],
            [True, True, True],
        )
        self.assertTrue(torch.equal(first.tokens, reordered.tokens))
        self.assertEqual(first.metadata["equal_time_ordering"], "time_band_detection_value_error")

        inferred = tokenize_light_curve(
            [1.0],
            [20.0],
            [0.2],
            ["g"],
            value_kind="magnitude",
        )
        self.assertTrue(inferred.metadata["detection_flags_inferred"])
        with self.assertRaisesRegex(ValueError, "token contracts"):
            pad_light_curves([first, inferred])

        tampered_metadata = dict(first.metadata)
        tampered_metadata["token_contract"] = {
            **tampered_metadata["token_contract"],
            "value_kind": "tampered",
        }
        tampered = TokenizedLightCurve(
            first.tokens,
            first.padding_mask,
            first.object_id,
            first.times,
            tampered_metadata,
        )
        with self.assertRaisesRegex(ValueError, "digest does not match"):
            pad_light_curves([tampered])

    def test_detection_strings_magnitude_direction_and_missing_error_sentinel(self) -> None:
        curve = tokenize_light_curve(
            [1.0, 2.0, 3.0],
            [20.0, 19.0, 18.0],
            [0.2, None, 0.2],
            ["g", "g", "g"],
            ["false", "true", "true"],
            value_kind="magnitude",
        )
        self.assertEqual(curve.tokens[:, DETECTION_INDEX].tolist(), [0.0, 1.0, 1.0])
        self.assertEqual(float(curve.tokens[1, ERROR_INDEX]), 0.0)
        self.assertGreater(float(curve.tokens[2, 1]), float(curve.tokens[0, 1]))
        self.assertEqual(curve.metadata["missing_error_count"], 1)

    def test_missing_value_and_error_metadata_describe_effective_token_content(self) -> None:
        curve = tokenize_light_curve(
            [1.0, 2.0, 3.0],
            [None, 2.0, 3.0],
            [0.5, None, 0.2],
            ["g", "g", "g"],
            [False, True, True],
        )

        self.assertEqual(curve.metadata["value_missing_count"], 1)
        self.assertEqual(curve.metadata["missing_error_count"], 1)
        self.assertEqual(curve.metadata["ignored_error_without_value_count"], 1)
        self.assertEqual(float(curve.tokens[0, ERROR_INDEX]), 0.0)
        self.assertEqual(float(curve.tokens[0, VALUE_PRESENT_INDEX]), 0.0)


@unittest.skipIf(torch is None, "PyTorch is an optional IRIS dependency")
class MaskAndModelTests(unittest.TestCase):
    @staticmethod
    def _batch():
        records = [
            {
                "object_id": "a",
                "times": [1.0, 1.5, 3.0, 8.0, 13.0],
                "values": [2.0, 2.2, 2.9, 4.2, 3.7],
                "errors": [0.1] * 5,
                "bands": ["g", "r", "g", "r", "i"],
                "detections": [True] * 5,
            },
            {
                "object_id": "b",
                "times": [2.0, 5.0, 5.5, 12.0],
                "values": [8.0, 7.0, 6.8, 5.1],
                "errors": [0.2, 0.2, 0.3, 0.2],
                "bands": ["r", "r", "g", "g"],
                "detections": [True] * 4,
            },
        ]
        dataset = LightCurveDataset(records)
        return pad_light_curves([dataset[0], dataset[1]])

    def test_contiguous_mask_respects_padding_and_leaves_context(self) -> None:
        padding_mask = torch.tensor(
            [[True, True, True, True, True, True], [True, True, True, True, False, False]]
        )
        generator = torch.Generator().manual_seed(9)
        targets = make_contiguous_target_mask(
            padding_mask,
            target_fraction=0.5,
            generator=generator,
        )
        self.assertFalse(bool((targets & ~padding_mask).any()))
        self.assertEqual(targets.sum(dim=1).tolist(), [3, 2])
        for row in targets:
            indices = torch.nonzero(row, as_tuple=False).flatten().tolist()
            self.assertEqual(indices, list(range(indices[0], indices[-1] + 1)))
        self.assertTrue(bool((padding_mask & ~targets).any(dim=1).all()))

    def test_forward_ema_and_collapse_diagnostics(self) -> None:
        torch.manual_seed(3)
        batch = self._batch()
        model = TSJEPA(
            d_model=16,
            n_heads=4,
            num_layers=1,
            ff_multiplier=2,
            predictor_hidden=16,
            dropout=0.0,
            ema_momentum=0.5,
        )
        target_mask = torch.tensor(
            [[False, True, True, False, False], [False, True, False, False, False]]
        )
        output = model(batch.tokens, batch.padding_mask, target_mask=target_mask)
        self.assertTrue(math.isfinite(float(output["loss"].detach())))
        self.assertEqual(int(output["target_mask"].sum()), 3)
        self.assertEqual(tuple(output["predictions"].shape), (2, 5, 16))
        self.assertTrue(
            all(not parameter.requires_grad for parameter in model.target_encoder.parameters())
        )

        context_parameter = next(model.context_encoder.parameters())
        target_parameter = next(model.target_encoder.parameters())
        before = target_parameter.detach().clone()
        with torch.no_grad():
            context_parameter.add_(0.2)
        model.update_target_encoder()
        self.assertTrue(torch.allclose(target_parameter, before + 0.1, atol=1e-6))

        collapsed = representation_diagnostics(torch.ones(8, 4))
        self.assertTrue(collapsed["is_collapsed"])
        varied = representation_diagnostics(torch.eye(4).repeat(3, 1), collapse_threshold=0.01)
        self.assertFalse(varied["is_collapsed"])
        # Centered one-hot vectors span d-1 dimensions because their components
        # sum to one.
        self.assertAlmostEqual(varied["effective_rank"], 3.0, places=5)
        self.assertAlmostEqual(varied["effective_rank_fraction"], 0.75, places=5)

        scalar = torch.arange(1.0, 9.0).unsqueeze(1)
        rank_one = representation_diagnostics(scalar * torch.tensor([[1.0, 2.0, 3.0, 4.0]]))
        self.assertFalse(rank_one["is_collapsed"])
        self.assertAlmostEqual(rank_one["effective_rank"], 1.0, places=4)
        self.assertLess(rank_one["effective_rank_fraction"], 0.3)

    def test_masked_prediction_does_not_leak_target_value_or_uncertainty(self) -> None:
        common = {
            "times": [1.0, 2.0, 4.0, 7.0, 11.0, 16.0],
            "bands": ["g", "r", "g", "r", "g", "r"],
            "detections": [True] * 6,
        }
        first = tokenize_light_curve(
            values=[1.0, 2.0, 3.0, 4.0, 7.0, 11.0],
            errors=[None, 0.2, 0.3, 0.4, 0.5, 0.6],
            **common,
        )
        changed_target = tokenize_light_curve(
            values=[1.0, 2.0, 30.0, -20.0, 7.0, 11.0],
            errors=[None, 0.2, 9.0, 12.0, 0.5, 0.6],
            **common,
        )
        first_batch = pad_light_curves([first])
        changed_batch = pad_light_curves([changed_target])
        target_mask = torch.tensor([[False, False, True, True, False, False]])
        torch.manual_seed(29)
        model = TSJEPA(
            d_model=8,
            n_heads=2,
            num_layers=1,
            ff_multiplier=2,
            predictor_hidden=8,
            dropout=0.0,
        ).eval()
        first_output = model(
            first_batch.tokens,
            first_batch.padding_mask,
            target_mask=target_mask,
        )
        changed_output = model(
            changed_batch.tokens,
            changed_batch.padding_mask,
            target_mask=target_mask,
        )
        self.assertTrue(
            torch.allclose(
                first_output["predictions"],
                changed_output["predictions"],
                atol=2e-5,
                rtol=2e-5,
            )
        )
        self.assertFalse(
            torch.allclose(
                first_output["targets"][target_mask],
                changed_output["targets"][target_mask],
            )
        )

    def test_missing_context_value_does_not_leak_masked_target_normalization(self) -> None:
        common = {
            "times": [1.0, 2.0, 3.0, 4.0, 5.0],
            "errors": [None, 0.1, 0.1, 0.1, 0.1],
            "bands": ["g"] * 5,
            "detections": [False, True, True, True, True],
        }
        first = tokenize_light_curve(values=[None, 1.0, 2.0, 3.0, 4.0], **common)
        changed_targets = tokenize_light_curve(
            values=[None, 1.0, 2.0, 30.0, 40.0],
            **common,
        )
        first_batch = pad_light_curves([first])
        changed_batch = pad_light_curves([changed_targets])
        target_mask = torch.tensor([[False, False, False, True, True]])

        torch.manual_seed(31)
        model = TSJEPA(
            d_model=8,
            n_heads=2,
            num_layers=1,
            ff_multiplier=2,
            predictor_hidden=8,
            dropout=0.0,
        ).eval()
        first_output = model(first_batch.tokens, first_batch.padding_mask, target_mask=target_mask)
        changed_output = model(
            changed_batch.tokens,
            changed_batch.padding_mask,
            target_mask=target_mask,
        )

        self.assertTrue(
            torch.allclose(
                first_output["predictions"],
                changed_output["predictions"],
                atol=2e-5,
                rtol=2e-5,
            )
        )
        self.assertFalse(
            torch.allclose(
                first_output["targets"][target_mask],
                changed_output["targets"][target_mask],
            )
        )

    def test_small_context_scale_does_not_leak_masked_target_normalization(self) -> None:
        common = {
            "times": [1.0, 2.0],
            "errors": [0.1, 0.1],
            "bands": ["g", "g"],
            "detections": [True, True],
        }
        first = pad_light_curves([tokenize_light_curve(values=[0.0, 1.0e5], **common)])
        changed = pad_light_curves([tokenize_light_curve(values=[0.0, 1.0e6], **common)])
        target_mask = torch.tensor([[False, True]])
        torch.manual_seed(37)
        model = TSJEPA(
            d_model=8,
            n_heads=2,
            num_layers=1,
            ff_multiplier=2,
            predictor_hidden=8,
            dropout=0.0,
        ).eval()

        first_output = model(first.tokens, first.padding_mask, target_mask=target_mask)
        changed_output = model(changed.tokens, changed.padding_mask, target_mask=target_mask)
        self.assertTrue(
            torch.allclose(
                first_output["predictions"],
                changed_output["predictions"],
                atol=2e-5,
                rtol=2e-5,
            )
        )

    def test_encoder_rejects_internal_padding_and_invalid_tokens(self) -> None:
        batch = self._batch()
        model = TSJEPA(d_model=8, n_heads=2, num_layers=1, dropout=0.0)
        internal_padding = batch.padding_mask.clone()
        internal_padding[0, 1] = False
        with self.assertRaisesRegex(ValueError, "packed"):
            model.encode(batch.tokens, internal_padding)

        bad_band = batch.tokens.clone()
        bad_band[0, 0, BAND_INDEX] = 99
        with self.assertRaisesRegex(ValueError, "band IDs"):
            model.encode(bad_band, batch.padding_mask)

        nonneutral_missing = batch.tokens.clone()
        nonneutral_missing[0, 0, DETECTION_INDEX] = 0
        nonneutral_missing[0, 0, VALUE_PRESENT_INDEX] = 0
        nonneutral_missing[0, 0, VALUE_INDEX] = 1.0
        with self.assertRaisesRegex(ValueError, "neutral zero"):
            model.encode(nonneutral_missing, batch.padding_mask)

        huge_finite_deltas = batch.tokens.clone()
        huge_finite_deltas[:, 1:, DELTA_TIME_INDEX] = 3.0e38
        representations = model.encode(huge_finite_deltas, batch.padding_mask)
        self.assertTrue(bool(torch.isfinite(representations).all()))

        with self.assertRaisesRegex(ValueError, "boolean"):
            representation_diagnostics(torch.ones(2, 3), torch.ones(2))


@unittest.skipIf(torch is None, "PyTorch is an optional IRIS dependency")
class TrainingAndCheckpointTests(unittest.TestCase):
    @staticmethod
    def _dataset() -> LightCurveDataset:
        records = []
        for index in range(4):
            records.append(
                {
                    "object_id": f"object-{index}",
                    "times": [0.0, 0.5 + index * 0.1, 2.0, 4.5, 9.0],
                    "values": [1.0, 1.2 + index * 0.1, 1.8, 2.4, 2.0],
                    "errors": [0.1, 0.1, 0.15, 0.2, 0.15],
                    "bands": ["g", "r", "g", "i", "r"],
                    "detections": [True] * 5,
                }
            )
        return LightCurveDataset(records)

    def test_numeric_configuration_rejects_booleans_and_negative_seed(self) -> None:
        for keyword in ("learning_rate", "weight_decay", "target_fraction", "ema_momentum"):
            with self.subTest(keyword=keyword), self.assertRaises(ValueError):
                TrainingConfig(**{keyword: True})
        with self.assertRaisesRegex(ValueError, "seed"):
            TrainingConfig(seed=-1)
        with self.assertRaises(ValueError):
            TSJEPA(d_model=8, n_heads=2, num_layers=1, dropout=False)
        with self.assertRaises(ValueError):
            TSJEPA(d_model=8, n_heads=2, num_layers=1, ema_momentum=False)

    def test_train_evaluate_embeddings_and_checkpoint_round_trip(self) -> None:
        torch.manual_seed(11)
        dataset = self._dataset()
        model = TSJEPA(
            d_model=8,
            n_heads=2,
            num_layers=1,
            ff_multiplier=2,
            predictor_hidden=8,
            dropout=0.0,
            ema_momentum=0.9,
        )
        history = train_jepa(
            model,
            dataset,
            TrainingConfig(
                epochs=1,
                batch_size=4,
                learning_rate=1e-3,
                target_fraction=0.4,
                shuffle=False,
                device="cpu",
            ),
        )
        self.assertEqual(history["total_steps"], 1)
        self.assertTrue(math.isfinite(history["epochs"][0]["loss"]))
        self.assertEqual(
            history["epochs"][0]["target_representation_diagnostics"]["num_vectors"],
            history["epochs"][0]["target_tokens"],
        )
        self.assertEqual(
            history["epochs"][0]["representation_diagnostic_scope"],
            "all_target_tokens_in_epoch",
        )
        self.assertTrue(history["epochs"][0]["collapsed_step_fraction_is_batch_dependent"])

        metrics = evaluate_jepa(model, dataset, batch_size=4, target_fraction=0.4)
        self.assertGreater(metrics["target_tokens"], 0)
        self.assertTrue(math.isfinite(metrics["loss"]))
        self.assertEqual(metrics["mask_repeats"], 5)
        self.assertEqual(len(metrics["repeat_losses"]), 5)
        self.assertGreaterEqual(metrics["loss_ci95_half_width"], 0.0)
        self.assertEqual(metrics["loss_ci95_method"], "student_t_over_mask_repeats")
        self.assertEqual(
            metrics["target_representation_diagnostics"]["num_vectors"],
            metrics["target_tokens"],
        )

        differently_batched = evaluate_jepa(
            model,
            dataset,
            batch_size=1,
            target_fraction=0.4,
            seed=101,
            mask_repeats=5,
        )
        self.assertAlmostEqual(
            metrics["mean_target_feature_std"],
            differently_batched["mean_target_feature_std"],
            places=6,
        )
        self.assertAlmostEqual(
            metrics["target_representation_diagnostics"]["effective_rank"],
            differently_batched["target_representation_diagnostics"]["effective_rank"],
            places=5,
        )

        shuffled_loader = torch.utils.data.DataLoader(
            dataset,
            batch_size=2,
            shuffle=True,
            collate_fn=collate_light_curves,
        )
        with self.assertRaisesRegex(ValueError, "non-random row ordering"):
            evaluate_jepa(model, shuffled_loader)

        extracted = extract_embeddings(model, dataset, batch_size=2)
        self.assertEqual(tuple(extracted["embeddings"].shape), (4, 8))
        self.assertEqual(extracted["object_ids"], tuple(f"object-{index}" for index in range(4)))

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "small-jepa.pt"
            metadata = save_checkpoint(
                path,
                model,
                training_state={"epoch": 1},
                metadata={"campaign": "unit-test", "data_snapshot": "synthetic-v1"},
            )
            self.assertEqual(metadata["user_metadata"]["campaign"], "unit-test")
            with self.assertRaises(FileExistsError):
                save_checkpoint(path, model)
            restored, payload = load_checkpoint(path)
            self.assertEqual(restored.get_config(), model.get_config())
            self.assertTrue(restored.token_contract_bound)
            self.assertEqual(restored.token_contract_sha256, model.token_contract_sha256)
            self.assertEqual(payload["training_state"]["epoch"], 1)
            for expected, actual in zip(model.parameters(), restored.parameters(), strict=True):
                self.assertTrue(torch.equal(expected, actual))

            mismatched_model = TSJEPA(
                d_model=16,
                n_heads=4,
                num_layers=1,
                ff_multiplier=2,
                predictor_hidden=16,
                dropout=0.0,
            )
            with self.assertRaisesRegex(ValueError, "config does not match"):
                load_checkpoint(path, model=mismatched_model)

            incompatible_path = Path(temporary_directory) / "future-jepa.pt"
            incompatible_payload = torch.load(path, weights_only=True)
            incompatible_payload["metadata"]["format_version"] = 999
            torch.save(incompatible_payload, incompatible_path)
            with self.assertRaisesRegex(ValueError, "format version"):
                load_checkpoint(incompatible_path)

            with self.assertRaisesRegex(ValueError, "JSON-compatible"):
                save_checkpoint(
                    Path(temporary_directory) / "unsafe-metadata.pt",
                    model,
                    metadata={"unsupported": object()},
                )

    def test_checkpoint_loader_never_falls_back_to_unrestricted_pickle(self) -> None:
        with (
            patch(
                "iris.ml.train.torch.load",
                side_effect=TypeError("weights_only unsupported"),
            ) as mocked_load,
            self.assertRaisesRegex(TypeError, "weights_only"),
        ):
            load_checkpoint("untrusted.pt")

        mocked_load.assert_called_once()
        self.assertIs(mocked_load.call_args.kwargs["weights_only"], True)

    def test_training_cannot_mix_contracts_across_separate_batches(self) -> None:
        items = [
            tokenize_light_curve(
                [1.0, 2.0],
                [1.0, 2.0],
                [0.1, 0.1],
                ["g", "g"],
                [True, True],
                value_kind="flux",
            ),
            tokenize_light_curve(
                [3.0, 4.0],
                [20.0, 19.0],
                [0.1, 0.1],
                ["g", "g"],
                [True, True],
                value_kind="magnitude",
            ),
        ]
        model = TSJEPA(d_model=8, n_heads=2, num_layers=1, dropout=0.0)

        with self.assertRaisesRegex(ValueError, "training cannot mix"):
            train_jepa(
                model,
                items,
                TrainingConfig(epochs=1, batch_size=1, shuffle=False),
            )

    def test_trained_model_rejects_evaluation_under_a_different_contract(self) -> None:
        flux = tokenize_light_curve([1.0, 2.0], [1.0, 2.0], [0.1, 0.1], ["g", "g"], [True, True])
        magnitude = tokenize_light_curve(
            [1.0, 2.0],
            [20.0, 19.0],
            [0.1, 0.1],
            ["g", "g"],
            [True, True],
            value_kind="magnitude",
        )
        model = TSJEPA(d_model=8, n_heads=2, num_layers=1, dropout=0.0)
        train_jepa(
            model,
            [flux],
            TrainingConfig(epochs=1, batch_size=1, shuffle=False),
        )

        with self.assertRaisesRegex(ValueError, "different tokenization contract"):
            evaluate_jepa(model, [magnitude], batch_size=1, mask_repeats=2)

    def test_cli_rejects_different_train_and_validation_token_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config = root / "iris.toml"
            config.write_text(
                """
[general]
campaign = "jepa_research"
[storage]
root = "state"
[jepa]
enabled = true
shadow_mode = true
embedding_dim = 8
encoder_layers = 1
attention_heads = 2
batch_size = 1
""".strip()
                + "\n",
                encoding="utf-8",
            )
            train_path = root / "train.jsonl"
            validation_path = root / "validation.jsonl"
            train_path.write_text(
                json.dumps(
                    {
                        "object_id": "train-object",
                        "times": [1.0, 2.0],
                        "values": [1.0, 2.0],
                        "errors": [0.1, 0.1],
                        "bands": ["g", "g"],
                        "detections": [True, True],
                        "value_kind": "flux",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            validation_path.write_text(
                json.dumps(
                    {
                        "object_id": "validation-object",
                        "times": [3.0, 4.0],
                        "values": [20.0, 19.0],
                        "errors": [0.1, 0.1],
                        "bands": ["g", "g"],
                        "detections": [True, True],
                        "value_kind": "magnitude",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = iris_main(
                    [
                        "jepa-train",
                        str(train_path),
                        str(validation_path),
                        str(root / "bundle"),
                        "--config",
                        str(config),
                    ]
                )

            self.assertEqual(code, 2)
            self.assertIn("token contracts differ", stderr.getvalue())
            self.assertFalse((root / "bundle").exists())


if __name__ == "__main__":
    unittest.main()
