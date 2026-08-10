# Plan A to Plan B Contract

Contract version: `studio.contract/v0.1`.

## A provides

- Canonical IDs and aggregate relationships for `SeriesProject`, creative `Episode`, and `ProductionRevision`.
- Episode lifecycle, approval policy/checkpoint primitives, immutable artifact envelope, canonical hashing, and lock/derive rules.
- Repository/UoW ports for aggregates, artifacts, approvals, and revision lineage.
- `StudioTaskEnvelope`, `StudioTaskResult`, task registry interface, durable submission, run correlation, retry/fencing behavior, and completion reconciliation.
- Versioned Studio event envelope/catalog and transactional outbox boundary.
- Infrastructure-composed `PreproductionModelPort` backed by route lock and endpoint coordination, returning route/model/usage provenance.
- Typed runtime capability query; a fail-closed signal when a real provider or required durable dependency is unavailable.

## B provides back

- Artifact `content` schemas and validators for every Story artifact type.
- Task handler implementations for the nine frozen Story task types.
- Required-capability declarations per task, versioned prompt IDs/hashes, structured model schemas, quality results, retry classification, and redaction rules.
- Domain-safe revision proposals and `LockedScreenplayPackage` assembly; no persistence or orchestration implementation leak.
- Contract tests that A can run against the worker registry and repository adapters.

## Invariants at the seam

1. B never imports SQLAlchemy/storage adapters, API models, worker composition, or legacy orchestration engines.
2. A never embeds Story prompts, scoring weights, screenplay parsing, or review policy content.
3. All handler inputs and outputs are serializable under the frozen envelope and preserve correlation, revision, artifact hashes, and route provenance.
4. Retrying the same task is idempotent; it may reuse an already persisted artifact only when all input hashes, prompt hash, schema version, and model-route lock match.
5. A stale/expired fencing token cannot persist an artifact or advance a run.
6. A locked screenplay cannot be overwritten. B requests derivation through A’s revision port.

## Contract tests and handoff gate

- Consumer fixtures round-trip through A serializers and B validators.
- Every frozen task type is registered exactly once; unknown task types fail closed.
- Schema-invalid provider output is rejected or repaired according to a bounded, observable policy; it never becomes a canonical artifact silently.
- Crash after artifact write but before finalization recovers without duplicate artifact or double run advance.
- `SCREENPLAY_RUNTIME_GATE` requires real A queue/worker/finalizer plus B handler execution for at least generation, review, revision, and lock.

Breaking changes require a version bump, updated fixtures, both plan-owner approvals, and an integration note; they may not be merged as an incidental implementation edit.
