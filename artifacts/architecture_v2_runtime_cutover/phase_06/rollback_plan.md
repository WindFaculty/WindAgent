# Phase 6 rollback plan

Phase 6 is recoverable from base commit
`7fb0340edf711a2b2c864265e30ae9b284de1d66` and the exact paths recorded in
`deleted_files_manifest.json`.

## Preferred rollback

1. Keep the canonical API, Worker, CLI, storage, provider, and orchestration
   packages as the runtime.
2. If an unknown external launcher is discovered, add a minimal, separately
   packaged compatibility entrypoint that delegates only to
   `windagent_api.main:app`.
3. Do not restore legacy routers, services, provider registries, worker startup,
   database initialization, or business logic.
4. Add a contract test for the external launcher and remove the compatibility
   entrypoint after its announced window.

## Investigative file recovery

An individual deleted file can be inspected with:

```text
git show 7fb0340edf711a2b2c864265e30ae9b284de1d66:<path>
```

Recover files on a separate branch. Do not re-add `apps/backend` to the root
workspace, Python path, CI runtime, or desktop launcher.

## Database safety

Runtime rollback does not authorize a destructive schema downgrade. Preserve
all user data, take a database backup before any schema operation, and use a
forward repair migration if a canonical schema issue is found.

## Validation after rollback

Re-run the architecture checker, Phase 6/V1/V2 contracts, full Python suite,
desktop and web tests/builds, and all three isolated package import probes.
