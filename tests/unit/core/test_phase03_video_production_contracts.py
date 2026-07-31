"""
Contract tests for the WindAgent Video Production ports (Phase 3).

Covers:
- Provider fake conforms to MediaGenerationProviderPort.
- Round-trip JSON serialization of the package.
- Backward-compatible additive fields.
- Unknown major version fails closed.
- Consumer handles duplicate events idempotently.
"""

import pytest

from windagent_core.contracts.video_production import (
    AssetStoragePort,
    MediaGenerationProviderPort,
    PreproductionPort,
    QualityReviewPort,
    VideoDirectionPort,
)
from windagent_core.domain.video_production import VideoProductionPackage
from windagent_core.domain.video_production.ids import (
    ProductionRevisionId,
    VideoProjectId,
)
from windagent_core.events.video_production import (
    EventIdempotencyGuard,
    VideoProductionEventCatalog,
    VideoProductionEventEnvelope,
)

from tests.fixtures.video_production.fixture_builder import build_valid_package_dict


class FakeMediaGenerationProvider:
    """Minimal fake implementing the MediaGenerationProviderPort semantics."""

    async def generate_image(self, request):
        return {"kind": "image", "request_id": str(request.request_id)}

    async def generate_video(self, request):
        return {"kind": "video", "request_id": str(request.request_id)}

    async def extend_video(self, request, source_asset_id, extension_seconds):
        return {"kind": "extension", "seconds": extension_seconds}

    async def inspect_job(self, request):
        return {"status": "COMPLETED"}

    async def download_result(self, request):
        return {"asset_id": "ast_downloaded", "content_hash": "a" * 64}


class TestPortConformance:
    def test_media_generation_provider_is_runtime_checkable(self):
        fake = FakeMediaGenerationProvider()
        assert isinstance(fake, MediaGenerationProviderPort)

    def test_ports_do_not_leak_browser_implementation_details(self):
        import inspect

        for port in (
            PreproductionPort,
            VideoDirectionPort,
            MediaGenerationProviderPort,
            AssetStoragePort,
            QualityReviewPort,
        ):
            source = inspect.getsource(port)
            for forbidden in ("cookie", "selector", "flow_project_url", "browser_session"):
                assert forbidden not in source.lower(), f"{port.__name__} leaks {forbidden}"


class TestRoundTripAndCompatibility:
    def test_round_trip_json(self):
        data = build_valid_package_dict()
        pkg = VideoProductionPackage.model_validate(data)
        raw = pkg.serialize()
        restored = VideoProductionPackage.deserialize(raw)
        assert restored.model_dump() == pkg.model_dump()

    def test_additive_fields_accepted(self):
        data = build_valid_package_dict()
        data["future_field"] = {"note": "forward compatible"}
        pkg = VideoProductionPackage.model_validate(data)
        assert pkg.schema_version == "1.0.0"

    def test_unknown_major_version_fails_closed(self):
        data = build_valid_package_dict()
        data["schema_version"] = "2.1.0"
        from windagent_core.domain.video_production.errors import UnsupportedMajorVersionError

        with pytest.raises(UnsupportedMajorVersionError):
            VideoProductionPackage.model_validate(data)


class TestIdempotentConsumer:
    def test_duplicate_events_not_processed_twice(self):
        guard = EventIdempotencyGuard()
        env = VideoProductionEventEnvelope(
            event_type=VideoProductionEventCatalog.GENERATION_SUBMITTED,
            project_id=VideoProjectId("vp_01"),
            revision_id=ProductionRevisionId("rev_01"),
            aggregate_id="vp_01",
        )
        assert guard.process(env) is True
        assert guard.process(env) is False

    def test_distinct_events_processed(self):
        guard = EventIdempotencyGuard()
        e1 = VideoProductionEventEnvelope(
            event_type=VideoProductionEventCatalog.GENERATION_SUBMITTED,
            project_id=VideoProjectId("vp_01"),
            revision_id=ProductionRevisionId("rev_01"),
            aggregate_id="vp_01",
        )
        e2 = VideoProductionEventEnvelope(
            event_type=VideoProductionEventCatalog.GENERATION_SUBMITTED,
            project_id=VideoProjectId("vp_01"),
            revision_id=ProductionRevisionId("rev_01"),
            aggregate_id="vp_01",
        )
        assert guard.process(e1) is True
        assert guard.process(e2) is True
