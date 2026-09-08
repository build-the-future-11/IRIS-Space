"""Coordinated, provenance-rich external validation for one candidate."""

from __future__ import annotations

import hmac
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from siderea.clients.base import ServiceResult
from siderea.clients.catalogs import SimbadClient, SkyBotClient, VSXClient
from siderea.clients.tns import TNSClient
from siderea.evidence_context import canonical_verification_context
from siderea.provenance import CheckProvenance, CheckStatus, digest_value

from .binding import EvidenceBindingContext, bind_completed_checks
from .catalog_policy import CatalogInterpretation, interpret_simbad
from .gates import MANDATORY_SERVICES, GateOutcome, evaluate_reportability


@dataclass(frozen=True)
class VerificationBundle:
    checks: tuple[CheckProvenance, ...]
    gate: GateOutcome
    manual_review_required: bool
    context: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        canonical = canonical_verification_context(
            self.context,
            manual_review_required=self.manual_review_required,
        )
        if self.manual_review_required:
            simbad = tuple(check for check in self.checks if check.service == "simbad")
            if len(simbad) != 1 or simbad[0].status is not CheckStatus.CLEAR:
                raise ValueError(
                    "SIMBAD manual review requires one clear SIMBAD check and context labels"
                )
        object.__setattr__(self, "context", canonical)


