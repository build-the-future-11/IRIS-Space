from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from siderea.clients.base import ServiceResult
from siderea.evidence_context import canonical_verification_context, format_skybot_epochs
from siderea.ingest import AlerceAdapter, BrokerQuery, IngestionError, ingest_csv
from siderea.ingest.schema import normalize_photometry_frame, resolve_columns
from siderea.integrity import (
    candidate_record_digest,
    candidate_run_binding_digest,
    verify_candidate_run_binding,
)
from siderea.provenance import CheckProvenance, CheckStatus, digest_value
from siderea.validation import (
    EvidenceBindingContext,
    VerificationSuite,
    bind_completed_check,
    preflight_digest,
)
from siderea.validation.catalog_policy import interpret_simbad
from siderea.validation.gates import GateDecision


def _clear_check(service: str, query: dict[str, object]) -> CheckProvenance:
    checked = datetime.now(UTC)
    return CheckProvenance(
        service=service,
        status=CheckStatus.CLEAR,
        checked_at=checked.isoformat(),
        expires_at=(checked + timedelta(hours=1)).isoformat(),
        query=query,
        response_digest=digest_value([]),
    )


def test_csv_rejects_duplicate_raw_headers_before_pandas_mangles_them(tmp_path) -> None:
    path = tmp_path / "duplicate-header.csv"
    path.write_text(
        "source_id,source_id,ra_deg,dec_deg,mjd,band,magnitude\nA,substituted,10,20,60000,g,19\n",
        encoding="utf-8",
    )

    with pytest.raises(IngestionError, match="differ only by case"):
        ingest_csv(path)


def test_one_physical_column_cannot_supply_multiple_logical_fields() -> None:
    with pytest.raises(IngestionError, match="mapped to both"):
        resolve_columns(
            ["identity_and_position", "mjd", "band", "magnitude"],
            column_map={
                "source_id": "identity_and_position",
                "ra_deg": "identity_and_position",
                "dec_deg": "identity_and_position",
            },
        )


def test_malformed_measurement_cannot_silently_become_a_nondetection() -> None:
    frame = pd.DataFrame(
        [
            {
                "source_id": "A",
                "ra_deg": 10.0,
                "dec_deg": 20.0,
                "mjd": 60000.0,
                "band": "g",
                "magnitude": "not-a-number",
            }
        ]
    )

    with pytest.raises(IngestionError, match="invalid numeric values.*magnitude"):
        normalize_photometry_frame(frame)


def test_coordinate_tolerance_is_pairwise_not_just_relative_to_first_row() -> None:
    frame = pd.DataFrame(
        [
            {
                "source_id": "A",
                "ra_deg": 10.0,
                "dec_deg": 0.0,
                "mjd": 1,
                "band": "g",
                "magnitude": 19,
            },
            {
                "source_id": "A",
                "ra_deg": 10.0 + 1.9 / 3600.0,
                "dec_deg": 0.0,
                "mjd": 2,
                "band": "g",
                "magnitude": 18,
            },
            {
                "source_id": "A",
                "ra_deg": 10.0 - 1.9 / 3600.0,
                "dec_deg": 0.0,
                "mjd": 3,
                "band": "g",
                "magnitude": 17,
            },
        ]
    )

    with pytest.raises(IngestionError, match="positions separated"):
        normalize_photometry_frame(frame, coordinate_tolerance_arcsec=2.0)


def test_csv_preserves_leading_zero_observation_identifiers(tmp_path) -> None:
    path = tmp_path / "identifiers.csv"
    path.write_text(
        "source_id,ra_deg,dec_deg,mjd,band,magnitude,observation_id\nA,10,20,60000,g,19,000012\n",
        encoding="utf-8",
    )

    assert ingest_csv(path).observations.loc[0, "observation_id"] == "000012"


