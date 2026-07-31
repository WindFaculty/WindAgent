# Revision and Locking — Video Production Protocol

Source: `core/windagent_core/domain/video_production/project.py`

## Model

```text
ProductionRevision
├── revision_id            stable opaque ID
├── parent_revision_id     previous revision (nil for the first)
├── created_at             UTC timestamp
├── created_by             actor identity
├── content_hash           SHA-256 of the package's canonical serialization
├── status                 DRAFT | LOCKED
├── locked                 bool flag
├── invalidation_intent    NONE | INVALIDATE_SHOT_PLAN | INVALIDATE_GENERATION
│                          | INVALIDATE_ASSETS | INVALIDATE_ALL
└── change_summary         human-readable note
```

## Immutability contract

1. Every revision is immutable (Pydantic `frozen=True`).
2. A **locked** revision cannot be mutated and cannot be re-derived without an
   explicit `InvalidationIntent`; attempts raise `LockedRevisionMutationError`.
3. Screenplay changes **must** declare a downstream invalidation intent.
4. Approvals always point to a specific `revision_id` + `target_hash`.

## Workflow

```text
derive_revision(parent, ...)
    parent.locked == False  → new revision (parent chain preserved)
    parent.locked == True
        invalidation_intent declared → new revision (invalidates downstream)
        no intent / NONE            → LockedRevisionMutationError

lock(revision) → locked copy (immutable; a NEW object, never in-place)
```

## Downstream invalidation intent

`InvalidationIntent` values map to the roadmap invalidation graph:

```text
NONE                    → no downstream invalidation
INVALIDATE_SHOT_PLAN    → cinematic/shot plans are stale
INVALIDATE_GENERATION   → generation candidates are stale
INVALIDATE_ASSETS       → reference assets are stale
INVALIDATE_ALL          → everything downstream is stale
```

## Validation enforcement

`VideoProductionPackageValidator` verifies a locked package's approval
`target_hash` matches the package's current `content_hash`. A mismatch is
reported as `LOCKED_REVISION_MUTATION`, proving the artifact was not silently
mutated after lock.

## Approval semantics

- Approval records: actor, role, decision, reason, timestamp, target hash.
- Approval always binds to a specific revision + content hash.
- Idempotent: duplicate approvals for the same hash are not created.
