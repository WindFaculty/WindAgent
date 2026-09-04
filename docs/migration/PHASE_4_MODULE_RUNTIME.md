# Phase 4 — module runtime

Date: 2026-09-01

## Scope delivered

`platform/modules` now supplies the only composition seam for a feature
module. A module publishes a frozen `ModuleManifest` with stable identity,
version, command/query/job registrations, event-handler registrations,
routers, migrations, and capabilities.

`ModuleLoader` always performs the same sequence:

```text
discover → validate whole set → commands → queries → jobs → event handlers
         → routers → migrations → publish module descriptors
```

Validation happens before any registration occurs. It rejects duplicate module
IDs and duplicate owners for command classes, query classes, or job type names;
event handlers remain fan-out by design. `InMemoryModuleRegistry` provides the
deterministic reference implementation of the existing registry protocol.

`PackageModuleDiscovery` scans `windagent.modules` for the convention
`<feature>/manifest.py` exposing `manifest: ModuleManifest`. Adding a feature
package such as `modules/youtube_analytics/manifest.py` needs no API or worker
bootstrap edit. Static discovery is available for deterministic tests and
embedded composition roots.

## Boundaries preserved

- The runtime is standard-library only and imports no FastAPI, Alembic, ORM,
  provider, or legacy implementation.
- Routers and migrations are opaque values at this phase, avoiding a premature
  dependency on the API and persistence layers.
- No product module was added. The existing placeholder module packages are
  not automatically registered until they publish their own manifest.
- Future product work only adds or changes its own module manifest; it does not
  edit `kernel`, `platform/modules`, API bootstrap, or worker runtime.

## Verification

- Unit tests cover manifest validation, deterministic staged registration,
  no-mutation validation failures, package discovery, and malformed manifests.
- Architecture tests continue to enforce platform domain neutrality and prohibit
  any V2 import from the frozen legacy system.
