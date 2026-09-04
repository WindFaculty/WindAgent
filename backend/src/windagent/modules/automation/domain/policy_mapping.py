"""Policy mapping between ToolRiskLevel and the platform PolicyEngine.

Frozen mapping from old ``windagent_tools.security.permission_engine``:

- ``HIGH_RISK_LEVELS`` (external_network, secret_access, process_execution,
  destructive, privileged) map to ``risk_level=HIGH`` in the evaluation
  request; the rest map to ``LOW``.
- ``HARD_DENY_ACTIONS`` always deny regardless of principal.
- Path-scope violations deny before principal checks.
- Destructive without ``user_approved`` yields ``REQUIRE_APPROVAL`` (the
  frozen destructive-guard rule).
"""

from __future__ import annotations

from .definition import HIGH_RISK_LEVELS, ToolRiskLevel

# Canonical hard-deny list preserved from old permission_engine (audit parity).
HARD_DENY_ACTIONS: frozenset[str] = frozenset(
    {"format_c", "drop_production_db", "exfiltrate_keys", "bypass_auth"}
)

# Tools that MUST go through PolicyEngine per plan section 18.
POLICY_GATED_CAPABILITIES: frozenset[str] = frozenset({"shell", "filesystem", "browser"})
POLICY_GATED_TOOLS: frozenset[str] = frozenset(
    {
        "exec_shell",
        "shell",
        "write_file",
        "filesystem_write",
        "browser_open",
        "browser_click",
        "browser_navigate",
        "open_url",
        "click_xy",
    }
)

# Side effects that always require policy even if tool name not in list
POLICY_GATED_SIDE_EFFECTS: frozenset[str] = frozenset({"process", "filesystem"})


def is_policy_gated(tool_name: str, *, capability: str = "", side_effect_class: str = "") -> bool:
    """Return whether this tool must pass the Policy Engine before execution."""
    lower = tool_name.lower()
    if lower in POLICY_GATED_TOOLS:
        return True
    if capability and capability.lower() in POLICY_GATED_CAPABILITIES:
        return True
    if side_effect_class in POLICY_GATED_SIDE_EFFECTS:
        # filesystem/process side effects are always gated, but read-only filesystem (read_file)
        # has side_effect_class == "none" so it bypasses.
        return side_effect_class in {"process", "filesystem"}
    # Heuristic: shell/browser prefix
    if lower.startswith(("exec_", "shell", "browser_", "open_url", "click_")):
        return True
    return False


def risk_to_policy_level(risk: ToolRiskLevel) -> str:
    """Map ToolRiskLevel to a coarse HIGH/LOW for the platform engine."""
    return "HIGH" if risk in HIGH_RISK_LEVELS else "LOW"


__all__ = [
    "HARD_DENY_ACTIONS",
    "POLICY_GATED_CAPABILITIES",
    "POLICY_GATED_SIDE_EFFECTS",
    "POLICY_GATED_TOOLS",
    "is_policy_gated",
    "risk_to_policy_level",
]
