from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from siderea.clients.base import ResilientExecutor, ServiceResult
from siderea.clients.catalogs import SimbadClient, SkyBotClient, VSXClient
from siderea.clients.tns import TNSClient, TNSCredentials, _validate_response
from siderea.provenance import CheckProvenance, CheckStatus, digest_value


class _Unit:
    def __rmul__(self, value: object) -> object:
        return value


class _FakeSession:
    def __init__(self) -> None:
        self.headers = {"User-Agent": "astroquery/test"}

    def request(self, *args: object, **kwargs: object) -> dict[str, object]:
        return dict(kwargs)


def _fake_astronomy_modules(
    observations: dict[str, dict[str, object]],
    *,
    simbad_field_error: Exception | None = None,
) -> dict[str, types.ModuleType]:
    astropy = types.ModuleType("astropy")
    units = types.ModuleType("astropy.units")
    units.deg = _Unit()  # type: ignore[attr-defined]
    units.arcsec = _Unit()  # type: ignore[attr-defined]
    coordinates = types.ModuleType("astropy.coordinates")
    coordinates.SkyCoord = lambda **kwargs: kwargs  # type: ignore[attr-defined]
    time_module = types.ModuleType("astropy.time")
    time_module.Time = lambda value, **kwargs: (value, kwargs)  # type: ignore[attr-defined]
    astropy.units = units  # type: ignore[attr-defined]
    astropy.coordinates = coordinates  # type: ignore[attr-defined]
    astropy.time = time_module  # type: ignore[attr-defined]

    astroquery = types.ModuleType("astroquery")
    imcce = types.ModuleType("astroquery.imcce")
    simbad = types.ModuleType("astroquery.simbad")
    vizier = types.ModuleType("astroquery.vizier")

    class _Query:
        TIMEOUT = 300.0

        def __init__(self) -> None:
            self._session = _FakeSession()

        def record(self, service: str) -> None:
            request = self._session.request("GET", "https://catalog.invalid")
            observations[service] = {
                "timeout_setting": getattr(self, "timeout", self.TIMEOUT),
                "request_timeout": request.get("timeout"),
                "user_agent": self._session.headers["User-Agent"],
            }

    class _Skybot(_Query):
        def cone_search(self, *args: object) -> list[object]:
            self.record("skybot")
            return []

    class _Simbad(_Query):
        timeout = 300.0

        def add_votable_fields(self, *fields: object) -> None:
            if simbad_field_error is not None:
                raise simbad_field_error

        def query_region(self, *args: object, **kwargs: object) -> list[object]:
            self.record("simbad")
            return []

    class _Vizier(_Query):
        def __init__(self, **kwargs: object) -> None:
            super().__init__()

        def query_region(self, *args: object, **kwargs: object) -> list[object]:
            self.record("vsx")
            return []

    imcce.Skybot = _Skybot  # type: ignore[attr-defined]
    simbad.Simbad = _Simbad  # type: ignore[attr-defined]
    vizier.Vizier = _Vizier  # type: ignore[attr-defined]
    astroquery.imcce = imcce  # type: ignore[attr-defined]
    astroquery.simbad = simbad  # type: ignore[attr-defined]
    astroquery.vizier = vizier  # type: ignore[attr-defined]
    return {
        "astropy": astropy,
        "astropy.units": units,
        "astropy.coordinates": coordinates,
        "astropy.time": time_module,
        "astroquery": astroquery,
        "astroquery.imcce": imcce,
        "astroquery.simbad": simbad,
        "astroquery.vizier": vizier,
    }