class VerificationSuite:
    def __init__(
        self,
        *,
        skybot: SkyBotClient | None = None,
        simbad: SimbadClient | None = None,
        vsx: VSXClient | None = None,
        tns: TNSClient | None = None,
        evidence_ttl_hours: float = 24.0,
    ) -> None:
        if isinstance(evidence_ttl_hours, bool) or not isinstance(evidence_ttl_hours, (int, float)):
            raise TypeError("evidence_ttl_hours must be a number")
        if not math.isfinite(evidence_ttl_hours) or evidence_ttl_hours <= 0:
            raise ValueError("evidence_ttl_hours must be finite and positive")
        self.skybot = skybot if skybot is not None else SkyBotClient()
        self.simbad = simbad if simbad is not None else SimbadClient()
        self.vsx = vsx if vsx is not None else VSXClient()
        self.tns = tns
        self.evidence_ttl_hours = evidence_ttl_hours

    @staticmethod
    def _catalog_check(
        result: ServiceResult[Any],
        *,
        expected_service: str,
    ) -> CheckProvenance:
        """Fail a claimed catalogue clearance whose records do not match its digest."""

        check = result.provenance
        if check.status is not CheckStatus.CLEAR:
            # Positive matches remain conservative vetoes even if a faulty
            # adapter supplied incomplete provenance.
            return check
        if check.service != expected_service:
            return replace(
                check,
                status=CheckStatus.ERROR,
                matches=(),
                error=f"catalogue result is not identified as {expected_service}",
            )
        try:
            actual_digest = digest_value(result.value)
        except (TypeError, ValueError) as exc:
            return replace(
                check,
                status=CheckStatus.ERROR,
                matches=(),
                error=f"catalogue response is not canonical JSON: {exc}",
            )
        if not hmac.compare_digest(check.response_digest, actual_digest):
            return replace(
                check,
                status=CheckStatus.ERROR,
                matches=(),
                error="catalogue response digest does not match its records",
            )
        return check

    def _fresh(self, check: CheckProvenance) -> CheckProvenance:
        checked = datetime.fromisoformat(check.checked_at)
        policy_expiry = checked + timedelta(hours=self.evidence_ttl_hours)
        expiry = policy_expiry
        if check.expires_at:
            supplied_expiry = datetime.fromisoformat(check.expires_at)
            expiry = min(policy_expiry, supplied_expiry)
        return replace(check, expires_at=expiry.isoformat())

    def _check_skybot_epochs(
        self,
        *,
        candidate_id: str,
        ra: float,
        dec: float,
        mjds: tuple[float, ...],
        radius_arcsec: float,
        evaluated_at: datetime,
    ) -> CheckProvenance:
        raw_results = tuple(
            self._catalog_check(
                self.skybot.check(
                    ra=ra,
                    dec=dec,
                    mjd=mjd,
                    radius_arcsec=radius_arcsec,
                ),
                expected_service="skybot",
            )
            for mjd in mjds
        )
        results = tuple(
            bind_completed_checks(
                (self._fresh(check),),
                EvidenceBindingContext(
                    candidate_id=candidate_id,
                    ra_deg=ra,
                    dec_deg=dec,
                    max_ttl_hours=self.evidence_ttl_hours,
                    required_radii_arcsec={"skybot": radius_arcsec},
                    skybot_reference_mjds=(mjd,),
                ),
            )[0]
            for check, mjd in zip(raw_results, mjds, strict=True)
        )
        results = tuple(
            replace(
                check,
                status=CheckStatus.STALE,
                error="SkyBoT component evidence is expired or future-dated",
                response_digest="",
            )
            if check.status is CheckStatus.CLEAR and not check.is_fresh(now=evaluated_at)
            else check
            for check in results
        )
        invalid_clear = next(
            (
                check.clear_integrity_error
                for check in results
                if check.status is CheckStatus.CLEAR and check.clear_integrity_error is not None
            ),
            None,
        )
        precedence = (
            CheckStatus.MATCH,
            CheckStatus.ERROR,
            CheckStatus.DISABLED,
            CheckStatus.STALE,
            CheckStatus.PENDING,
            CheckStatus.CLEAR,
        )
        status = next(
            state for state in precedence if any(check.status is state for check in results)
        )
        if invalid_clear is not None and status is not CheckStatus.MATCH:
            status = CheckStatus.ERROR
        matches = tuple(dict.fromkeys(name for check in results for name in check.matches if name))
        errors = [check.error for check in results if check.error]
        if invalid_clear is not None:
            errors.append(invalid_clear)
        latencies = [check.latency_ms for check in results if check.latency_ms is not None]
        checked_at = max(
            results,
            key=lambda check: datetime.fromisoformat(check.checked_at),
        ).checked_at
        clear_expiries = [
            datetime.fromisoformat(check.expires_at)
            for check in results
            if check.status is CheckStatus.CLEAR and check.expires_at
        ]
        aggregate_expiry = min(clear_expiries).isoformat() if clear_expiries else ""
        return CheckProvenance(
            service="skybot",
            status=status,
            checked_at=checked_at,
            expires_at=aggregate_expiry,
            query={
                "ra": ra,
                "dec": dec,
                "mjds": list(mjds),
                "radius_arcsec": radius_arcsec,
                "coverage_policy": "all_distinct_detection_epochs",
            },
            matches=matches,
            error="; ".join(dict.fromkeys(errors)),
            attempts=sum(check.attempts for check in results),
            latency_ms=sum(latencies) if latencies else None,
            response_digest=(
                digest_value([check.to_dict() for check in results])
                if status in {CheckStatus.CLEAR, CheckStatus.MATCH}
                else ""
            ),
            service_version=next(
                (check.service_version for check in results if check.service_version), ""
            ),
        )

    def verify(
        self,
        *,
        candidate_id: str,
        ra: float,
        dec: float,
        peak_mjd: float,
        quality_passed: bool,
        reference_mjds: Iterable[float] | None = None,
        mandatory_services: Iterable[str] = MANDATORY_SERVICES,
        skybot_radius_arcsec: float = 10.0,
        tns_radius_arcsec: float = 3.0,
        catalog_radius_arcsec: float = 3.0,
    ) -> VerificationBundle:
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise ValueError("candidate_id must be a non-empty string")
        candidate_id = candidate_id.strip()
        if not isinstance(quality_passed, bool):
            raise TypeError("quality_passed must be boolean")
        required_values = tuple(mandatory_services)
        if any(not isinstance(service, str) for service in required_values):
            raise TypeError("mandatory service names must be strings")
        required = tuple(
            dict.fromkeys(
                service.strip().casefold() for service in required_values if service.strip()
            )
        )
        unsupported = set(required) - set(MANDATORY_SERVICES)
        if not required or unsupported:
            raise ValueError(
                "mandatory_services must be a non-empty subset of " + ", ".join(MANDATORY_SERVICES)
            )
        for name, value in (("ra", ra), ("dec", dec), ("peak_mjd", peak_mjd)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
        if not math.isfinite(ra) or not 0 <= ra < 360:
            raise ValueError("ra must be within [0, 360)")
        if not math.isfinite(dec) or not -90 <= dec <= 90:
            raise ValueError("dec must be within [-90, 90]")
        if not math.isfinite(peak_mjd) or peak_mjd < 0:
            raise ValueError("peak_mjd must be finite and non-negative")
        references = {float(peak_mjd)}
        if isinstance(reference_mjds, (str, bytes, Mapping)):
            raise TypeError("reference_mjds must be an iterable of numbers")
        for value in reference_mjds or ():
            if isinstance(value, bool):
                raise ValueError("reference_mjds must be finite and non-negative")
            if not isinstance(value, (int, float)):
                raise TypeError("reference_mjds must contain numbers")
            number = float(value)
            if not math.isfinite(number) or number < 0:
                raise ValueError("reference_mjds must be finite and non-negative")
            references.add(number)
        ordered_references = tuple(sorted(references))
        gate_evaluated_at = datetime.now(UTC)
        radii = (skybot_radius_arcsec, tns_radius_arcsec, catalog_radius_arcsec)
        if any(
            isinstance(radius, bool) or not isinstance(radius, (int, float)) for radius in radii
        ):
            raise TypeError("verification radii must be numbers")
        if any(not math.isfinite(radius) or radius <= 0 for radius in radii):
            raise ValueError("verification radii must be finite and positive")
        skybot = self._check_skybot_epochs(
            candidate_id=candidate_id,
            ra=ra,
            dec=dec,
            mjds=ordered_references,
            radius_arcsec=skybot_radius_arcsec,
            evaluated_at=gate_evaluated_at,
        )
        raw_simbad = self.simbad.check(ra=ra, dec=dec, radius_arcsec=catalog_radius_arcsec)
        simbad: CatalogInterpretation = interpret_simbad(raw_simbad)
        vsx = self._catalog_check(
            self.vsx.check(ra=ra, dec=dec, radius_arcsec=catalog_radius_arcsec),
            expected_service="vsx",
        )
        if self.tns is None:
            tns = CheckProvenance(
                service="tns",
                status=CheckStatus.DISABLED,
                query={"candidate_id": candidate_id, "ra": ra, "dec": dec},
                error="TNS credentials/client not configured",
                attempts=0,
            )
        else:
            tns = self.tns.search(
                internal_name=candidate_id,
                ra=ra,
                dec=dec,
                radius_arcsec=tns_radius_arcsec,
            ).provenance

        checks = bind_completed_checks(
            tuple(self._fresh(check) for check in (tns, skybot, simbad.check, vsx)),
            EvidenceBindingContext(
                candidate_id=candidate_id,
                ra_deg=ra,
                dec_deg=dec,
                max_ttl_hours=self.evidence_ttl_hours,
                required_radii_arcsec={
                    "tns": tns_radius_arcsec,
                    "skybot": skybot_radius_arcsec,
                    "simbad": catalog_radius_arcsec,
                    "vsx": catalog_radius_arcsec,
                },
                skybot_reference_mjds=ordered_references,
            ),
        )
        manual_review_required = simbad.manual_review_required and "simbad" in required
        gate = evaluate_reportability(
            checks,
            quality_passed=quality_passed,
            manual_review_required=manual_review_required,
            mandatory_services=required,
            at=gate_evaluated_at,
        )
        return VerificationBundle(
            checks=checks,
            gate=gate,
            manual_review_required=manual_review_required,
            context={
                "simbad": simbad.context_labels,
                "skybot_epochs": tuple(f"{value:.8f}" for value in ordered_references),
            },
        )
