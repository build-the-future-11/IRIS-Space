from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from typing import Any

from iris.clients.base import ServiceResult
from iris.provenance import CheckProvenance, CheckStatus, digest_value
from iris.validation import GateDecision, VerificationSuite
from iris.validation.catalog_policy import interpret_simbad


class _Catalog:
    def __init__(
        self,
        service: str,
        *,
        status: CheckStatus = CheckStatus.CLEAR,
        rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.service = service
        self.status = status
        self.rows = rows or []

    def check(self, **query: Any) -> ServiceResult[list[dict[str, object]]]:
        return ServiceResult(
            CheckProvenance(
                service=self.service,
                status=self.status,
                query=query,
                error="offline" if self.status is CheckStatus.ERROR else "",
                response_digest=(
                    digest_value(self.rows)
                    if self.status in {CheckStatus.CLEAR, CheckStatus.MATCH}
                    else ""
                ),
            ),
            self.rows,
        )


class _TNS:
    def __init__(self, status: CheckStatus = CheckStatus.CLEAR) -> None:
        self.status = status

    def search(self, **query: Any) -> ServiceResult[dict[str, object]]:
        candidate_id = str(query["internal_name"])
        provenance_query = {
            "methods": ["internal_name", "cone"],
            "coverage_policy": "internal_name_and_position_cone",
            "candidate_id": candidate_id,
            "internal_name_checked": candidate_id,
            "ra": query["ra"],
            "dec": query["dec"],
            "radius_arcsec": query["radius_arcsec"],
        }
        return ServiceResult(
            CheckProvenance(
                service="tns",
                status=self.status,
                query=provenance_query,
                error="offline" if self.status is CheckStatus.ERROR else "",
                response_digest=(
                    digest_value({})
                    if self.status in {CheckStatus.CLEAR, CheckStatus.MATCH}
                    else ""
                ),
                service_version="tns-two-stage-search.v1",
            ),
            {},
        )


class _WrongSkyBot(_Catalog):
    def check(self, **query: Any) -> ServiceResult[list[dict[str, object]]]:
        return ServiceResult(
            CheckProvenance(
                service="skybot",
                status=CheckStatus.CLEAR,
                query={**query, "ra": float(query["ra"]) + 1.0},
                response_digest=digest_value([]),
            ),
            [],
        )


class _MixedAgeSkyBot(_Catalog):
    def check(self, **query: Any) -> ServiceResult[list[dict[str, object]]]:
        now = datetime.now(UTC)
        checked = now - timedelta(days=2) if float(query["mjd"]) == 61000.0 else now
        return ServiceResult(
            CheckProvenance(
                service="skybot",
                status=CheckStatus.CLEAR,
                checked_at=checked.isoformat(),
                query=query,
                response_digest=digest_value([]),
            ),
            [],
        )


class VerificationSuiteTests(unittest.TestCase):
    def suite(
        self,
        *,
        tns: _TNS | None = None,
        simbad_rows: list[dict[str, object]] | None = None,
        skybot: _Catalog | None = None,
    ) -> VerificationSuite:
        return VerificationSuite(
            skybot=skybot or _Catalog("skybot"),
            simbad=_Catalog("simbad", rows=simbad_rows),
            vsx=_Catalog("vsx"),
            tns=tns,
            evidence_ttl_hours=12,
        )

    def test_complete_clear_evidence_is_reportable_and_time_bounded(self) -> None:
        result = self.suite(tns=_TNS()).verify(
            candidate_id="ZTF26safe",
            ra=12.3,
            dec=-4.5,
            peak_mjd=61000.0,
            quality_passed=True,
        )

        self.assertEqual(result.gate.decision, GateDecision.REPORTABLE)
        self.assertTrue(all(check.expires_at for check in result.checks))
        self.assertTrue(all(check.is_fresh() for check in result.checks))

    def test_nonfinite_evidence_ttl_is_rejected(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite"):
                VerificationSuite(evidence_ttl_hours=value)

    def test_skybot_check_covers_all_supplied_detection_epochs(self) -> None:
        result = self.suite(tns=_TNS()).verify(
            candidate_id="ZTF26epochs",
            ra=12.3,
            dec=-4.5,
            peak_mjd=61000.0,
            reference_mjds=(61001.0, 61002.0),
            quality_passed=True,
        )
        skybot = next(check for check in result.checks if check.service == "skybot")

        self.assertEqual(skybot.query["mjds"], [61000.0, 61001.0, 61002.0])
        self.assertEqual(skybot.attempts, 3)
        self.assertEqual(result.gate.decision, GateDecision.REPORTABLE)

    def test_one_stale_skybot_epoch_cannot_be_refreshed_by_a_newer_epoch(self) -> None:
        result = self.suite(tns=_TNS(), skybot=_MixedAgeSkyBot("skybot")).verify(
            candidate_id="ZTF26mixed-age",
            ra=12.3,
            dec=-4.5,
            peak_mjd=61000.0,
            reference_mjds=(61001.0,),
            quality_passed=True,
        )
        skybot = next(check for check in result.checks if check.service == "skybot")

        self.assertEqual(skybot.status, CheckStatus.STALE)
        self.assertEqual(result.gate.decision, GateDecision.BLOCK_INCOMPLETE_EVIDENCE)

    def test_missing_tns_credentials_fail_closed(self) -> None:
        result = self.suite().verify(
            candidate_id="ZTF26blocked",
            ra=12.3,
            dec=-4.5,
            peak_mjd=61000.0,
            quality_passed=True,
        )

        self.assertEqual(result.gate.decision, GateDecision.BLOCK_INCOMPLETE_EVIDENCE)
        tns = next(check for check in result.checks if check.service == "tns")
        self.assertEqual(tns.status, CheckStatus.DISABLED)

    def test_gate_uses_the_explicit_required_service_policy(self) -> None:
        result = self.suite().verify(
            candidate_id="ZTF26stellar",
            ra=12.3,
            dec=-4.5,
            peak_mjd=61000.0,
            quality_passed=True,
            mandatory_services=("skybot", "simbad", "vsx"),
        )

        self.assertEqual(result.gate.decision, GateDecision.REPORTABLE)

    def test_misbehaving_client_cannot_clear_a_different_position(self) -> None:
        result = self.suite(tns=_TNS(), skybot=_WrongSkyBot("skybot")).verify(
            candidate_id="ZTF26bound",
            ra=12.3,
            dec=-4.5,
            peak_mjd=61000.0,
            quality_passed=True,
        )

        self.assertEqual(result.gate.decision, GateDecision.BLOCK_INCOMPLETE_EVIDENCE)
        skybot = next(check for check in result.checks if check.service == "skybot")
        self.assertEqual(skybot.status, CheckStatus.ERROR)
        self.assertIn("evidence binding failed", skybot.error)

    def test_galaxy_counterpart_requires_manual_adjudication(self) -> None:
        result = self.suite(
            tns=_TNS(),
            simbad_rows=[{"MAIN_ID": "NGC 123", "OTYPE": "Galaxy"}],
        ).verify(
            candidate_id="ZTF26host",
            ra=12.3,
            dec=-4.5,
            peak_mjd=61000.0,
            quality_passed=True,
        )

        self.assertEqual(result.gate.decision, GateDecision.NEEDS_MANUAL_REVIEW)
        self.assertIn("NGC 123", result.context["simbad"][0])

    def test_single_letter_g_matching_does_not_misclassify_unknown_type(self) -> None:
        raw = _Catalog(
            "simbad",
            status=CheckStatus.MATCH,
            rows=[{"MAIN_ID": "mystery", "OTYPE": "gamma source"}],
        ).check()
        interpretation = interpret_simbad(raw)
        self.assertEqual(interpretation.check.status, CheckStatus.CLEAR)
        self.assertTrue(interpretation.manual_review_required)
        self.assertIn("unknown", interpretation.reason)


if __name__ == "__main__":
    unittest.main()
