from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from siderea.provenance import CheckProvenance, CheckStatus, digest_value
from siderea.validation import EvidenceBindingContext, bind_completed_check


class EvidenceBindingTests(unittest.TestCase):
    def context(self) -> EvidenceBindingContext:
        return EvidenceBindingContext(
            candidate_id="ZTF26bound",
            ra_deg=12.3,
            dec_deg=-4.5,
            max_ttl_hours=12.0,
            required_radii_arcsec={
                "tns": 5.0,
                "skybot": 10.0,
                "simbad": 3.0,
                "vsx": 3.0,
            },
            skybot_reference_mjds=(61000.0,),
        )

    def check(
        self,
        service: str,
        *,
        status: CheckStatus = CheckStatus.CLEAR,
        query: dict[str, object] | None = None,
        ttl_hours: float = 12.0,
        service_version: str = "",
    ) -> CheckProvenance:
        checked = datetime.now(UTC)
        return CheckProvenance(
            service=service,
            status=status,
            checked_at=checked.isoformat(),
            expires_at=(checked + timedelta(hours=ttl_hours)).isoformat(),
            query=query or {},
            response_digest=digest_value({"service": service, "query": query or {}}),
            service_version=service_version,
        )

    def test_clear_without_a_successful_response_digest_is_rejected(self) -> None:
        checked = datetime.now(UTC)
        unauditable = CheckProvenance(
            service="simbad",
            status=CheckStatus.CLEAR,
            checked_at=checked.isoformat(),
            expires_at=(checked + timedelta(hours=1)).isoformat(),
            query={"ra": 12.3, "dec": -4.5, "radius_arcsec": 3.0},
            attempts=0,
        )

        result = bind_completed_check(unauditable, self.context())

        self.assertEqual(result.status, CheckStatus.ERROR)
        self.assertIn("successful service attempt", result.error)

    def test_tns_clear_requires_candidate_identity(self) -> None:
        result = bind_completed_check(
            self.check(
                "tns",
                query={
                    "methods": ["internal_name", "cone"],
                    "coverage_policy": "internal_name_and_position_cone",
                    "ra": 12.3,
                    "dec": -4.5,
                    "radius_arcsec": 5.0,
                },
                service_version="tns-two-stage-search.v1",
            ),
            self.context(),
        )

        self.assertEqual(result.status, CheckStatus.ERROR)
        self.assertIn("identity", result.error)

    def test_tns_clear_requires_the_two_stage_producer_contract(self) -> None:
        result = bind_completed_check(
            self.check(
                "tns",
                query={
                    "oid": "ZTF26bound",
                    "RA": 12.3,
                    "DEC": -4.5,
                    "radius": 5.0 / 60.0,
                    "units": "arcmin",
                },
            ),
            self.context(),
        )

        self.assertEqual(result.status, CheckStatus.ERROR)
        self.assertIn("service_version", result.error)

        query = {
            "methods": ["internal_name", "cone"],
            "coverage_policy": "internal_name_and_position_cone",
            "candidate_id": "ZTF26bound",
            "internal_name_checked": "ZTF26bound",
            "ra": 12.3,
            "dec": -4.5,
            "radius_arcsec": 5.0,
        }
        checked = datetime.now(UTC)
        valid = CheckProvenance(
            service="tns",
            status=CheckStatus.CLEAR,
            checked_at=checked.isoformat(),
            expires_at=(checked + timedelta(hours=12)).isoformat(),
            query=query,
            response_digest=digest_value(query),
            service_version="tns-two-stage-search.v1",
        )
        self.assertEqual(bind_completed_check(valid, self.context()).status, CheckStatus.CLEAR)

    def test_overlong_clear_ttl_is_stale(self) -> None:
        result = bind_completed_check(
            self.check(
                "simbad",
                ttl_hours=13.0,
                query={"ra": 12.3, "dec": -4.5, "radius_arcsec": 3.0},
            ),
            self.context(),
        )

        self.assertEqual(result.status, CheckStatus.STALE)
        self.assertIn("TTL exceeds", result.error)

    def test_positive_match_remains_a_conservative_veto(self) -> None:
        original = self.check("vsx", status=CheckStatus.MATCH)

        self.assertIs(bind_completed_check(original, self.context()), original)

    def test_skybot_clear_must_cover_every_reference_epoch(self) -> None:
        context = EvidenceBindingContext(
            candidate_id="ZTF26bound",
            ra_deg=12.3,
            dec_deg=-4.5,
            max_ttl_hours=12.0,
            required_radii_arcsec={"skybot": 10.0},
            skybot_reference_mjds=(61000.0, 61001.0),
        )
        incomplete = bind_completed_check(
            self.check(
                "skybot",
                query={
                    "ra": 12.3,
                    "dec": -4.5,
                    "radius_arcsec": 10.0,
                    "mjd": 61000.0,
                },
            ),
            context,
        )
        complete = bind_completed_check(
            self.check(
                "skybot",
                query={
                    "ra": 12.3,
                    "dec": -4.5,
                    "radius_arcsec": 10.0,
                    "mjds": [61000.0, 61001.0],
                },
            ),
            context,
        )

        self.assertEqual(incomplete.status, CheckStatus.ERROR)
        self.assertIn("uncovered", incomplete.error)
        self.assertEqual(complete.status, CheckStatus.CLEAR)


if __name__ == "__main__":
    unittest.main()
