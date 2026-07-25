# Phase 5 verdict

PASS

Gate: `CANONICAL_CONTRACT_OWNERSHIP_UNIFIED`

Evidence:
- New canonical structure created: `core/windagent_core/contracts/providers/`
  (requests, responses, usage, capabilities, ports) and
  `core/windagent_core/contracts/tools/` (invocation, results, metadata, ports).
- Old structures deleted with NO compatibility re-export:
  `core/windagent_core/providers/`, `core/windagent_core/tools/` (pydantic duplicate),
  `providers/windagent_providers/base/ports.py`.
- Duplicate ToolInvocation/ToolResult eliminated: dataclass shape is the single
  canonical contract; removed from `core/windagent_core/domain/models.py`; pydantic
  copy deleted. `ToolInvocation.arguments` alias preserves permission-engine duck-typing.
- Capability/descriptor schemas (ProviderCapabilities, ModelDescriptor, QuotaState,
  RateLimitState, ProviderHealth, DiscoveredModel, ConnectionTestResult,
  ProtocolDetectionResult, CacheDirective, ProviderStreamEvent, FinishReason) moved to
  `contracts/providers/capabilities.py` — implementation-independent.
- Provider ports (EndpointRegistryPort, CanonicalModelRegistryPort, RouteLockPort,
  RouteAttemptPort, QuotaStatePort, EndpointStatePort, CachePort, UsageLedgerPort)
  moved to `contracts/providers/ports.py` as runtime_checkable Protocols (was ABC).
- Tool ports (ToolExecutorPort, ToolRegistryPort) added in `contracts/tools/ports.py`.
- Tool metadata (ToolDefinition, ToolExecutionContext, ToolRiskLevel) moved to
  `contracts/tools/metadata.py`; tools package keeps BaseTool ABC only.
- 40+ import sites updated across providers/, tools/, storage/, apps/backend/, tests/.
- Duplicate-model scanner: `scripts/check_duplicate_canonical_models.py` detects by
  semantic name + field signature; exits non-zero on duplicate fixture (tested),
  passes on real tree (546 files).
- `configs/architecture/scaffold_v2.yaml` canonical_models extended with all new
  provider/tool contract names; architecture checker PASS (0 violations).
- Ownership rule verified: `windagent_core.contracts.*` imports nothing outside core;
  providers/tools import contracts from core only.
- Tests: 6/6 new phase-5 tests pass; full suite 539 passed / 9 failed — identical to
  Phase 2/3 pre-existing baseline.
