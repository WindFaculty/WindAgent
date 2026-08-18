# Architecture & Production Risk Register

| Risk ID | Description | Severity | Mitigation & Guardrail | Status |
| :--- | :--- | :--- | :--- | :--- |
| **RSK-001** | Legacy V2 endpoints re-introduced by mistake | HIGH | `scripts/audit_architecture_rules.py` (Rule F004) + deliberate 410 Gone tombstone router in `main.py` | **MITIGATED** |
| **RSK-002** | Direct untyped `fetch()` calls creeping into UI components | MEDIUM | `scripts/audit_architecture_rules.py` (Rule F003) + mandatory `@windagent/api-client` usage | **MITIGATED** |
| **RSK-003** | Platform coupling between Web and Desktop | HIGH | PlatformAdapter architecture (Phase 14) + Rule F001, F002, F006 | **MITIGATED** |
| **RSK-004** | Runtime mock or synthetic data leaks | MEDIUM | Zero synthetic fixtures in production code + Rule F007 | **MITIGATED** |
| **RSK-005** | Broken deep links / unregistered routes | LOW | Single authoritative `routeManifest.ts` + Rules F008, F009 | **MITIGATED** |
