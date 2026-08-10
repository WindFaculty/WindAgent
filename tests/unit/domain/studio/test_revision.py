"""A2 domain tests: revision immutability, derivation, and stale-write guards.

Property-style checks over the canonical content hash (order-independence,
collision-freedom on distinct content) plus derivation/lock invariants:
stale parent rejection, locked-parent derivation, derive-after-lock,
lock immutability, and serialization round trips.
"""

import json

import pytest

from windagent_core.contracts.studio.errors import (
    StudioArtifactHashMismatchError,
    StudioLockedRevisionError,
    StudioStaleRevisionError,
    StudioValidationError,
)
from windagent_core.contracts.studio.ids import (
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
)
from windagent_core.domain.studio.revision import (
    StudioInvalidationIntent,
    StudioLockState,
    StudioProductionRevision,
    StudioRevisionService,
    StudioRevisionStatus,
    canonical_content_hash,
)

SERIES = SeriesProjectId.generate("ser")
EPISODE = EpisodeId.generate("ep")


def _revision(**overrides) -> StudioProductionRevision:
    base = dict(
        revision_id=ProductionRevisionId.generate("rev"),
        series_id=SERIES,
        episode_id=EPISODE,
        creator="alice",
        actor="alice",
        content_hash="a" * 64,
    )
    base.update(overrides)
    return StudioProductionRevision(**base)


# ---- canonical hash properties -------------------------------------------------


def test_hash_is_order_independent():
    content_a = {"b": 1, "a": [3, 2, 1]}
    content_b = {"a": [3, 2, 1], "b": 1}
    assert canonical_content_hash(content=content_a) == canonical_content_hash(
        content=content_b
    )


def test_hash_is_deterministic_and_sha256_hex():
    h = canonical_content_hash(content={"k": "v"})
    assert len(h) == 64
    assert h == canonical_content_hash(content={"k": "v"})


def test_hash_differs_for_distinct_content():
    assert canonical_content_hash(content={"k": 1}) != canonical_content_hash(
        content={"k": 2}
    )


def test_hash_embeds_schema_version():
    assert canonical_content_hash(
        content={}, schema_version="studio.artifact/v1alpha1"
    ) != canonical_content_hash(content={}, schema_version="studio.artifact/v2")


# ---- derivation invariants -----------------------------------------------------


def test_derive_creates_child_lineage():
    parent = _revision()
    child = StudioRevisionService.derive_revision(
        parent=parent,
        series_id=SERIES,
        episode_id=EPISODE,
        new_content_hash="b" * 64,
        creator="alice",
    )
    assert child.parent_revision_id == parent.revision_id
    assert child.series_id == SERIES
    assert child.episode_id == EPISODE
    assert child.optimistic_version == 0
    assert child.state == StudioRevisionStatus.DRAFT


def test_derive_rejects_stale_parent_version():
    parent = _revision(optimistic_version=3)
    with pytest.raises(StudioStaleRevisionError):
        StudioRevisionService.derive_revision(
            parent=parent,
            series_id=SERIES,
            episode_id=EPISODE,
            new_content_hash="b" * 64,
            creator="alice",
            expected_parent_version=2,
        )


def test_derive_from_locked_requires_invalidation_intent():
    locked = _revision(lock_state=StudioLockState.LOCKED)
    with pytest.raises(StudioLockedRevisionError):
        StudioRevisionService.derive_revision(
            parent=locked,
            series_id=SERIES,
            episode_id=EPISODE,
            new_content_hash="b" * 64,
            creator="alice",
        )
    with pytest.raises(StudioLockedRevisionError):
        StudioRevisionService.derive_revision(
            parent=locked,
            series_id=SERIES,
            episode_id=EPISODE,
            new_content_hash="b" * 64,
            creator="alice",
            invalidation_intent=StudioInvalidationIntent.NONE,
        )


def test_derive_after_lock_is_the_only_mutation_path():
    locked = _revision(lock_state=StudioLockState.LOCKED)
    child = StudioRevisionService.derive_revision(
        parent=locked,
        series_id=SERIES,
        episode_id=EPISODE,
        new_content_hash="b" * 64,
        creator="alice",
        invalidation_intent=StudioInvalidationIntent.DOWNSTREAM,
    )
    assert child.parent_revision_id == locked.revision_id
    assert child.invalidation_intent == StudioInvalidationIntent.DOWNSTREAM