def test_ingestion_batch_access_cannot_mutate_internal_rows_or_provenance(tmp_path) -> None:
    path = tmp_path / "immutable-batch.csv"
    path.write_text(
        "source_id,ra_deg,dec_deg,mjd,band,magnitude\nA,10,20,60000,g,19\n",
        encoding="utf-8",
    )
    batch = ingest_csv(path)

    exposed_rows = batch.observations
    exposed_rows.loc[0, "magnitude"] = -99.0
    exposed_provenance = batch.provenance
    exposed_provenance["sha256"] = "0" * 64
    exposed_provenance["column_map"]["source_id"] = "forged"

    assert batch.to_frame().loc[0, "magnitude"] == 19.0
    assert batch.provenance["sha256"] != "0" * 64
    assert batch.provenance["column_map"]["source_id"] == "source_id"


def test_preflight_digest_rejects_an_empty_mandatory_service_policy() -> None:
    context = EvidenceBindingContext(
        candidate_id="A",
        ra_deg=10.0,
        dec_deg=20.0,
        max_ttl_hours=24.0,
    )

    with pytest.raises(ValueError, match="at least one"):
        preflight_digest(
            context=context,
            checks=(),
            quality_passed=True,
            manual_review_required=False,
            mandatory_services=(),
            required_reviewers=1,
        )


def test_integrity_json_rejects_type_erasure_and_nonfinite_values() -> None:
    with pytest.raises(TypeError, match="keys must be strings"):
        digest_value({1: "value"})
    with pytest.raises(ValueError, match="non-finite"):
        digest_value({"value": float("nan")})


def test_check_query_is_deeply_immutable_and_defensively_copied() -> None:
    original = {"epochs": [1.0, 2.0], "nested": {"radius": 3.0}}
    check = _clear_check("simbad", original)

    original["epochs"].append(3.0)
    original["nested"]["radius"] = 99.0
    assert check.query["epochs"] == [1.0, 2.0]
    assert check.query["nested"]["radius"] == 3.0
    with pytest.raises(AttributeError):
        check.query["epochs"].append(4.0)
    with pytest.raises(TypeError):
        check.query["new"] = "mutation"


def test_broker_query_rejects_boolean_bounds_and_string_class_sequence() -> None:
    with pytest.raises(TypeError, match="classes"):
        BrokerQuery(classes="SN")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="max_objects"):
        BrokerQuery(max_objects=True)  # type: ignore[arg-type]


class _SurveyAwareAlerce:
    def __init__(self) -> None:
        self.surveys: list[str] = []
        self.object_queries: list[dict[str, object]] = []

    def query_objects(self, **query: object) -> pd.DataFrame:
        self.surveys.append(str(query["survey"]))
        self.object_queries.append(query)
        row: dict[str, object] = {
            "oid": "LSST-A",
            "meanra": 11.0,
            "meandec": -2.0,
        }
        if query["survey"] == "lsst":
            row.update(
                {
                    "class_name": query["class_name"],
                    "classifier_name": query["classifier"],
                    "classifier_version": "2.0.1",
                    "n_det": query["n_det"][0],  # type: ignore[index]
                }
            )
        return pd.DataFrame([row])

    def query_detections(self, _: str, **query: object) -> pd.DataFrame:
        self.surveys.append(str(query["survey"]))
        if query["survey"] == "ztf":
            return pd.DataFrame(
                {
                    "mjd": [60001.0],
                    "fid": [1],
                    "magpsf": [18.0],
                    "sigmapsf": [0.1],
                    "isdiffpos": [1],
                    "candid": [1234],
                }
            )
        return pd.DataFrame(
            {
                "mjd": [60001.0],
                "band": [1],
                "band_name": ["g"],
                "psfFlux": [100.0],
                "psfFluxErr": [3.0],
                "psfFlux_flag": [0],
                "psfFlux_flag_edge": [0],
                "psfFlux_flag_noGoodPixels": [0],
                "isNegative": [False],
                "pixelFlags": [False],
                "pixelFlags_bad": [False],
                "pixelFlags_cr": [False],
                "pixelFlags_crCenter": [False],
                "pixelFlags_edge": [False],
                "pixelFlags_nodata": [False],
                "pixelFlags_nodataCenter": [False],
                "pixelFlags_interpolated": [False],
                "pixelFlags_interpolatedCenter": [False],
                "pixelFlags_offimage": [False],
                "pixelFlags_saturated": [False],
                "pixelFlags_saturatedCenter": [False],
                "pixelFlags_suspect": [False],
                "pixelFlags_suspectCenter": [False],
                "pixelFlags_streak": [False],
                "pixelFlags_streakCenter": [False],
                "pixelFlags_injected": [False],
                "pixelFlags_injectedCenter": [False],
                "pixelFlags_injected_template": [False],
                "pixelFlags_injected_templateCenter": [False],
                "timeWithdrawnMjdTai": [None],
            }
        )

    def query_non_detections(self, _: str, **query: object) -> pd.DataFrame:
        self.surveys.append(str(query["survey"]))
        return pd.DataFrame()