class CatalogClientTests(unittest.TestCase):
    def test_retry_jitter_respects_maximum_and_long_retries_do_not_overflow(self):
        delays = []

        def fail():
            raise OSError("service unavailable")

        executor = ResilientExecutor(
            attempts=1100,
            base_delay_seconds=1,
            max_delay_seconds=2,
            jitter_fraction=0.5,
            sleeper=delays.append,
        )
        with patch("siderea.clients.base.random.random", return_value=1.0):
            result = executor.run(service="test", query={}, operation=fail, has_match=bool)
        self.assertEqual(result.provenance.status, CheckStatus.ERROR)
        self.assertEqual(result.provenance.attempts, 1100)
        self.assertEqual(len(delays), 1099)
        self.assertEqual(delays[0], 1.5)
        self.assertTrue(all(delay <= 2 for delay in delays))

    def test_disabled_is_not_clear(self):
        result = SkyBotClient(enabled=False).check(ra=1, dec=2, mjd=60000)
        self.assertEqual(result.provenance.status, CheckStatus.DISABLED)
        self.assertFalse(result.safe_clear)

    def test_tns_error_payload_cannot_be_interpreted_as_clear(self):
        with self.assertRaisesRegex(ValueError, "TNS API error"):
            _validate_response({"id_code": 403, "id_message": "bad credentials"})

    def test_tns_malformed_success_cannot_be_interpreted_as_clear(self):
        with self.assertRaisesRegex(ValueError, "search-result array"):
            _validate_response({"id_code": 200, "data": {}})
        with self.assertRaisesRegex(ValueError, "malformed row"):
            _validate_response({"id_code": 200, "data": ["not an object"]})
        _validate_response({"id_code": 200, "data": []})

    def test_tns_endpoint_must_be_https(self):
        credentials = TNSCredentials("secret", "1", "siderea-test")
        for endpoint in ("", "file:///etc/passwd", "http://example.test/search"):
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(ValueError, "HTTPS"):
                TNSClient(credentials, endpoint=endpoint)

        client = TNSClient(credentials, endpoint=" https://example.test/search ")
        self.assertEqual(client.endpoint, "https://example.test/search")

    def test_tns_credentials_and_timeout_are_strictly_typed(self):
        with self.assertRaisesRegex(TypeError, "credentials must be strings"):
            TNSCredentials(123, "1", "siderea-test").validate()  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "timeout_seconds must be a number"):
            TNSClient(TNSCredentials("secret", "1", "siderea-test"), timeout_seconds=True)

    def test_tns_search_rejects_boolean_coordinates_and_non_string_identity(self):
        client = TNSClient(TNSCredentials("secret", "1", "siderea-test"))
        with self.assertRaisesRegex(TypeError, "internal_name must be a string"):
            client.search(internal_name=123, ra=10.0, dec=20.0)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "ra must be a number"):
            client.search(internal_name="ZTF-test", ra=True, dec=20.0)
        with self.assertRaisesRegex(TypeError, "dec must be a number"):
            client.search(internal_name="ZTF-test", ra=10.0, dec=False)
        with self.assertRaisesRegex(TypeError, "radius_arcsec must be a number"):
            client.search(internal_name="ZTF-test", ra=10.0, dec=20.0, radius_arcsec=True)

    def test_retry_configuration_rejects_non_finite_values(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            ResilientExecutor(base_delay_seconds=float("nan"))

    def test_catalog_clients_apply_timeout_and_identification_to_fresh_sessions(self):
        observations: dict[str, dict[str, object]] = {}
        executor = ResilientExecutor(attempts=1)
        policy = {
            "timeout_seconds": 4.25,
            "user_agent": "siderea-observatory/contact@example.test",
        }
        clients_and_queries = (
            (SkyBotClient(executor, **policy), {"ra": 1, "dec": 2, "mjd": 60000}),
            (SimbadClient(executor, **policy), {"ra": 1, "dec": 2}),
            (VSXClient(executor, **policy), {"ra": 1, "dec": 2}),
        )

        with patch.dict(sys.modules, _fake_astronomy_modules(observations)):
            results = [client.check(**query) for client, query in clients_and_queries]

        self.assertTrue(all(result.provenance.status is CheckStatus.CLEAR for result in results))
        self.assertEqual(set(observations), {"skybot", "simbad", "vsx"})
        for service, observed in observations.items():
            with self.subTest(service=service):
                self.assertEqual(observed["timeout_setting"], 4.25)
                self.assertEqual(observed["request_timeout"], 4.25)
                self.assertEqual(
                    observed["user_agent"],
                    "astroquery/test siderea-observatory/contact@example.test",
                )
        for result in results:
            self.assertEqual(result.provenance.query["network_policy"], policy)

    def test_simbad_metadata_failure_is_explicit_error_evidence(self):
        executor = ResilientExecutor(attempts=1)
        modules = _fake_astronomy_modules(
            {},
            simbad_field_error=TimeoutError("otype metadata request timed out"),
        )

        with patch.dict(sys.modules, modules):
            result = SimbadClient(executor).check(ra=1, dec=2)

        self.assertEqual(result.provenance.status, CheckStatus.ERROR)
        self.assertEqual(result.provenance.attempts, 1)
        self.assertIn("otype metadata request timed out", result.provenance.error)
        self.assertFalse(result.safe_clear)

    def test_catalog_network_policy_rejects_unsafe_values(self):
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            SkyBotClient(timeout_seconds=float("inf"))
        with self.assertRaisesRegex(ValueError, "line breaks"):
            SimbadClient(user_agent="siderea-good\r\nInjected: bad")

    def test_tns_clear_attests_both_name_and_cone_responses(self):
        client = TNSClient(TNSCredentials("secret", "1", "siderea-test"))
        by_name = ServiceResult(
            provenance=CheckProvenance(
                service="tns",
                status=CheckStatus.CLEAR,
                query={"method": "internal_name", "internal_name": "ZTF-test"},
                response_digest=digest_value({"data": []}),
                attempts=1,
            ),
            value={"data": []},
        )
        by_cone = ServiceResult(
            provenance=CheckProvenance(
                service="tns",
                status=CheckStatus.CLEAR,
                query={"method": "cone", "ra": 10.0, "dec": 20.0},
                response_digest=digest_value({"data": {"reply": []}}),
                attempts=2,
            ),
            value={"data": {"reply": []}},
        )

        with patch.object(client, "_search_once", side_effect=(by_name, by_cone)):
            result = client.search(
                internal_name="ZTF-test",
                ra=10.0,
                dec=20.0,
                radius_arcsec=5.0,
            )

        self.assertEqual(result.provenance.status, CheckStatus.CLEAR)
        self.assertEqual(result.provenance.attempts, 3)
        self.assertEqual(
            result.provenance.query["coverage_policy"],
            "internal_name_and_position_cone",
        )
        self.assertEqual(len(result.provenance.response_digest), 64)


if __name__ == "__main__":
    unittest.main()
