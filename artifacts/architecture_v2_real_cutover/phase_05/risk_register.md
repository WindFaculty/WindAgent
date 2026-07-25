# Phase 5 risk register

1. RISK: ToolInvocation contract unified to dataclass shape (id/params); pydantic shape
   (invocation_id/arguments) removed. MITIGATION: permission engine already duck-typed
   both (`arguments or params`); `arguments` alias property added to canonical
   ToolInvocation. Only test_phase10 used the pydantic kwargs — updated.
2. RISK: Provider capability dataclasses moved from providers/base/contracts.py to core.
   MITIGATION: base/contracts.py re-exports them; base/__init__.py re-exports from core;
   no provider-internal import sites changed beyond ports.
3. RISK: BaseTool ToolDefinition/ToolExecutionContext/ToolRiskLevel moved to core
   contracts. MITIGATION: tools/windagent_tools/base.py re-exports from core; 15 tool
   modules unchanged except import source (still `tools.base`).
4. RISK: BaseModelProvider (ABC, providers/base/provider.py) intentionally left in
   providers — it is an implementation base class, not a core contract. Out of phase scope.
5. RISK: Pre-existing 9 test failures unchanged. Verified identical to Phase 2/3 baseline.
6. RISK: providers/pyproject.toml version was 2.0.0 (Phase 6 scope item) — aligned to
   0.3.0 to satisfy workspace version consistency rule.