def test_alerce_binds_explicit_survey_to_every_query_and_provenance() -> None:
    client = _SurveyAwareAlerce()
    batch = AlerceAdapter(client, survey="LSST").fetch(BrokerQuery(max_objects=1))

    assert client.surveys == ["lsst", "lsst", "lsst"]
    assert client.object_queries == [
        {
            "classifier": "stamp_classifier_rubin_beta",
            "class_name": "SN",
            "n_det": [3, 1_000_000],
            "ranking": 1,
            "probability": 0.0,
            "order_by": "probability",
            "order_mode": "DESC",
            "page_size": 1,
            "page": 1,
            "format": "pandas",
            "survey": "lsst",
        }
    ]
    assert batch.provenance["adapter"] == "siderea.ingest.alerce.v4"
    assert batch.provenance["survey"] == "lsst"
    assert batch.provenance["classifier_version"] == "2.0.1"
    assert batch.provenance["observed_classifier_versions"] == ["2.0.1"]
    assert batch.observations["survey"].tolist() == ["lsst/alerce"]
    with pytest.raises(ValueError, match="ztf.*lsst"):
        AlerceAdapter(client, survey="ambiguous")

    unsupported_client = _SurveyAwareAlerce()
    with pytest.raises(IngestionError, match="does not support"):
        AlerceAdapter(unsupported_client, survey="lsst").fetch(
            BrokerQuery(classes=("SNIa",), max_objects=1)
        )
    assert unsupported_client.object_queries == []


def test_alerce_uses_legacy_ztf_detection_filter_and_default_classifier() -> None:
    client = _SurveyAwareAlerce()
    AlerceAdapter(client, survey="ztf").fetch(BrokerQuery(max_objects=1))

    query = client.object_queries[0]
    assert query["classifier"] == "lc_classifier_transient"
    assert query["ndet"] == [3, 1_000_000]
    assert "n_det" not in query


def test_alerce_lsst_query_matches_multisurvey_valid_parameter_contract() -> None:
    valid_lsst_parameters = {
        "oid",
        "survey",
        "classifier",
        "class_name",
        "ranking",
        "n_det",
        "probability",
        "firstmjd",
        "lastmjd",
        "ra",
        "dec",
        "radius",
        "page",
        "page_size",
        "count",
        "order_by",
        "order_mode",
        "format",
    }

    class ContractCheckingAlerce(_SurveyAwareAlerce):
        def query_objects(self, **query: object) -> pd.DataFrame:
            unexpected = set(query) - valid_lsst_parameters
            if unexpected:
                raise ValueError(f"Invalid parameter: {sorted(unexpected)[0]}")
            return super().query_objects(**query)

    client = ContractCheckingAlerce()
    AlerceAdapter(
        client,
        survey="lsst",
        classifier="custom-lsst",
        classifier_version="2.0.1",
    ).fetch(BrokerQuery(max_objects=1, min_detections=7))

    assert client.object_queries[0]["n_det"] == [7, 1_000_000]
    assert client.object_queries[0]["classifier"] == "custom-lsst"
    assert "ndet" not in client.object_queries[0]


