# Plan B to Plan C Contract

Contract version: `studio.contract/v0.1`; artifact schema version: `studio.artifact/v1alpha1`.

## B provides

- JSON-schema-compatible content models for all Story artifacts, score dimensions, validation issues, review findings, revision diffs, and locked screenplay package.
- Presentation-safe artifact summaries plus full typed views where authorized.
- Quality/continuity/format/duration/production-feasibility signals with stable codes, severity, locations, and suggested actions.
- Approval checkpoint labels, candidate selection requirements, revision reasons, and prompt/model provenance fields intended for display.
- Golden fixtures for the Vietnamese rabbit-and-kite vertical slice, including invalid and stale cases; generated final content is never committed as a hardcoded production response.

## C provides back

- API representation mapping that preserves B schema versions and discriminators.
- Schema-generated TypeScript types, state reducers, and UI views for candidate comparison, bible/canon, beats/outline, screenplay, review findings, revision diff, approval, and lock receipt.
- UI commands containing exact artifact hash, revision/version, candidate/checkpoint identity, and idempotency key.
- Accessibility, localization-safe rendering, long-content behavior, and contract snapshots.

## Invariants at the seam

1. C does not reproduce B’s Pydantic/domain schema manually; generation or checked mapping tests are mandatory.
2. A candidate can be selected only from the current `IdeaCandidateSet` and exact hash.
3. Review findings keep stable machine codes; translated labels do not become domain values.
4. A revision diff is computed from immutable artifact/revision pairs; UI local edits cannot mutate the server’s locked artifact.
5. Lock UI submits the reviewed screenplay hash and displays the server-issued receipt. It cannot synthesize `READY_FOR_PRODUCTION`.
6. Prompt/provider provenance is visible in diagnostics/evidence but secrets and raw private reasoning are not exposed.

## Contract tests and handoff gate

- All golden fixtures validate in Python and TypeScript.
- Unknown future artifact fields are preserved or safely ignored according to the versioning rule; unknown discriminator values show an explicit unsupported state.
- Empty, malformed, long Vietnamese, and stale-revision fixtures render without fake defaults.
- `STORY_ARTIFACT_CONTRACT_GATE` freezes B schemas before C’s real screens leave fixture mode.
- `REAL_VERTICAL_SLICE_GATE` proves displayed content originates from persisted B artifacts created by real worker/provider execution.

Breaking changes require a schema-version bump, regenerated clients/fixtures, and both plan-owner approvals.
