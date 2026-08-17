# Phase 0 Risk Register & Architectural Vulnerabilities

## Identified Risks & Technical Debt

### 1. Route Authority & Hash Desynchronization (HIGH)
- **Finding**: `App.tsx` manually syncs hashes (`#/dashboard`, `#/studio`, etc.) with `activeTab` state, but only handles 8 tabs while navigation declares 18+ tabs.
- **Impact**: Deep links break or default to blank / wrong tab; back/forward browser history is out of sync.
- **Mitigation Phase**: Phase 4 (TanStack Router migration).

### 2. Handwritten API Client & v2Unavailable Stubs (HIGH)
- **Finding**: `apps/desktop/src/api/client.ts` mixes direct `fetch()`, legacy `/api/v2/*` endpoints, and runtime fallback `v2Unavailable()` exceptions.
- **Impact**: Inconsistent error contracts (`ApiProblem` vs custom JSON vs standard `Error`), unhandled 404/500 errors in UI.
- **Mitigation Phase**: Phase 2 (Unified API V3 foundation) and Phase 3 (OpenAPI generated client).

### 3. Split State Management (MEDIUM)
- **Finding**: Redux Toolkit, Zustand, React Context, and ad-hoc `useState` coexist across desktop apps and frontend packages.
- **Impact**: Duplicate caching of server state, race conditions during tab transitions.
- **Mitigation Phase**: Phase 4 & Phase 6 (TanStack Query for server state + Zustand for local UI state).

### 4. Monolithic CSS & Duplicated Tokens (MEDIUM)
- **Finding**: `apps/desktop/src/styles.css` is ~126 KB with duplicate CSS variable definitions and untyped class selectors.
- **Impact**: Styling inconsistencies between desktop and web builds.
- **Mitigation Phase**: Phase 5 (Design Token extraction & UI primitive package).

### 5. Web App Re-importing Desktop (HIGH)
- **Finding**: `apps/web/src/main.tsx` directly renders desktop `App.tsx` and imports desktop `styles.css`.
- **Impact**: Web bundle carries Tauri dependencies and desktop-specific sidecar code.
- **Mitigation Phase**: Phase 4 (Shared Frontend App shell).