def test_alerce_custom_lsst_classifier_uses_response_validation_not_default_taxonomy() -> None:
    class CustomTaxonomyAlerce(_SurveyAwareAlerce):
        def query_objects(self, **query: object) -> pd.DataFrame:
            result = super().query_objects(**query)
            result["classifier_version"] = "9.4"
            return result

    client = CustomTaxonomyAlerce()
    AlerceAdapter(
        client,
        survey="lsst",
        classifier="custom",
        classifier_version="9.4",
    ).fetch(BrokerQuery(classes=("NewClass",), max_objects=1))

    assert client.object_queries[0]["class_name"] == "NewClass"


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ({"class_name": "AGN"}, "class_name"),
        ({"classifier_name": "other"}, "classifier_name"),
        ({"classifier_version": "future"}, "classifier_version"),
        ({"n_det": 1}, "minimum-detection"),
    ),
)
def test_alerce_rejects_lsst_responses_that_violate_query_contract(
    mutation: dict[str, object], message: str
) -> None:
    class MismatchedAlerce(_SurveyAwareAlerce):
        def query_objects(self, **query: object) -> pd.DataFrame:
            result = super().query_objects(**query)
            for field, value in mutation.items():
                result[field] = value
            return result

    with pytest.raises(IngestionError, match=message):
        AlerceAdapter(MismatchedAlerce(), survey="lsst").fetch(
            BrokerQuery(max_objects=1, min_detections=3)
        )


def test_alerce_rejects_lsst_response_missing_classifier_contract_fields() -> None:
    class IncompleteAlerce(_SurveyAwareAlerce):
        def query_objects(self, **query: object) -> pd.DataFrame:
            return super().query_objects(**query).drop(columns=["classifier_version"])

    with pytest.raises(IngestionError, match="missing contract fields.*classifier_version"):
        AlerceAdapter(IncompleteAlerce(), survey="lsst").fetch(BrokerQuery(max_objects=1))


def test_alerce_custom_lsst_classifier_requires_a_version_contract() -> None:
    with pytest.raises(ValueError, match="custom LSST classifier.*classifier_version"):
        AlerceAdapter(_SurveyAwareAlerce(), survey="lsst", classifier="custom")


def test_alerce_normalizes_official_lsst_flux_and_band_fields() -> None:
    class LsstResponseAlerce(_SurveyAwareAlerce):
        def query_detections(self, _: str, **query: object) -> pd.DataFrame:
            frame = super().query_detections(_, **query)
            frame["measurement_id"] = 991
            frame["mjd"] = 61001.25
            frame["band"] = 2
            frame["band_name"] = "r"
            frame["psfFlux"] = 138.5
            frame["psfFluxErr"] = 4.25
            return frame

    batch = AlerceAdapter(LsstResponseAlerce(), survey="lsst").fetch(BrokerQuery(max_objects=1))

    observation = batch.observations.iloc[0]
    assert observation["band"] == "r"
    assert observation["flux"] == pytest.approx(138.5)
    assert observation["flux_error"] == pytest.approx(4.25)
    assert observation["observation_id"] == "991"
    assert observation["survey"] == "lsst/alerce"
    assert observation["quality"]


def test_alerce_rejects_flagged_or_withdrawn_lsst_measurements_from_features() -> None:
    class FlaggedLsstAlerce(_SurveyAwareAlerce):
        def query_detections(self, _: str, **query: object) -> pd.DataFrame:
            frame = super().query_detections(_, **query)
            result = frame.loc[frame.index.repeat(5)].reset_index(drop=True)
            result["mjd"] = [60001.0, 60002.0, 60003.0, 60004.0, 60005.0]
            result.loc[1, "psfFlux_flag_edge"] = 1
            result.loc[2, "timeWithdrawnMjdTai"] = 60004.0
            result.loc[3, "pixelFlags_cr"] = True
            result.loc[4, "isNegative"] = True
            result.loc[4, "psfFlux"] = -100.0
            return result

    batch = AlerceAdapter(FlaggedLsstAlerce(), survey="lsst").fetch(BrokerQuery(max_objects=1))

    assert batch.observations["quality"].tolist() == [True, False, False, False, True]
    assert batch.observations.iloc[-1]["flux"] == pytest.approx(-100.0)


