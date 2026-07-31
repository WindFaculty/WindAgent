# Versioning Policy — Video Production Protocol

## Schema versioning

`schema_version` follows `MAJOR.MINOR.PATCH`:

```text
MAJOR — incompatible change (fail closed)
MINOR — additive compatible feature
PATCH — compatible fix / clarification
```

## Fail-closed rule

Unknown **MAJOR** versions are rejected at parse time:

```text
validate_package_major("2.0.0")  → raises UnsupportedMajorVersionError
```

No silent interpretation, no downgrade path, no fallback to a guessed schema.

## Additive compatibility

Within the same MAJOR, **additive compatible fields** are allowed:

- New optional fields may be added.
- Existing optional fields may not become required.
- Existing required fields may not be removed or renamed.
- New enum values are additive unless semantics change.

Pydantic models use `extra="allow"` so forward-compatible fields survive a
round trip.

## Process

1. A schema change proposal is authored with revision context.
2. Compatibility tests (additive fields, unknown major rejection) run in CI.
3. Only after evidence passes may a new MINOR/PATCH ship; a new MAJOR is a new
   protocol generation with explicit migration notes.

## Events

Event envelopes carry their own `schema_version`; the same fail-closed MAJOR
rule applies to `video_production.*` event types.

## Authority

`road_map.md` Phase 3 and this document. Conflicts resolve in favor of the
roadmap and approved ADRs.
