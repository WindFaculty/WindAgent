"""
Unit tests for the WindAgent Video Production domain (Phase 3).

Covers:
- Stable serialization / content hash
- Revision immutability and locking
- Duplicate / broken reference detection
- Event envelope validation
- Approval target hash
"""

import pytest

from windagent_core.domain.video_production import (
    ApprovalDecisionType,
    InvalidationIntent,
    LockedRevisionMutationError,
    ProductionRevision,
    RevisionService,
    UnsupportedMajorVersionError,
    VideoProductionPackage,
    VideoProductionPackageValidator,
)
from windagent_core.domain.video_production.ids import (
    ProductionRevisionId,
    VideoProjectId,
)
from windagent_core.events.video_production import (
    VideoProductionEventCatalog,
    VideoProductionEventEnvelope,
)

from tests.fixtures.video_production.fixture_builder import (
    build_invalid_broken_reference,
    build_invalid_duplicate_id,
    build_invalid_asset_missing_hash,
    build_invalid_missing_id,
    build_invalid_mutation_after_lock,
    build_invalid_unordered_shot,
    build_valid_package,
    build_valid_package_dict,
)


class TestCanonicalSerializationAndHash:
    def test_canonical_hash_stable_for_same_content(self):
        pkg_a = build_valid_package()
        pkg_b = VideoProductionPackage.model_validate(build_valid_package_dict())
        assert pkg_a.content_hash() == pkg_b.content_hash()

    def test_serialize_round_trip(self):
        pkg = build_valid_package()
        raw = pkg.serialize()
        restored = VideoProductionPackage.deserialize(raw)
        assert restored.content_hash() == pkg.content_hash()

    def test_content_hash_changes_when_content_changes(self):
        pkg = build_valid_package()
        changed = pkg.model_copy(update={"project_id": VideoProjectId("vp_other")})
        assert changed.content_hash() != pkg.content_hash()

    def test_unknown_major_version_fails_closed(self):
        with pytest.raises(UnsupportedMajorVersionError):
            VideoProductionPackage(
                schema_version="2.0.0",
                project_id=VideoProjectId("vp_01"),
                revision_id=ProductionRevisionId("rev_01"),
            )


class TestRevisionImmutability:
    def _base_revision(self) -> ProductionRevision:
        return ProductionRevision(
            revision_id=ProductionRevisionId("rev_01"),
            project_id=VideoProjectId("vp_01"),
            created_by="planner",
            content_hash="a" * 64,
        )

    def test_derive_from_draft_allows_change(self):
        parent = self._base_revision()
        child = RevisionService.derive_revision(
            parent=parent,
            project_id=parent.project_id,
            new_content_hash="b" * 64,
            created_by="planner",
            invalidation_intent=InvalidationIntent.INVALIDATE_SHOT_PLAN,
        )
        assert child.parent_revision_id == parent.revision_id
        assert child.revision_id != parent.revision_id

    def test_derive_from_locked_without_intent_rejected(self):
        parent = RevisionService.lock(self._base_revision())
        with pytest.raises(LockedRevisionMutationError):
            RevisionService.derive_revision(
                parent=parent,
                project_id=parent.project_id,
                new_content_hash="c" * 64,
                created_by="planner",
            )

    def test_locked_revision_immutable(self):
        rev = self._base_revision()
        locked = RevisionService.lock(rev)
        assert locked.locked is True
        assert RevisionService.is_locked(locked)


class TestValidatorRules:
    def test_valid_package_has_no_issues(self):
        issues = VideoProductionPackageValidator.validate(build_valid_package())
        assert issues == []

    def test_missing_id_detected(self):
        issues = VideoProductionPackageValidator.validate_dict(build_invalid_missing_id())
        assert any(i.code == "MISSING_ID" for i in issues)

    def test_duplicate_id_detected(self):
        issues = VideoProductionPackageValidator.validate_dict(build_invalid_duplicate_id())
        assert any(i.code == "DUPLICATE_ID" for i in issues)

    def test_broken_reference_detected(self):
        issues = VideoProductionPackageValidator.validate_dict(build_invalid_broken_reference())
        assert any(i.code == "BROKEN_REFERENCE" for i in issues)

    def test_unordered_shot_detected(self):
        issues = VideoProductionPackageValidator.validate_dict(build_invalid_unordered_shot())
        assert any(i.code == "UNORDERED_SHOT" for i in issues)

    def test_asset_missing_hash_detected(self):
        issues = VideoProductionPackageValidator.validate_dict(build_invalid_asset_missing_hash())
        assert any(i.code == "ASSET_MISSING_HASH" for i in issues)

    def test_mutation_after_lock_detected(self):
        issues = VideoProductionPackageValidator.validate_dict(build_invalid_mutation_after_lock())
        assert any(i.code == "LOCKED_REVISION_MUTATION" for i in issues)


class TestApprovalTargetHash:
    def test_approval_points_to_locked_revision_hash(self):
        pkg = build_valid_package()
        # Lock with approval matching the CURRENT content hash → valid
        locked = pkg.model_copy(update={"approvals": pkg.approvals.model_copy(update={"locked": True})})
        # current approvals' target_hash intentionally differs from content_hash in fixture;
        # re-point to actual content hash to prove validity.
        from windagent_core.domain.video_production.approval import ApprovalDecision
        from windagent_core.domain.video_production.ids import ApprovalId

        approval = ApprovalDecision(
            approval_id=ApprovalId("appr_valid"),
            project_id=str(pkg.project_id),
            revision_id=pkg.revision_id,
            target_hash=pkg.content_hash(),
            actor="reviewer-1",
            decision=ApprovalDecisionType.APPROVED,
        )
        locked = locked.model_copy(
            update={"approvals": locked.approvals.model_copy(update={"approvals": [approval]})}
        )
        assert VideoProductionPackageValidator.validate(locked) == []


class TestEventEnvelope:
    def test_event_envelope_validation(self):
        env = VideoProductionEventEnvelope(
            event_type=VideoProductionEventCatalog.PROJECT_CREATED,
            project_id=VideoProjectId("vp_01"),
            revision_id=ProductionRevisionId("rev_01"),
            aggregate_id="vp_01",
        )
        assert env.event_id
        assert env.schema_version == "1.0.0"

    def test_event_envelope_unknown_type_rejected(self):
        with pytest.raises(Exception):
            VideoProductionEventEnvelope(
                event_type="video_production.unknown",
                project_id=VideoProjectId("vp_01"),
                revision_id=ProductionRevisionId("rev_01"),
                aggregate_id="vp_01",
            )