@pytest.mark.parametrize(
    "flag",
    (
        "psfFlux_flag",
        "psfFlux_flag_edge",
        "psfFlux_flag_noGoodPixels",
        "pixelFlags",
        "pixelFlags_bad",
        "pixelFlags_cr",
        "pixelFlags_crCenter",
        "pixelFlags_edge",
        "pixelFlags_nodata",
        "pixelFlags_nodataCenter",
        "pixelFlags_interpolated",
        "pixelFlags_interpolatedCenter",
        "pixelFlags_offimage",
        "pixelFlags_saturated",
        "pixelFlags_saturatedCenter",
        "pixelFlags_suspect",
        "pixelFlags_suspectCenter",
        "pixelFlags_streak",
        "pixelFlags_streakCenter",
        "pixelFlags_injected",
        "pixelFlags_injectedCenter",
        "pixelFlags_injected_template",
        "pixelFlags_injected_templateCenter",
    ),
)
def test_alerce_lsst_quality_policy_rejects_each_adverse_flag(flag: str) -> None:
    class FlaggedLsstAlerce(_SurveyAwareAlerce):
        def query_detections(self, _: str, **query: object) -> pd.DataFrame:
            frame = super().query_detections(_, **query)
            frame.loc[0, flag] = 1 if flag.startswith("psfFlux_") else True
            return frame

    batch = AlerceAdapter(FlaggedLsstAlerce(), survey="lsst").fetch(BrokerQuery(max_objects=1))

    assert batch.observations["quality"].tolist() == [False]


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (("drop", "pixelFlags_cr"), "requires exactly one 'pixelflags_cr'"),
        (("set", "pixelFlags_cr", None), "invalid binary flag 'pixelFlags_cr'"),
        (("set", "pixelFlags_cr", 2), "invalid binary flag 'pixelFlags_cr'"),
        (("drop", "timeWithdrawnMjdTai"), "requires exactly one 'timewithdrawnmjdtai'"),
    ),
)
def test_alerce_lsst_quality_policy_fails_closed_on_incomplete_flags(
    mutation: tuple[object, ...], message: str
) -> None:
    class MalformedLsstAlerce(_SurveyAwareAlerce):
        def query_detections(self, _: str, **query: object) -> pd.DataFrame:
            frame = super().query_detections(_, **query)
            operation, field, *value = mutation
            if operation == "drop":
                return frame.drop(columns=[str(field)])
            frame[str(field)] = frame[str(field)].astype(object)
            frame.loc[0, str(field)] = value[0]
            return frame

    with pytest.raises(IngestionError, match=message):
        AlerceAdapter(MalformedLsstAlerce(), survey="lsst").fetch(BrokerQuery(max_objects=1))


