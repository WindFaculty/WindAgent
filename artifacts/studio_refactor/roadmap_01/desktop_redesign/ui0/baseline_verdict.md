# UI0 — BASELINE & REDESIGN CONTRACT — VERDICT

Phase: Desktop Redesign Roadmap UI0
Date: 2026-08-13
Branch: `chore/cleanup-stale-md-docs` @ `b36e84f`
Gate: **WIND_STUDIO_UI0_BASELINE_FROZEN — PASS**

---

## UI0.1 Freeze baseline

Frozen at commit `b36e84f` (branch `chore/cleanup-stale-md-docs`, 13 ahead / 0 behind origin).
Working tree carries pre-existing cleanup-branch WIP (staged deletions of dead e2e tests,
test renames) + the UI0 changes from this session. Nothing else committed.

| Surface | Result |
|---|---|
| Desktop tests (`apps/desktop` vitest) | 14 files / 144 tests PASS (was 13/142; +apiBase.test.ts) |
| Frontend packages vitest (6 packages) | 59 tests PASS |
| Web vitest (`apps/web`) | 6 files / 70 tests PASS |
| Desktop typecheck (`tsc -b --noEmit`) | PASS |
| Desktop build (`tsc -b && vite build`) | PASS (569.92 kB main chunk; >500 kB warning pre-existing) |
| Web typecheck | PASS (was FAIL at HEAD, see UI0-INFRA-02) |
| Web build | PASS (was FAIL at HEAD) |
| Studio deep-link tests | `src/test/studioShellTests.test.tsx` (inside desktop suite) |
| Studio story tests | `src/test/studioStoryTests.test.tsx` (30 tests, inside desktop suite) |
| Production package tests | `src/test/productionPackageTests.test.ts` + production-* package suites |

Backend studio pytest suites (contracts / domain / v3 api) untouched — UI0 does not
reach the runtime.

### Defects found and fixed during freeze

- **UI0-INFRA-01 — divergent API base defaults** (see UI0.3).
- **UI0-INFRA-02 — `apps/web` build red at HEAD**: `apps/web/src/app/App.tsx` re-exports
  the desktop App via `@desktop` alias, but the web `tsconfig.json` never gained the
  `paths` entry; desktop sources also use ES2022-only APIs (`.at()`) and a dynamic
  `@tauri-apps/api` import. CI `web-test` (typecheck + build) has been red since
  `a210883`. Fixed: tsconfig `paths` + ES2022 target/lib + `@tauri-apps/api` devDependency.

Out of scope, recorded: `apps/web/src/clients/*` and `frontend/packages/production-client`
still default to `localhost:8000` — dead code / never instantiated in app src; not touched.

---

## UI0.2 Frozen behavior contracts

These semantics are the redesign contract. Any future UI phase that changes them
breaks the baseline; UI1+ must preserve them exactly.

### Commands (StudioPage → StudioStore → HttpStudioApiClient → /api/v3/studio)

| Command | Frozen semantics |
|---|---|
| `createSeries` | POST /api/v3/studio/series with `X-Idempotency-Key`. Key `studio_series_${crypto.randomUUID()}` minted per click; never auto-retried by client (caller replay = new click = new key). Success: navigate `#/studio/series/<id>`. |
| `createEpisode` | POST /api/v3/studio/series/<id>/episodes. Key `studio_episode_*`. Success: navigate `#/studio/episodes/<id>`. |
| `startRun` | POST /api/v3/studio/episodes/<id>/runs. Key `studio_run_*`. Server returns `{run_id, resuming}`; resuming flag means continue, not restart. |
| `selectIdea` | POST .../idea-selection. Body = candidate from the SERVED IdeaCandidateSet: `{candidate_id, revision_id, expected_content_hash, expected_optimistic_version}` — hash/version taken from the served artifact envelope + episode, never synthesized. Key `studio_idea_*`. |
| `submitApproval` | POST .../approvals. `artifact_hash` = current revision's `content_hash` from server; `revision_id` from `current_revision.revision_id ?? current_revision_id ?? revision_id`; decision ∈ {APPROVED, REJECTED, REQUEST_REVISION}; reason optional; `expected_optimistic_version` from episode. Key `studio_approval_*`. Missing revision/hash → error "No current revision on server to approve.", no request sent. |
| `lockScreenplay` | POST .../screenplay-lock with `expected_content_hash` = current revision content hash + `expected_optimistic_version`. Key `studio_lock_*`. Locked episodes render read-only (`READ_ONLY_STATES = {LOCKED, READY_FOR_PRODUCTION}`). |

### Store semantics (StudioStore)

