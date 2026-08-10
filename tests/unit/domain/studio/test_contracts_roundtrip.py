"""A2 contract tests: durable envelope / result / event round trips and errors.

Serialization round trips for task envelopes, task results, and event
envelopes; task-result status consistency rules; frozen error-code HTTP
mapping; capability profile fail-closed behavior.
"""

import pytest
from pydantic import ValidationError

from windagent_core.contracts.studio.capabilities import (
    CapabilityStatus,
    RuntimeCapability,
    RuntimeCapabilityProfile,
)
from windagent_core.contracts.studio.errors import (
    HTTP_STATUS_BY_CODE,
    StudioError,
    StudioErrorCode,
    StudioStaleRevisionError,
)
from windagent_core.contracts.studio.ids import (
    ArtifactId,
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
    StudioRunId,
)
from windagent_core.contracts.studio.models import (
    StudioArtifactRef,
    StudioEventEnvelope,
    StudioRouteProvenance,
    StudioTaskEnvelope,
    StudioTaskResult,
    StudioTaskStatus,
    StudioTaskType,
)
from windagent_core.events.studio import StudioEventCatalog

SERIES = SeriesProjectId.generate("ser")
EPISODE = EpisodeId.generate("ep")
RUN = StudioRunId.generate("run")
REV = ProductionRevisionId.generate("rev")


def _task_envelope(**overrides) -> StudioTaskEnvelope:
    base = dict(
        task_type=StudioTaskType.IDEA_GENERATE,
        studio_run_id=RUN,
        dag_node_id="node_1",
        series_id=SERIES,
        episode_id=EPISODE,
        idempotency_key="idem_1",
    )
    base.update(overrides)
    return StudioTaskEnvelope(**base)


# ---- task envelope -------------------------------------------------------------


def test_task_envelope_round_trip_is_lossless():
    envelope = _task_envelope(
        input_artifact_refs=[
            StudioArtifactRef(
                artifact_id=ArtifactId.generate("art"),
                artifact_type="StoryBible",
                content_hash="a" * 64,
            )
        ],
        payload={"prompt": "x"},
        attempt=2,
    )
    restored = StudioTaskEnvelope.model_validate(envelope.to_dict())
    assert restored == envelope
    assert restored.to_dict() == envelope.to_dict()


def test_task_envelope_frozen_task_types_are_dotted_studio():
    for task_type in StudioTaskType:
        assert task_type.value.startswith("studio.story.")
        assert task_type.value.count(".") >= 2


def test_task_envelope_requires_idempotency_key():
    with pytest.raises(ValidationError):
        _task_envelope(idempotency_key="")


# ---- task result ---------------------------------------------------------------


def test_task_result_succeeded_cannot_carry_error():
    with pytest.raises(ValidationError):
        StudioTaskResult(
            task_id="t1",
            studio_run_id=RUN,
            dag_node_id="node_1",
            status=StudioTaskStatus.SUCCEEDED,
            error="boom",
        )


def test_task_result_failed_must_carry_error():
    with pytest.raises(ValidationError):
        StudioTaskResult(
            task_id="t1",
            studio_run_id=RUN,
            dag_node_id="node_1",
            status=StudioTaskStatus.FAILED,
        )


def test_task_result_round_trip_with_provenance():
    result = StudioTaskResult(
        task_id="t1",
        studio_run_id=RUN,
        dag_node_id="node_1",
        output_artifact_refs=[
            StudioArtifactRef(
                artifact_id=ArtifactId.generate("art"),
                artifact_type="ScreenplayDraft",
                content_hash="b" * 64,
            )
        ],
        route_provenance=StudioRouteProvenance(
            provider_id="openrouter",
            model_id="deepseek-v4-flash",
            usage={"prompt_tokens": 10},
        ),
        next_episode_state="SCREENPLAY_REVIEW",
    )
    restored = StudioTaskResult.model_validate(result.to_dict())
    assert restored == result


# ---- event envelope ------------------------------------------------------------


def test_event_envelope_round_trip_via_dict():
    envelope = StudioEventEnvelope(
        event_type=StudioEventCatalog.SCREENPLAY_LOCKED,
        aggregate_id=str(EPISODE),
        sequence=3,
        studio_run_id=RUN,
        artifact_refs=[ArtifactId.generate("art")],
        payload={"revision": str(REV)},
    )
    restored = StudioEventEnvelope.from_dict(envelope.to_dict())
    assert restored == envelope


def test_event_envelope_rejects_unknown_type():
    with pytest.raises(ValidationError):
        StudioEventEnvelope(
            event_type="studio.not.in.catalog",
            aggregate_id=str(EPISODE),
        )


def test_all_catalog_events_are_dotted_and_lowercase():
    for event_type in StudioEventCatalog.ALL_EVENTS:
        assert event_type.startswith("studio.")
        assert event_type == event_type.lower()


def test_catalog_matches_global_event_catalog_registration():
    from windagent_core.events.catalog import EventCatalog

    registered = {
        value
        for name, value in vars(EventCatalog).items()
        if name.startswith("STUDIO_") and isinstance(value, str)
    }
    assert registered == StudioEventCatalog.ALL_EVENTS


# ---- errors --------------------------------------------------------------------


def test_studio_error_http_status_mapping_is_frozen():
    assert HTTP_STATUS_BY_CODE[StudioErrorCode.NOT_FOUND] == 404
    assert HTTP_STATUS_BY_CODE[StudioErrorCode.STALE_REVISION] == 409
    assert HTTP_STATUS_BY_CODE[StudioErrorCode.CAPABILITY_UNAVAILABLE] == 503
    assert HTTP_STATUS_BY_CODE[StudioErrorCode.INTERNAL_ERROR] == 500


def test_studio_error_exposes_code_and_status():
    err = StudioStaleRevisionError("stale", details={"k": "v"})
    assert err.studio_code == StudioErrorCode.STALE_REVISION
    assert err.http_status == 409
    payload = err.to_dict()
    assert payload["code"] == "STUDIO_STALE_REVISION"
    assert payload["studio_code"] == "STALE_REVISION"
    assert payload["http_status"] == 409


def test_studio_errors_are_windagent_errors():
    assert issubclass(StudioError, Exception)


# ---- capabilities --------------------------------------------------------------


def test_capability_profile_fail_closed():
    clean = RuntimeCapabilityProfile(certification_mode=True)
    assert clean.is_fail_closed_ok
    fake = RuntimeCapabilityProfile(
        certification_mode=True, fail_closed_flags=["fake_runtime"]
    )
    assert not fake.is_fail_closed_ok


def test_capability_profile_by_name_and_round_trip():
    profile = RuntimeCapabilityProfile(
        capabilities=[
            RuntimeCapability(
                name="worker",
                status=CapabilityStatus.AVAILABLE,
                source="probe",
            )
        ]
    )
    assert profile.by_name("worker").status == CapabilityStatus.AVAILABLE
    assert profile.by_name("missing") is None
    restored = RuntimeCapabilityProfile.model_validate(profile.to_dict())
    assert restored == profile
