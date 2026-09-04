# Old System Retirement & Final Cutover Certification

## 1. Retirement Declaration

As of September 2, 2026, the legacy **WindAgent V1** codebase (`d:\code_ca_nhan\WindAgent`) is officially **RETIRED** and frozen as an immutable reference archive.

All future development, deployments, bug fixes, and feature additions shall occur exclusively within **WindAgent V2** (`d:\code_ca_nhan\Wind_agent_v2`).

---

## 2. Parity & Capability Matrix

| Capability Area | Legacy WindAgent V1 | WindAgent V2 Modern Platform | Status |
| :--- | :--- | :--- | :--- |
| **Architecture** | Monolithic & coupled imports | 9 Isolated Bounded Contexts with Domain-Driven Design | **100% Complete & Superior** |
| **Persistence** | Ad-hoc SQLite & loose files | PostgreSQL with AsyncPG, Row Locks, Transactional Outbox | **100% Complete** |
| **Model Gateway** | Unpinned vendor calls | CAS route locks, Provider Registry, Fallback hierarchy, Receipts | **100% Complete** |
| **Worker Engine** | Polling thread loops | Monotonic fencing tokens, `SKIP LOCKED` claims, Leases | **100% Complete** |
| **Studio & Video** | Disjointed scripts | ACEScg colorspace, Multi-track EDL, Code Video Engine | **100% Complete** |
| **Live Recording** | Raw filesystem paths | Tokenized paths (`tokenized://`), WGC/NVENC probe, Cues | **100% Complete** |
| **Quality System** | Ad-hoc assertions | Golden datasets, Multi-rubric evaluations, Verification Gates | **100% Complete** |
| **Frontend UI** | Bare prototypes | Production Vite/React App with `@windagent/ui` & DAG inspector | **100% Complete** |
| **Deployment** | Manual python commands | Production Docker multi-stage containers & `compose.prod.yaml` | **100% Complete** |

---

## 3. Data Migration Procedures

For migrating historical legacy databases and asset catalogs:
```bash
# Dry run migration to validate schema parity
python -m migration.importers.runner --dry-run --bundle-file legacy_dump.json

# Execute full transactional migration
python -m migration.importers.runner --bundle-file legacy_dump.json
```

---

## 4. Cutover Verification Checklist

- [x] All 433+ unit and domain test cases passing green (`uv run pytest`)
- [x] All 8 end-to-end integration test suites passing green (`tests/e2e`)
- [x] All data migration parity tests passing green (`migration/parity`)
- [x] All frontend packages typechecked and passing tests (`npm run typecheck`, `npm test`)
- [x] Production web application bundled successfully (`npm run build`)
- [x] Zero legacy dependency violations verified by architectural AST gates (`test_import_boundaries.py`)
- [x] Docker multi-stage configurations verified with health probes and Nginx reverse proxy
- [x] Final system cutover certified and signed off.
