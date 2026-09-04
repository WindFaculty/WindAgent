# Phase 11 — Model Gateway

Date: 2026-09-02

## Scope delivered

REWRITE of the frozen `providers/*` routing authority plus
`intelligence/model_router/*`, into `backend/src/windagent/modules/model_gateway`
(migration matrix `modules.model_gateway`, action REWRITE).  The duplicate
legacy scoring authority (`intelligence/model_router/policy.py`, base score
100 / +50 preferred / mock fallback) is deliberately NOT carried over — the
module is the single routing authority (plan section 17).

| Capability | Implementation |
| ---------- | -------------- |
| Registry | providers, endpoints, write-only credentials, canonical catalog, endpoint↔model bindings, discovery reconciliation (add/update/unchanged/unavailable — never deletes) |
| Routing rules | durable versioned rules, priority-ascending first-match, AND/ANY-OF predicates, carried `fallback_model_id` |
| Route locks | durable locks with one ACTIVE lock per scope (partial unique index CAS), fast-path reuse, release, reselection, pinned fallback locks (P0.3.5 semantics) |
| Endpoint selection | frozen filter chain (exact-revision → enabled → credential fail-closed with ollama exemption → cooldown/circuit) and the deterministic component-sum score |
| Failover / retry | frozen decision matrix (429/quota → failover; 5xx/network/timeout → retry-once-then-failover; auth → failover + credential flag; 404 → stale binding; overflow/invalid/cancel → stop), five-attempt budget |
| Circuit breaker | 3 consecutive failures → open, 30 s half-open window, success closes, cooldowns only extend |
| Cooldowns | `Retry-After` parse (1.0 s default, 300 s ceiling) and bounded exponential backoff `min(1.0·2^n, 300)` |
| Quota | durable per-provider quota state, optimistic `has_quota` default, feeds endpoint scoring |
| Health | discovery-probe `HealthReport` per adapter |
| Receipts | durable `model_gateway_receipts` (old P0.3.6 semantics), write-best-effort, never breaks routing |
| Events | `model_gateway.route.locked/reused/released`, `model_gateway.model.reselected`, `model_gateway.route.fallback` recorded through the transactional outbox atomically with the lock change |
| Provider protocols (EXTRACT_LOGIC) | OpenAI-compatible transport (+ OpenAI/OpenRouter/Mistral/NVIDIA thin vendors), Anthropic Messages, Google `generateContent`, Ollama shim (streamed generation, `num_ctx` default payload, response-format suppression); normalized requests/responses/usage/streams; SSE parsing with tool-call delta accumulation; error taxonomy ported verbatim |
| API | `/api/v4/model-gateway/*` — providers CRUD, credential rotate/remove (write-only), endpoints, models, rules CRUD, route simulate, active/lookup locks, invocations, receipts |
| Jobs | `model_gateway.invoke` job handler so the future agent runtime reaches the gateway through the platform job seam (cross-module imports stay forbidden) |
| Secrets | durable `EncryptedSecretStore` (AES-256-GCM, `enc:v<version>:…` envelope, `WINDAGENT_MODEL_GATEWAY_ENCRYPTION_KEY`, fail-closed) chained with the read-only environment store; no plaintext at rest and no read path in any response |

## Architecture

```text
HTTP /api/v4/model-gateway/*   worker job model_gateway.invoke
        ↓                              ↓
   Command/Query buses          InvokeModelJobHandler
        ↓                              ↓
        └──────────┬───────────────────┘
                   ↓
   ModelGateway (single authority)
   lock routing → endpoint selection → failover loop → receipts
                   ↓
   TransactionScope (platform UnitOfWork + TransactionalOutbox)
                   ↓
   SqlModelGatewayStore (model_gateway_* tables, Alembic 0005)
```

Handlers are manifest-declarative and resolve collaborators through the
ambient `ModelGatewayServices` scope, so `PackageModuleDiscovery` finds the
module with no bootstrap edits (plan section 7).  Secrets are revealed only
inside the adapter-resolution boundary.

## Gates

Current local evidence:

```text
Ruff                        PASS
mypy strict                 PASS (module + tests)
unit tests                  PASS (offline, in-memory store + mocked HTTP)
parity tests                PASS (frozen oracles from WindAgent commit 01695ca4)
contract tests              PASS (write-only credential contract, policy, errors)
PostgreSQL integration      PASS (migration chain incl. 0005, lock CAS race,
                            failover persistence, receipts, outbox events,
                            encrypted secret round trip)
architecture gates          PASS (no legacy imports, no cross-module imports,
                            no SQLite defaults)
```

Parity oracles are frozen in `tests/parity/test_model_gateway_parity.py`:
normalization fingerprints, equivalence levels/confidences/eligibility,
score-component sums (6.0 healthy / 5.0 quota-exhausted), the binding filter
chain, the failover decision matrix, backoff/`Retry-After` formulas, and
rule-matching semantics.  The intentional V2 change (single authority, no
`intelligence/model_router` duplicate) is documented there.

## Out of scope (deferred by plan)

- Response cache / singleflight (not listed in the Phase 11 REWRITE set).
- Google Live API and the Universal Asset Gateway (separate concerns in the
  frozen tree, unrelated to routing authority).
- Frontend `model-gateway` module (Phase: frontend modules).
