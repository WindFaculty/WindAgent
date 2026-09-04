# Phase 2 — Kernel

Date: 2026-09-01

## Scope delivered

The kernel is a clean-room, standard-library-only library at
`backend/src/windagent/kernel`. It contains no legacy import, framework,
database, HTTP client, provider, module, or application dependency.

| Area | Public contracts |
| --- | --- |
| IDs | `EntityId`, `EventId`, `ActorId`, `CorrelationId`, `CausationId` |
| Errors/results | `DomainError`, `ValidationError`, `Result[T]` |
| Time | `Clock`, `SystemClock`, `FrozenClock`, UTC normalization |
| Value types | `Money` (`Decimal` only), `Version`, immutable JSON values |
| Events | `DomainEvent`, `EventEnvelope` |

## Contract decisions

- UUID identifiers are nominal types: the same UUID is not equal across
  `EntityId`, `ActorId`, and correlation/causation identifiers. Their stored
  representation is a canonical UUID string.
- `Result[T]` has exactly one state. Failures carry `DomainError`, ensuring a
  later API or worker layer can map expected errors consistently without
  importing its transport into the kernel.
- All kernel timestamps are timezone-aware and normalized to UTC. `FrozenClock`
  makes behavior deterministic for unit and replay scenarios.
- `Money` rejects floats and implicit rounding. Currency-specific rounding is a
  module policy, not a kernel concern.
- `EventEnvelope` fixes the Phase 6 metadata shape early: event identity/type/
  version, aggregate identity/type/sequence, actor/correlation/causation,
  occurrence time, and a recursively immutable JSON payload. It deliberately
  contains no event bus, outbox, serializer framework, or persistence code.

## Verification

`tests/unit/test_kernel.py` verifies value-object invariants and result/event
behavior. `tests/architecture/test_import_boundaries.py` additionally enforces
that every kernel source file uses only standard-library imports plus relative
kernel imports.

Parity and integration are not applicable: this phase introduces generic V2
primitives and intentionally does not migrate a legacy business capability or
connect to infrastructure.
