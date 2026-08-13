# WindAgent Desktop State Management

Evidence: `apps/desktop/src/state/*`, `apps/desktop/src/services/*`, `frontend/packages/studio-state`, `frontend/packages/production-state`.

## Stack (mixed, no single convention)

| Mechanism | Where | State owned |
|---|---|---|
| React `useState` + props | App.tsx (activeTab, metrics, health, expansion flags, refreshInterval) | UI state, routing state, header telemetry |
| `useReducer` (legacy) | state/sessionStore.ts | session chat state (ChatMessage, tool calls, runner snapshot, workflow) — single-session MVP, no persistence |
| Zustand v5 | state/agentSessionStore.ts, state/multiAgentStore.tsx | agent session entities, conversation projections (agent board, task graphs, browser state) |
| React Context | state/theme.tsx | theme (light/dark, localStorage + prefers-color-scheme) |
| Class store (custom) | @windagent/studio-state StudioStore | Studio series/episodes/runs/artifacts/capabilities/event cursors/pending commands/errors |
| Redux Toolkit (unused) | @windagent/production-state | production screenplay/project/binding/recovery slices — NO app importer (dead export) |
| SessionStorage | StudioPage (studio.eventCursors), useConversationId (windagent.conversationId) | cursor persistence, conversation id |
| Singleton managers | services/agentSocketManager.ts, services/conversationSocketManager.ts | WS lifecycle outside React |

## State categories

- UI state: activeTab, expansion, refreshInterval — App.tsx useState.
- Session state: sessionStore reducer (legacy) + agentSessionStore (zustand).
- Project state: production-state slices (dead), ProductionShell local useState (live, fed by fake client).
- Series/episode/story state: StudioStore (live, server-authority).
- Runtime state: App.tsx health booleans + metrics (Tauri IPC or mock).
- Model/provider state: Models page local state via fetchModelsHealth.

## Studio flow (the Roadmap-1-relevant one)

```
API response (HttpStudioApiClient)
  -> StudioStore Maps (server-authority; optimistic = PENDING marker only)
  -> StudioPage local useState mirrors (seriesList/episodes/episode/artifacts/capabilities)
  -> components (RunProgress, ApprovalBar, ArtifactContentView)
```

Mutation flow: page mints idempotency key -> store.runCommand -> client POST -> on success store refreshes -> page re-reads store -> setState. Conflict -> store records conflict + reloads episode; page shows ERROR_LABEL. Event cursor: server `next_after` only, hydrated from sessionStorage on reload.

## Verdict

Studio state layer is production-quality and REUSABLE as-is. Desktop global state is a patchwork: no router store, no query cache, three different state paradigms — redesign should standardize on the StudioStore pattern (plain class store) or migrate to one library, but nothing must change before the redesign task decides.