def test_derive_rejects_malformed_content_hash():
    with pytest.raises(StudioValidationError):
        StudioRevisionService.derive_revision(
            parent=_revision(),
            series_id=SERIES,
            episode_id=EPISODE,
            new_content_hash="short",
            creator="alice",
        )


def test_derive_is_fresh_draft_even_from_locked_parent():
    locked = _revision(lock_state=StudioLockState.LOCKED)
    child = StudioRevisionService.derive_revision(
        parent=locked,
        series_id=SERIES,
        episode_id=EPISODE,
        new_content_hash="b" * 64,
        creator="alice",
        invalidation_intent=StudioInvalidationIntent.DOWNSTREAM,
    )
    assert child.lock_state == StudioLockState.UNLOCKED
    assert not child.locked


# ---- lock invariants -----------------------------------------------------------


def test_lock_rejects_stale_hash():
    rev = _revision(content_hash="a" * 64)
    with pytest.raises(StudioArtifactHashMismatchError):
        StudioRevisionService.lock_revision(
            revision=rev, expected_content_hash="b" * 64
        )


def test_lock_rejects_stale_version():
    rev = _revision(optimistic_version=5)
    with pytest.raises(StudioStaleRevisionError):
        StudioRevisionService.lock_revision(revision=rev, expected_version=4)


def test_lock_is_immutable_copy_and_bumps_version():
    rev = _revision()
    locked = StudioRevisionService.lock_revision(revision=rev)
    assert rev.lock_state == StudioLockState.UNLOCKED  # original untouched
    assert locked.locked
    assert locked.state == StudioRevisionStatus.LOCKED
    assert locked.optimistic_version == rev.optimistic_version + 1


def test_lock_is_idempotent_when_already_locked():
    locked = _revision(lock_state=StudioLockState.LOCKED, status=StudioRevisionStatus.LOCKED)
    again = StudioRevisionService.lock_revision(revision=locked)
    assert again.optimistic_version == locked.optimistic_version


def test_locked_revision_remains_immutable():
    rev = _revision()
    locked = StudioRevisionService.lock_revision(revision=rev)
    assert locked.model_config.get("frozen") is True
    with pytest.raises(ValueError):
        locked.content_hash = "c" * 64  # type: ignore[misc]


# ---- stale-write guard ---------------------------------------------------------


def test_write_guard_rejects_stale_version_and_hash():
    rev = _revision(optimistic_version=2)
    with pytest.raises(StudioStaleRevisionError):
        StudioRevisionService.record_stale_write_guard(revision=rev, expected_version=1)
    with pytest.raises(StudioArtifactHashMismatchError):
        StudioRevisionService.record_stale_write_guard(
            revision=rev, expected_content_hash="f" * 64
        )


def test_write_guard_passes_on_fresh_state():
    rev = _revision(optimistic_version=2)
    StudioRevisionService.record_stale_write_guard(
        revision=rev, expected_version=2, expected_content_hash=rev.content_hash
    )  # no raise


# ---- serialization round trips -------------------------------------------------


def test_compat_dump_round_trip():
    rev = _revision(
        parent_revision_id=ProductionRevisionId.generate("rev"),
        summary="round trip",
        metadata={"k": "v"},
        invalidation_intent=StudioInvalidationIntent.DOWNSTREAM,
    )
    dumped = rev.model_dump_json_compat()
    assert dumped["revision_id"] == str(rev.revision_id)
    assert dumped["parent_revision_id"] == str(rev.parent_revision_id)
    assert dumped["invalidation_intent"] == "DOWNSTREAM"
    assert dumped["optimistic_version"] == rev.optimistic_version


def test_pydantic_round_trip_is_lossless():
    rev = _revision(metadata={"nested": {"x": [1, 2]}}, summary="s")
    restored = StudioProductionRevision.model_validate(rev.model_dump())
    assert restored == rev
    assert restored.model_dump() == rev.model_dump()


def test_canonical_hash_round_trip_stable_across_json_encodings():
    content = {"nested": {"x": [1, 2]}, "text": "héllo"}
    h1 = canonical_content_hash(content=content)
    h2 = canonical_content_hash(content=json.loads(json.dumps(content)))
    assert h1 == h2
