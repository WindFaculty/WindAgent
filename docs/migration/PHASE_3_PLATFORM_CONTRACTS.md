# Phase 3 â€” platform contracts

Date: 2026-09-01

## Scope delivered

Phase 3 fixes the domain-agnostic seams on which feature modules and later
runtime phases will depend. Every contract is handwritten in
`backend/src/windagent/platform/` and uses only the standard library plus
existing kernel primitives; no legacy code, feature module, web framework,
ORM, provider SDK, or queue implementation is imported.

| Package | Canonical contract |
| --- | --- |
| `commands` | `Command`, `CommandHandler`, `CommandBus` |
| `queries` | `Query`, `QueryHandler`, `QueryBus` |
| `modules` | `ModuleDescriptor`, `ModuleRegistry` |
| `jobs` | `JobSubmission`, `JobReceipt`, `JobHandler`, `JobQueue`, `JobScheduler` |
| `events` | `EventHandler`, `EventSubscription`, `EventBus`, `EventPublisher` |
| `persistence` | `UnitOfWork` |
| `artifacts` | `ArtifactReference`, `ArtifactStore` |
| `security` | `SecretStore`, `PolicyEngine`, and ALLOW/DENY/REQUIRE_APPROVAL policy data |
| `observability` | `Telemetry`, `TelemetrySpan` |

`ArtifactReference`, `JobSubmission`, and policy/module data are immutable and
validate JSON payloads at the boundary. `SecretValue` deliberately redacts
normal string representations, so plaintext access remains explicit.

## Deliberately deferred

- Phase 4: `ModuleManifest`, discovery, validation, and registration runtime.
- Phase 5: SQLAlchemy/PostgreSQL `UnitOfWork` implementation and repositories.
- Phase 6: event registry, outbox, dispatcher, subscriptions, and replay.
- Phase 7: durable queue claim/lease/fencing/retry/cancellation and the full
  `JobEnvelope`.
- Phases 9-10: identity/authn/authz/secret adapters and concrete telemetry
  exporters.

No product concept such as Episode, Agent, Model, Recording, Studio, or
provider has entered the platform boundary.

## Gates

- Unit tests provide small in-memory implementations for every public protocol
  and verify immutable boundary values.
- The architecture suite now requires each Phase 3 contract package to import
  only the standard library or `windagent.kernel`, in addition to the existing
  ban on feature-module and application imports.
