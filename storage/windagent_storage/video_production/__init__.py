"""
Content-addressed artifact storage + invalidation (plan 05 Phase 18,
gate VP18_ARTIFACT_INVALIDATION_VERIFIED).

Extends the existing storage package with a content-addressed artifact
pipeline — it does NOT create a parallel storage authority (plan 05 §3, §4):

- model.py        — ArtifactRecord (§12) + statuses, append-only history;
- key.py          — pinned-version full content key (§13);
- store.py        — ContentAddressedStore + ArtifactRecordStore (atomic);
- graph.py        — ArtifactDependencyGraph (§14.2) with minimal-scope queries;
- invalidation.py — ArtifactInvalidationService (§14.3), never deletes;
- publisher.py    — atomic publish pipeline (§14.1) + ArtifactAvailable event;
- reuse.py        — ArtifactReusePolicy (§14.4) full-key + hash-valid reuse.
"""

from windagent_storage.video_production.model import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactApprovalStatus,
    ArtifactRecord,
    ArtifactStatus,
    ArtifactType,
    ArtifactValidationStatus,
    new_artifact_id,
)
from windagent_storage.video_production.key import (
    ARTIFACT_KEY_VERSION,
    canonicalize_input,
    compute_artifact_key,
    key_matches,
    key_version_of,
)
from windagent_storage.video_production.store import (
    ArtifactRecordStore,
    ContentAddressedStore,
)
from windagent_storage.video_production.graph import (
    GRAPH_SCHEMA_VERSION,
    ArtifactDependencyEdge,
    ArtifactDependencyGraph,
    ArtifactDependencyType,
    build_bgm_scope,
    build_character_scope,
)
from windagent_storage.video_production.invalidation import (
    INVALIDATION_SCHEMA_VERSION,
    ArtifactInvalidationService,
    InvalidationChange,
    InvalidationChangeType,
    InvalidationResult,
)
from windagent_storage.video_production.publisher import (
    ArtifactAvailableEvent,
    ArtifactPublisher,
    DecodeValidatorPort,
    EventJournal,
    PublishRequest,
    PublishResult,
)
from windagent_storage.video_production.reuse import (
    ArtifactReusePolicy,
    ReuseDecision,
    ReuseVerdict,
)
from windagent_storage.video_production.ir_invalidation import (
    IR_INVALIDATION_SCHEMA_VERSION,
    IrInvalidationResult,
    IrTrackInvalidationService,
)

__all__ = [
    # model
    "ARTIFACT_SCHEMA_VERSION",
    "ArtifactType",
    "ArtifactStatus",
    "ArtifactValidationStatus",
    "ArtifactApprovalStatus",
    "ArtifactRecord",
    "new_artifact_id",
    # key
    "ARTIFACT_KEY_VERSION",
    "canonicalize_input",
    "compute_artifact_key",
    "key_matches",
    "key_version_of",
    # store
    "ContentAddressedStore",
    "ArtifactRecordStore",
    # graph
    "GRAPH_SCHEMA_VERSION",
    "ArtifactDependencyType",
    "ArtifactDependencyEdge",
    "ArtifactDependencyGraph",
    "build_character_scope",
    "build_bgm_scope",
    # invalidation
    "INVALIDATION_SCHEMA_VERSION",
    "InvalidationChangeType",
    "InvalidationChange",
    "InvalidationResult",
    "ArtifactInvalidationService",
    # publisher
    "ArtifactPublisher",
    "PublishRequest",
    "PublishResult",
    "ArtifactAvailableEvent",
    "EventJournal",
    "DecodeValidatorPort",
    # reuse
    "ArtifactReusePolicy",
    "ReuseDecision",
    "ReuseVerdict",
    # IR track-scoped invalidation (VP3D Stage A Phase 2)
    "IR_INVALIDATION_SCHEMA_VERSION",
    "IrInvalidationResult",
    "IrTrackInvalidationService",
]
