# ADR-0014: Milestone 4 User Platform Ecosystem, Unified Migration & Complete System Cutover

- **Status**: Accepted
- **Date**: 2026-09-02
- **Deciders**: WindAgent V2 Core Architecture Team
- **Context**: Milestone 4 of the Clean-Room Reimplementation Plan (`ban_ke_hoach.md`)

---

## 1. Context and Problem Statement

With Milestones 1 (Kernel & Platform Infrastructure), 2 (Core Modules: Workspace, Model Gateway, Automation, Agent Runtime, Memory), and 3 (Production Capabilities: Studio, Production, Live Record, Quality) 100% complete and certified green, the final milestone requires establishing the complete user platform:
1. Modern frontend monorepo (`@windagent/api-sdk`, `@windagent/ui`, `@windagent/realtime`, `@windagent/app`) providing end-to-end user interfaces across all 9 bounded contexts.
2. Native Desktop supervisor and IPC recording adapter (`apps/desktop`).
3. Clean data migration importers and parity test suites (`migration/`).
4. End-to-end integration test coverage (`tests/e2e/`).
5. Production container deployment with multi-stage Dockerfiles and compose orchestration.
6. Formal retirement of the legacy codebase and production cutover certification.

---

## 2. Decision Outcomes

1. **Frontend Architecture**:
   - Built a modular TypeScript ecosystem with strict typing (`@windagent/api-sdk`).
   - Created a design system (`@windagent/ui`) with dark-theme glassmorphism, responsive data tables, DAG visualization (`GraphViewer`), and metric cards.
   - Built single page application routing with tabs and interactive workflows across all 9 domain modules.

2. **Native Desktop Platform**:
   - Implemented `DesktopSupervisor` with graceful lifecycle management.
   - Implemented `NativeRecordingAdapter` preserving WGC and NVENC acceleration while enforcing tokenized path isolation (`tokenized://...`) and fail-closed hardware probing.

3. **Data Migration Pipeline**:
   - Created unified `MigrationRunner` with transactional idempotency, dry-run validation, and RBAC mapping.
   - Implemented automated parity tests in `migration/parity/test_migration_parity.py`.

4. **E2E Test Suites**:
   - Built test suites verifying every bounded context and the full platform user journey without ORM leaks or cross-module boundary violations.

5. **Production Deployment**:
   - Multi-stage Docker images (`Dockerfile.api`, `Dockerfile.worker`, `Dockerfile.frontend`).
   - Nginx reverse proxy with gzip, CSP, and WebSocket upgrade.
   - Orchestrated multi-service `compose.prod.yaml` with automated health checks.

6. **Cutover & Retirement**:
   - Formally designated `WindAgent` legacy repository as read-only frozen archive.
   - WindAgent V2 is canonical and production ready.

---

## 3. Invariants Enforced

1. **Zero Legacy Imports**: No module or app in V2 imports from old `WindAgent` packages.
2. **Strict Module Boundaries**: All 9 bounded contexts interact exclusively through platform contracts.
3. **Canonical PostgreSQL Persistence**: ACID transactions with row-level locks, outbox events, and idempotency keys.
