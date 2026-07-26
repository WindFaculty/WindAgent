# Phase 1 — Risk Register

| Risk ID | Description | Impact | Severity | Mitigation | Status |
|---|---|---|---|---|---|
| R1-01 | In-memory fallback accidentally used in production | High | Medium | App and Worker composition roots explicitly inject `SQLEndpointBindingRepository`, `SQLRouteLockRepository`, and `SQLProviderRoutingAuditRepository`. In-memory store logs explicit warning. | MITIGATED |
| R1-02 | Concurrent lock creation under high load | High | High | Partial unique index `uq_route_locks_v3_active_scope` on DB enforces single active lock per (scope_type, scope_id). Concurrent requests reload existing lock when insert conflicts. | MITIGATED |
| R1-03 | Model drift on HTTP 429 failover | Medium | High | `RouteLockRecord.canonical_model_id` is immutable. Endpoint failover reuses the exact canonical model and only selects an alternative endpoint binding. | MITIGATED |
| R1-04 | Migration schema incompatibility across SQLite and PostgreSQL | Medium | Medium | Migration script `phase1_routing_authority.py` uses SQLAlchemy inspector and conditional ALTER TABLE statements safe for both SQLite and PostgreSQL. | MITIGATED |