| Contract | Frozen behavior |
|---|---|
| Server authority | Store never advances a stage / marks artifact durable on its own. All mutations go through API; state refreshes from server responses. |
| Optimistic state | Limited to a PENDING marker (`pendingCommands` set) on the in-flight command. A refresh that disagrees with pending state wins. No optimistic durable completion. |
| Idempotency key | Owned by the caller, stable across retries of the same command attempt; store never mints a new key for a replayed command. Client never auto-retries POSTs (safe caller replay with same key). |
| Conflict handling | `STALE_REVISION` / `ARTIFACT_HASH_MISMATCH` / `LOCKED_REVISION` → `StoreErrorKind.conflict`, stores `{episode_id, code, details}`, reloads episode from server; UI shows "Stale revision conflict — server state refreshed below." |
| Error mapping | CAPABILITY_UNAVAILABLE/PROVIDER_UNAVAILABLE → capability_unavailable; NOT_FOUND → not_found; VALIDATION_ERROR/INVALID_TRANSITION/APPROVAL_REQUIRED/IDEMPOTENCY_MISMATCH → validation; network/timeout → network (retryable); unknown schema → unsupported_schema (never blank/synthesized view). |
| Polling | `pollRun`: immediate first tick then `setInterval` 2000 ms default; each tick: GET run → GET events `?after=<cursor>`; cursor advances ONLY from server `next_after` (even on empty pages); stops on terminal statuses {COMPLETED, FAILED, CANCELLED}; returns stop function. |
| Cursor persistence | `sessionStorage['studio.eventCursors']` (StudioPage `CURSOR_STORAGE_KEY`): hydrate once on mount, serialize on `beforeunload`. Corrupt snapshot → start fresh. |
| Deep-link hydration | Route authority = URL hash: `#/studio`, `#/studio/series/<id>`, `#/studio/episodes/<id>`. `parseHash` on mount + `hashchange` listener; each route change re-fetches from server (series list, episodes, episode+artifacts). Refresh/deep-link always rehydrates from server, no client-only state. |
| Capabilities | Loaded from GET /api/v3/studio/capabilities; UI shows statuses for durable_db, studio_orchestration, story_engine, worker, model_route; fail-closed surfaced as capability_unavailable. |
| Polling lifecycle | `stopPolling(runId)` / `stopAllPolling()`; poll replaced per run (`pollRun` stops existing). |

### Client rules (HttpStudioApiClient)

- Base URL: single authority (UI0-INFRA-01) `API_BASE`; default `http://127.0.0.1:8765`, override `VITE_API_BASE`.
- Timeout 15 000 ms default → `StudioTimeoutError` (AbortController).
- GETs may retry once on network failure; POSTs never retried.
- POST headers: `Content-Type: application/json`, `X-Idempotency-Key`, optional `X-WindAgent-Actor`.
- Error payloads map to typed `StudioApiError` (code/status/retryable/details/correlation_id); non-JSON error body → `StudioNetworkError`.

---

## UI0.3 Canonical API base investigation

| Source | Value before UI0 | Authority? |
|---|---|---|
| `scripts/dev_api.ps1` | backend binds `127.0.0.1:8765` | canonical backend port |
| vite dev proxy (desktop + web) | `/api` → `http://127.0.0.1:8765` (strips /api), `/ws` → `ws://127.0.0.1:8765` | dev canonical |
| `scripts/healthcheck.ps1` / `run.ps1` | `127.0.0.1:8765` | canonical |
| `apps/desktop/src/api/client.ts` | hardcoded `http://127.0.0.1:8765` | matched, but hardcoded |
| `apps/desktop/src/pages/StudioPage.tsx` | default `http://localhost:8000` | **DIVERGENT** — wrong port, bypasses proxy |
| `apps/desktop/src/lib/routerApi.ts` | default relative `""` | **DIVERGENT** — dead in Tauri production (no dev server) |
| `VITE_API_BASE` env | honored by StudioPage + routerApi only | canonical override knob |
| CI (`ci.yaml`) | no VITE_API_BASE set anywhere; desktop/web build without it | default path |
| Certification | only C7 cert script sets `VITE_API_BASE=http://127.0.0.1:8765` | workaround, not config |

**Target reached: ONE DESKTOP API BASE AUTHORITY.**
New module `apps/desktop/src/lib/apiBase.ts` exports `API_BASE` / `WS_BASE`
(`VITE_API_BASE` override → default `http://127.0.0.1:8765` / `ws://127.0.0.1:8765`).
All three divergent sites now import from it. Dedicated test: `src/lib/apiBase.test.ts`
(default + override cases). Behavior identical when no env override is set.

---

## Gate

```text
WIND_STUDIO_UI0_BASELINE_FROZEN = PASS
```

- Baseline frozen (commit, branch, status, test matrix, build matrix, dependency snapshot).
- Behavior contracts recorded (UI0.2) — redesign must not change semantics.
- API base single authority implemented + tested (UI0-INFRA-01).
- Pre-existing web build breakage fixed (UI0-INFRA-02) so the baseline is actually green.
- No changes to studio-contracts / studio-client / studio-state / API v3 / worker / story runtime.
