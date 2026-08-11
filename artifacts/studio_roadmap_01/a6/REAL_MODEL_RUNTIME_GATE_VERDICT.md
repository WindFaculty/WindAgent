# REAL_MODEL_RUNTIME_GATE — A6 verdict

- Contract: studio.contract/v0.1
- Gate: REAL_MODEL_RUNTIME_GATE
- Verdict: **PASS**

## Checks

- PASS — handler_invokes_real_route_through_coordinator
- PASS — route_provenance_persisted
- PASS — receipt_redaction_safe
- PASS — route_lock_deterministic
- PASS — error_taxonomy_typed
- PASS — capability_report_honest
- PASS — certification_fails_closed
- PASS — provider_smoke_opt_in
- PASS — model_route_test_suite_passes
- PASS — architecture_checker_green

## Scope

- RouteLockedModelPort is the real PreproductionModelPort: every Story completion
  locks a canonical model through RouteLockService (deterministic scope per
  capability+prompt; explicit route_lock_id wins) and executes through
  EndpointExecutionCoordinator (same-model failover, cooldowns, attempt audit).
- A worker Story handler (studio.story.idea.generate) crossed the full path:
  durable envelope -> StudioRuntimeAdapter -> B handler -> route lock ->
  coordinator -> provider, and the artifact envelope persisted complete route
  provenance (model_route_id, provider_id, model_id, prompt_id, usage).
- Provider failures map into typed retryability (transient/quota/auth/schema/
  safety/terminal/unknown) with explicit retryable flags; no silent fallback
  and no mock bypass — disabled models and exhausted endpoints propagate.
- WorkerRuntimeCapabilityProbe reports durable DB, queue, outbox, worker, real
  model route, Blender, story engine, and future engines with source/reason/
  timestamp; env variables are compatibility inputs, not hidden policy.
- Certification profile fails closed on fake runtime, fixture model port, and
  non-durable model route; the real port carries no fixture marker.
- Real-provider smoke is opt-in (WINDAGENT_PROVIDER_SMOKE=1); gate evidence uses
  a controlled provider stub outside certification (A5/A6 rule).

Evidence JSON: `artifacts/studio_roadmap_01/a6/evidence.json`
Generated: 2026-08-11T01:28:59.304243+00:00
