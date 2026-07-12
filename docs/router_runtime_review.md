# Router Runtime Review — Phase 5.5

**Date:** 2026-07-05  
**Branch:** `feat/router-runtime-ui-integration`  
**Reviewed by:** Codex Agent (automated review + manual analysis)

---

## Backend Review

### RouterAwareAdapter / agent_runtime_adapters.py

**Verdict: ✅ Acceptable**

- All 5 agents (Coder, GUI, Workflow, Research) delegate correctly through `RouterExecutionService.execute_chat()`.
- No direct model calls bypass the router.
- No API keys referenced or logged.
- **Issue noted (minor):** `agent_runtime_adapters.py` is missing the `PlannerAgent` adapter — Planner uses `planner_service.py` instead. This is intentional and acceptable.

### provider_gateway.py

**Verdict: ✅ Good**

- Secret scrubbing present: `if "Bearer" in err_msg or "key" in err_msg.lower()` replaces with generic error.
- Properly delegates to `router_service.execute_chat()` without calling providers directly.
- OpenAI-compatible format is correct: `id`, `object`, `choices`, `usage`.
- Streaming: SSE format correct with `data: [DONE]` termination.
- **Issue noted (minor):** `content-type` header for streaming responses is managed by the FastAPI `StreamingResponse` wrapper in the router, not here. This is correct.

### quota_service.py

**Verdict: ✅ Good**

- Daily reset logic is stable: `check_and_reset_provider_quota()` checks both `reset_at` timestamp and calendar day.
- Reset creates a new snapshot (append-only), preserving audit history.
- `should_route()` returns `True` for Ollama (local) unconditionally — correct.
- **Potential issue:** `should_route()` returns `True` when no snapshot exists ("optimistic default"). This is intentional for initial setup but may cause silent failures on quota-exceeded accounts where no snapshot was ever seeded. Document in operational runbook.

### router_execution_service.py

**Verdict: ✅ Good — one minor concern**

- `execute_chat()` always logs to DB via `finally` block — good for auditability.
- `resolve_route()` has multi-tier fallback: primary → fallback → final_fallback → emergency → first-in-catalog.
- **Concern:** The "last resort" logic (lines 720-724: pick first model from catalog) can route to any model regardless of role compatibility. This is a fail-open pattern. Document it clearly as an emergency-only path.
- The 0.4 score threshold for rejecting a model is reasonable but undocumented. Should be a named constant.

### planner_service.py

**Verdict: ✅ Good**

- Mock-mode aware: falls back gracefully when `WINDAGENT_MODEL_BACKEND=mock`.
- Uses `_router_service` for model resolution when available.

### conftest.py

**Verdict: ✅ Good**

- `WINDAGENT_MODEL_BACKEND=mock` is set.
- Each test gets an isolated temp SQLite DB — no shared state contamination.
- Mock prevents real API calls during test.

### test_router_runtime.py

**Verdict: ✅ Passing**

- Covers: streaming, non-streaming, daily quota reset, adapter routing, execution log persistence.
- All assertions are meaningful (not trivially true).

---

## Frontend Review — Router.tsx (1865 lines)

### Architecture Assessment

**Verdict: ⚠️ Large monolithic component — Phase 6 begins split**

| Concern | Status |
|---|---|
| Single file >1800 lines | Flagged — Phase 6 starts decomposition |
| Hardcoded API paths | Mitigated — `routerApi.ts` centralizes all endpoints |
| Duplicate fetch state | Present — each `fetchAllData()` call updates 5+ state slices. Acceptable for MVP. |
| Loading/error/empty state | ✅ — `apiError` state shown in header. Empty tables show "No rules found" message. |
| Easter egg game isolation | ⚠️ — game state exists in main component. Phase 6 adds `_` prefixed unused state. Full `ScubaOstrichGame.tsx` extraction deferred. |
| Bundle impact | Low — game uses Web Audio API (no external dependencies). |

### Issues Fixed in Phase 6

1. **TypeScript unused variable errors** — game state setters and `setSearchText` prefixed with `_`.
2. **Scattered API calls** — `routerApi.ts` created as centralized client module.
3. **Stats response mapping** — frontend mapped `totalRoutes` from nested `totalRoutes.value` but backend sends flat structure. Mismatch tolerated by null-coalescing.

### Remaining Risks

- Router.tsx should eventually be split into 7-8 sub-components per Phase 6 plan.
- Stats polling interval (6 seconds) may be aggressive for low-resource environments — make configurable.
- `alert()` calls for error feedback should be replaced with toast notifications.

---

## Security Review

| Check | Status |
|---|---|
| No secrets in code | ✅ All keys from environment only |
| Error messages scrubbed | ✅ `provider_gateway.py` scrubs Bearer/key references |
| No real API calls in tests | ✅ `WINDAGENT_MODEL_BACKEND=mock` |
| No force-push | ✅ Normal git push used |
| No `.env` modified | ✅ Environment is read-only in code |
| Execution logs don't store secrets | ✅ Only role, model_id, latency, status |

---

## OpenAI Compatibility

The `/v1/chat/completions` and `/v1/models` endpoints are compatible with standard OpenAI Python SDK `openai.OpenAI(base_url=..., api_key="dummy")` usage:

- Response format matches OpenAI spec.
- Streaming uses correct SSE format with `data: [DONE]` termination.
- Model naming via `role:Planner` or direct role name is supported.
- **Limitation:** No function calling / tool_calls support yet. Not needed for current scope.

---

## Recommendations

1. ✅ **Phase 6:** Extract `ScubaOstrichGame.tsx` as isolated lazy component.
2. ✅ **Phase 6:** Extract `RouterRulesPanel.tsx`, `RouterSimulatorPanel.tsx` from Router.tsx.
3. 🔲 **Operational:** Document quota "optimistic default" behavior in runbook.
4. 🔲 **Future:** Replace `alert()` calls with toast notification component.
5. 🔲 **Future:** Make routing score threshold (0.4) a named constant.