def test_alerce_ztf_uses_raw_psf_policy_and_positive_subtractions() -> None:
    class OfficialZtfAlerce(_SurveyAwareAlerce):
        def query_objects(self, **query: object) -> pd.DataFrame:
            self.object_queries.append(query)
            return pd.DataFrame({"oid": ["ZTF-A"], "meanra": [11.0], "meandec": [-2.0]})

        def query_detections(self, _: str, **query: object) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "mjd": [60001.0, 60002.0],
                    "fid": [1, 1],
                    "magpsf": [19.0, 18.5],
                    "sigmapsf": [0.1, 0.2],
                    "magpsf_corr": [14.0, 13.0],
                    "sigmapsf_corr": [100.0, 100.0],
                    "corrected": [True, True],
                    "dubious": [False, False],
                    "isdiffpos": [1, -1],
                    "candid": [101, 102],
                }
            )

        def query_non_detections(self, _: str, **query: object) -> pd.DataFrame:
            return pd.DataFrame({"mjd": [60000.0], "fid": [1], "diffmaglim": [20.5]})

    batch = AlerceAdapter(OfficialZtfAlerce(), survey="ztf").fetch(BrokerQuery(max_objects=1))

    detections = batch.observations.loc[batch.observations["is_detection"]]
    assert detections["magnitude"].tolist() == [19.0, 18.5]
    assert detections["magnitude_error"].tolist() == [0.1, 0.2]
    assert batch.observations["quality"].tolist() == [True, True, False]
    assert batch.provenance["photometry_policy"]["corrected_fields_used"] is False


def test_alerce_applies_timeout_user_agent_and_bounded_retries() -> None:
    class Session:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {"User-Agent": "alerce-client"}
            self.timeouts: list[float | None] = []

        def request(self, *_: object, timeout: float | None = None, **__: object) -> None:
            self.timeouts.append(timeout)

    class Search:
        def __init__(self) -> None:
            self.session = Session()

    class RetryingAlerce(_SurveyAwareAlerce):
        def __init__(self) -> None:
            super().__init__()
            self.legacy_ztf_client = Search()
            self.object_attempts = 0

        def query_objects(self, **query: object) -> pd.DataFrame:
            self.object_attempts += 1
            if self.object_attempts < 3:
                raise TimeoutError("transient broker timeout")
            return super().query_objects(**query)

    client = RetryingAlerce()
    delays: list[float] = []
    adapter = AlerceAdapter(
        client,
        timeout_seconds=4.5,
        user_agent="siderea-test/contact",
        max_retries=2,
        backoff_seconds=0.25,
        sleeper=delays.append,
    )
    batch = adapter.fetch(BrokerQuery(max_objects=1))

    client.legacy_ztf_client.session.request("GET", "https://example.test")
    assert client.legacy_ztf_client.session.timeouts == [4.5]
    assert client.legacy_ztf_client.session.headers["User-Agent"] == (
        "alerce-client siderea-test/contact"
    )
    assert client.object_attempts == 3
    assert delays == [0.25, 0.5]
    assert batch.provenance["network_policy"] == {
        "timeout_seconds": 4.5,
        "user_agent": "siderea-test/contact",
        "max_retries": 2,
        "backoff_seconds": 0.25,
        "session_policy_enforced": True,
    }


