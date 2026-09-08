from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from siderea.config import (
    ConfigError,
    GeneralConfig,
    HuntConfig,
    JEPAConfig,
    NetworkConfig,
    RankingConfig,
    ReviewConfig,
    ValidationConfig,
    config_to_dict,
    load_config,
)
from siderea.domain import (
    Candidate,
    CandidateState,
    CheckStatus,
    Evidence,
    EvidenceKind,
    Observation,
)
from siderea.state import (
    ReportabilityError,
    TransitionError,
    assess_reportability,
    transition_candidate,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_default_identity_is_siderea_novel_transients(self) -> None:
        config = load_config(PROJECT_ROOT / "configs" / "default.toml")

        self.assertEqual(config.general.name, "SIDEREA")
        self.assertEqual(config.general.campaign, "novel_transients")

    def test_all_repository_configs_load(self) -> None:
        for path in sorted((PROJECT_ROOT / "configs").glob("*.toml")):
            with self.subTest(path=path.name):
                config = load_config(path)
                self.assertEqual(config.general.name, "SIDEREA")
                self.assertTrue(config.validation.fail_closed)
                self.assertTrue(config.review.require_human_approval)
                self.assertTrue(config.storage.root.is_absolute())

    def test_default_config_is_typed_and_json_friendly(self) -> None:
        config = load_config(PROJECT_ROOT / "configs" / "default.toml")
        self.assertEqual(config.hunt.object_limit, 350)
        self.assertEqual(config.validation.required_checks, ("skybot", "tns", "simbad", "vsx"))
        self.assertEqual(config.jepa.embedding_dim, 256)
        rendered = config_to_dict(config)
        self.assertIsInstance(rendered["storage"]["root"], str)
        self.assertEqual(rendered["hunt"]["broker_classes"][0], "SN")

    def test_unknown_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.toml"
            path.write_text("[validation]\nfail_clsoed = true\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "unknown validation key"):
                load_config(path)

    def test_unknown_config_schema_and_unimplemented_broker_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            future = root / "future.toml"
            future.write_text("[general]\nschema_version = 2\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "must be 1"):
                load_config(future)

            broker = root / "broker.toml"
            broker.write_text("[hunt]\nbroker = 'other'\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "another adapter"):
                load_config(broker)

    def test_fail_open_configuration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe.toml"
            path.write_text("[validation]\nfail_closed = false\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "must remain true"):
                load_config(path)

    def test_self_approval_configuration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe-review.toml"
            path.write_text("[review]\nallow_self_approval = true\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "must remain false"):
                load_config(path)

    def test_invalid_jepa_dimensions_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-jepa.toml"
            path.write_text(
                "[jepa]\nembedding_dim = 250\nattention_heads = 8\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "must be divisible"):
                load_config(path)

    def test_jepa_cannot_claim_non_shadow_operation_before_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe-jepa.toml"
            path.write_text("[jepa]\nshadow_mode = false\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "must remain true"):
                load_config(path)

    def test_non_finite_scientific_thresholds_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "non-finite.toml"
            path.write_text(
                "[network]\ntimeout_seconds = inf\n[jepa]\nmask_fraction = nan\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "finite"):
                load_config(path)

    def test_direct_config_construction_rejects_boolean_numeric_aliases(self) -> None:
        unsafe_constructors = (
            lambda: GeneralConfig(schema_version=True),
            lambda: HuntConfig(object_limit=True),
            lambda: ValidationConfig(evidence_ttl_hours=True),
            lambda: ValidationConfig(fail_closed=1),  # type: ignore[arg-type]
            lambda: NetworkConfig(max_retries=True),
            lambda: ReviewConfig(nightly_budget=True),
            lambda: ReviewConfig(require_human_approval=1),  # type: ignore[arg-type]
            lambda: RankingConfig(amplitude_weight=True),
            lambda: JEPAConfig(enabled=1),  # type: ignore[arg-type]
            lambda: JEPAConfig(encoder_layers=True),
            lambda: JEPAConfig(mask_fraction=True),
            lambda: JEPAConfig(seed=True),
        )
        for construct in unsafe_constructors:
            with self.subTest(construct=construct), self.assertRaises(ConfigError):
                construct()


class DomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

    def candidate(self) -> Candidate:
        return Candidate(
            candidate_id="ZTF26example",
            ra_deg=123.4,
            dec_deg=-22.5,
            origin="alerce",
            created_at=self.now,
            updated_at=self.now,
        )

    def evidence(
        self,
        name: str,
        status: CheckStatus,
        *,
        age_hours: float = 0,
        ttl_hours: float = 24,
    ) -> Evidence:
        checked_at = self.now - timedelta(hours=age_hours)
        return Evidence(
            check_name=name,
            kind=EvidenceKind.CATALOG,
            status=status,
            source=f"{name}-client",
            checked_at=checked_at,
            expires_at=checked_at + timedelta(hours=ttl_hours),
        )

    def test_observation_supports_detection_and_upper_limit(self) -> None:
        detection = Observation(
            mjd=61289.25,
            band=" r ",
            detected=True,
            magnitude=19.1,
            magnitude_error=0.08,
            survey="ZTF",
        )
        upper_limit = Observation(
            mjd=61288.25,
            band="r",
            detected=False,
            limiting_magnitude=20.5,
            survey="ZTF",
        )
        self.assertEqual(detection.band, "r")
        self.assertFalse(upper_limit.detected)

    def test_observation_requires_measurement_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "detection requires"):
            Observation(mjd=61289.25, band="g", detected=True)
        with self.assertRaisesRegex(ValueError, "non-detection requires"):
            Observation(mjd=61289.25, band="g", detected=False)
        with self.assertRaisesRegex(ValueError, "must be positive"):
            Observation(
                mjd=61289.25,
                band="g",
                detected=True,
                flux=1.0,
                flux_error=0.0,
            )

    def test_candidate_validates_coordinates(self) -> None:
        with self.assertRaisesRegex(ValueError, "ra_deg"):
            Candidate(candidate_id="bad", ra_deg=360.0, dec_deg=0.0)
        with self.assertRaisesRegex(ValueError, "dec_deg"):
            Candidate(candidate_id="bad", ra_deg=0.0, dec_deg=-91.0)

    def test_latest_evidence_wins_without_erasing_history(self) -> None:
        candidate = self.candidate()
        first = self.evidence("tns", CheckStatus.UNAVAILABLE, age_hours=2)
        second = self.evidence("TNS", CheckStatus.PASS, age_hours=1)
        candidate = candidate.record_evidence(first, at=self.now)
        candidate = candidate.record_evidence(second, at=self.now)
        self.assertEqual(len(candidate.evidence), 2)
        self.assertIs(candidate.latest_evidence("tns"), second)

    def test_reportability_is_explicit_and_fail_closed(self) -> None:
        candidate = self.candidate()
        candidate = candidate.record_evidence(self.evidence("tns", CheckStatus.PASS), at=self.now)
        candidate = candidate.record_evidence(
            self.evidence("skybot", CheckStatus.UNAVAILABLE), at=self.now
        )
        assessment = assess_reportability(candidate, ("tns", "skybot", "simbad"), at=self.now)
        self.assertFalse(assessment.reportable)
        self.assertEqual(assessment.missing_checks, ("simbad",))
        self.assertEqual(assessment.non_passing_checks, ("skybot=unavailable",))

    def test_stale_pass_does_not_open_gate(self) -> None:
        candidate = self.candidate().record_evidence(
            self.evidence("tns", CheckStatus.PASS, age_hours=25, ttl_hours=24),
            at=self.now,
        )
        assessment = assess_reportability(candidate, ("tns",), at=self.now)
        self.assertFalse(assessment.reportable)
        self.assertEqual(assessment.stale_checks, ("tns",))

    def test_pass_without_expiration_does_not_open_gate(self) -> None:
        evidence = Evidence(
            check_name="tns",
            kind=EvidenceKind.CATALOG,
            status=CheckStatus.PASS,
            source="tns-client",
            checked_at=self.now,
        )
        self.assertFalse(evidence.is_fresh(self.now))
        candidate = self.candidate().record_evidence(evidence, at=self.now)
        assessment = assess_reportability(candidate, ("tns",), at=self.now)
        self.assertFalse(assessment.reportable)
        self.assertEqual(assessment.stale_checks, ("tns",))

    def test_equal_time_conflicting_domain_evidence_is_order_invariant(self) -> None:
        passing = self.evidence("tns", CheckStatus.PASS)
        error = Evidence(
            check_name="tns",
            kind=EvidenceKind.CATALOG,
            status=CheckStatus.ERROR,
            source="tns-client",
            checked_at=passing.checked_at,
            expires_at=passing.expires_at,
        )
        first = self.candidate().record_evidence(passing, at=self.now)
        first = first.record_evidence(error, at=self.now)
        second = self.candidate().record_evidence(error, at=self.now)
        second = second.record_evidence(passing, at=self.now)

        first_assessment = assess_reportability(first, ("tns",), at=self.now)
        second_assessment = assess_reportability(second, ("tns",), at=self.now)

        self.assertEqual(first_assessment, second_assessment)
        self.assertFalse(first_assessment.reportable)
        self.assertEqual(
            first_assessment.non_passing_checks,
            ("tns=conflicting_latest_evidence",),
        )

    def test_candidate_state_machine_rejects_shortcuts(self) -> None:
        candidate = self.candidate()
        enriching = transition_candidate(candidate, CandidateState.ENRICHING, at=self.now)
        self.assertEqual(enriching.state, CandidateState.ENRICHING)
        with self.assertRaises(TransitionError):
            transition_candidate(enriching, CandidateState.REPORTED, at=self.now)

    def test_reportable_transition_requires_fresh_named_evidence(self) -> None:
        screening = Candidate(
            candidate_id="ZTF-state",
            ra_deg=10.0,
            dec_deg=20.0,
            state=CandidateState.SCREENING,
            created_at=self.now,
            updated_at=self.now,
        )
        with self.assertRaisesRegex(ReportabilityError, "required_checks"):
            transition_candidate(screening, CandidateState.REPORTABLE, at=self.now)

        passing = screening.record_evidence(self.evidence("tns", CheckStatus.PASS), at=self.now)
        reportable = transition_candidate(
            passing,
            CandidateState.REPORTABLE,
            at=self.now,
            required_checks=("tns",),
        )
        with self.assertRaisesRegex(ReportabilityError, "independent approval"):
            transition_candidate(reportable, CandidateState.APPROVED, at=self.now)
        approved = transition_candidate(
            reportable,
            CandidateState.APPROVED,
            at=self.now,
            approval_recorded=True,
        )
        with self.assertRaisesRegex(ReportabilityError, "reporting preflight"):
            transition_candidate(approved, CandidateState.REPORTED, at=self.now)


if __name__ == "__main__":
    unittest.main()
