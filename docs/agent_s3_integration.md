# Agent-S3 integration status

The former Agent-S3 integration was part of the retired Architecture V1
implementation. Its adapter, setup helper, routes, and runtime dependencies are
not available in the Architecture V2 production runtime.

This document is retained as a compatibility notice so old links do not imply
that the removed installer or endpoints are still supported.

Reintroducing this capability requires a new canonical package design with:

- an explicit execution port and adapter;
- permission and secret-redaction contracts;
- no dynamic import from `external/`;
- API V2 routes and migrated regression tests;
- architecture, isolation, and clean-install evidence.

Historical implementation and test receipts remain in the repository's
artifact history and are not authoritative runtime documentation.