@pytest.mark.parametrize(
    ("keyword", "value"),
    (
        ("timeout_seconds", True),
        ("timeout_seconds", float("inf")),
        ("user_agent", "siderea\r\ninjected"),
        ("max_retries", True),
        ("max_retries", -1),
        ("backoff_seconds", float("nan")),
    ),
)
def test_alerce_rejects_unsafe_network_policy(keyword: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        AlerceAdapter(_SurveyAwareAlerce(), **{keyword: value})


def test_skybot_requires_a_distinct_query_for_each_distinct_reference_epoch() -> None:
    context = EvidenceBindingContext(
        candidate_id="A",
        ra_deg=10.0,
        dec_deg=20.0,
        max_ttl_hours=1.0,
        required_radii_arcsec={"skybot": 10.0},
        skybot_reference_mjds=(61000.0, 61000.001),
    )
    check = _clear_check(
        "skybot",
        {"ra": 10.0, "dec": 20.0, "radius_arcsec": 10.0, "mjd": 61000.0005},
    )

    rebound = bind_completed_check(check, context)
    assert rebound.status is CheckStatus.ERROR
    assert "uncovered" in rebound.error


def test_clearance_rejects_malformed_or_conflicting_query_aliases() -> None:
    context = EvidenceBindingContext(
        candidate_id="A",
        ra_deg=10.0,
        dec_deg=20.0,
        max_ttl_hours=1.0,
        required_radii_arcsec={"simbad": 3.0},
    )
    conflicting = _clear_check(
        "simbad",
        {
            "ra": 10.0,
            "ra_deg": 11.0,
            "dec": 20.0,
            "radius_arcsec": 3.0,
        },
    )
    malformed = _clear_check(
        "simbad",
        {"ra": 10.0, "dec": 20.0, "radius_arcsec": "invalid"},
    )

    assert bind_completed_check(conflicting, context).status is CheckStatus.ERROR
    assert bind_completed_check(malformed, context).status is CheckStatus.ERROR


def test_skybot_epoch_serialization_rejects_precision_collisions() -> None:
    with pytest.raises(ValueError, match="canonical eight-decimal precision"):
        format_skybot_epochs((61000.000000001, 61000.000000002))
    with pytest.raises(ValueError, match="field names must be strings"):
        canonical_verification_context(
            {1: [], "simbad": [], "skybot_epochs": []},  # type: ignore[dict-item]
            manual_review_required=False,
        )


def test_simbad_clearance_is_bound_to_the_interpreted_records() -> None:
    rows = [{"MAIN_ID": "V123", "OTYPE": "V*"}]
    check = CheckProvenance(
        service="simbad",
        status=CheckStatus.CLEAR,
        query={"ra": 10.0, "dec": 20.0, "radius_arcsec": 3.0},
        response_digest=digest_value([]),
    )

    interpreted = interpret_simbad(ServiceResult(check, rows))
    assert interpreted.check.status is CheckStatus.ERROR
    assert "digest" in interpreted.reason


class _Catalog:
    def __init__(self, service: str, *, digest_matches: bool = True) -> None:
        self.service = service
        self.digest_matches = digest_matches

    def check(self, **query: object) -> ServiceResult[list[dict[str, object]]]:
        rows: list[dict[str, object]] = []
        digest = digest_value(rows if self.digest_matches else ["different"])
        return ServiceResult(
            CheckProvenance(
                service=self.service,
                status=CheckStatus.CLEAR,
                query=query,
                response_digest=digest,
            ),
            rows,
        )


def test_verification_suite_blocks_mismatched_skybot_response_digest() -> None:
    suite = VerificationSuite(
        skybot=_Catalog("skybot", digest_matches=False),  # type: ignore[arg-type]
        simbad=_Catalog("simbad"),  # type: ignore[arg-type]
        vsx=_Catalog("vsx"),  # type: ignore[arg-type]
        evidence_ttl_hours=1.0,
    )

    bundle = suite.verify(
        candidate_id="A",
        ra=10.0,
        dec=20.0,
        peak_mjd=61000.0,
        quality_passed=True,
        mandatory_services=("skybot",),
    )
    assert bundle.gate.decision is GateDecision.BLOCK_INCOMPLETE_EVIDENCE
    assert (
        next(check for check in bundle.checks if check.service == "skybot").status
        is CheckStatus.ERROR
    )


def test_run_binding_is_separate_from_run_stable_candidate_record_digest() -> None:
    record: dict[str, object] = {
        "run_id": "run-one",
        "scientific_fingerprint": "science-one",
        "candidate_id": "A",
        "candidate_version": "a" * 64,
        "value": 1,
    }
    record["candidate_record_digest"] = candidate_record_digest(record)
    record["candidate_run_binding_digest"] = candidate_run_binding_digest(record)
    verify_candidate_run_binding(record)

    another_run = deepcopy(record)
    another_run["run_id"] = "run-two"
    assert candidate_record_digest(another_run) == record["candidate_record_digest"]
    assert candidate_run_binding_digest(another_run) != record["candidate_run_binding_digest"]
    with pytest.raises(ValueError, match="run binding differs"):
        verify_candidate_run_binding(another_run)

    changed_science = deepcopy(record)
    changed_science["scientific_fingerprint"] = "science-two"
    assert candidate_record_digest(changed_science) != record["candidate_record_digest"]
