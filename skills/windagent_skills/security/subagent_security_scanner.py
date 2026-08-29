"""Subagent Security and Policy Scanner (Phase 13 — ban_ke_hoach_v1 §19, §29).

Performs static analysis and policy auditing on proposed Subagent candidates:
1. Tool Authorization & Forbidden Tool Detection:
   - Blocks unauthorized dangerous/host tools (system_bash, eval_code, host_exec, steal_tokens, raw_socket).
   - Validates tools against registered tool catalog when provided.
2. Skill Whitelist Validation:
   - Validates requested skills against active registered skill inventory.
3. Memory Scope Boundary Enforcement:
   - Ensures memory access scopes are bounded.
   - Disallows unapproved GLOBAL write access without explicit elevation.
4. Prompt Injection & Jailbreak Detection:
   - Scans system_supplement for adversarial instructions, bypass patterns, and data exfiltration directives.
   - Detects embedded secrets and access tokens.
5. Budget & Recursion Depth Ceilings:
   - Enforces max_depth <= 5.
   - Enforces reasonable max_turns (<= 200) and max_cost_usd (<= $100).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from windagent_core.domain.subagent_evolution import (
    MemoryScope,
    SubagentCandidate,
    SubagentRiskLevel,
    SubagentSecurityAuditResult,
)


FORBIDDEN_TOOLS: Set[str] = {
    "system_bash",
    "host_exec",
    "eval_code",
    "execute_arbitrary_shell",
    "privilege_escalate",
    "steal_tokens",
    "raw_socket_tool",
    "os_system_tool",
    "credential_dump",
}

PROMPT_INJECTION_PATTERNS = [
    (re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior)\s+(instructions|prompts|rules)"), "Prompt Injection: Ignore Previous Instructions"),
    (re.compile(r"(?i)bypass\s+(security|safety|filter|guardrail)"), "Adversarial Directive: Bypass Security"),
    (re.compile(r"(?i)you\s+are\s+now\s+(in\s+)?(sudo|root|god|dan|unrestricted)\s+mode"), "Jailbreak: Privilege Escalation Persona"),
    (re.compile(r"(?i)(exfiltrate|leak|transmit)\s+(secrets|passwords|credentials|keys)"), "Exfiltration Directive"),
    (re.compile(r"(?i)drop\s+table|delete\s+from\s+chat_sessions|truncate\s+table"), "SQL Injection In Prompt"),
]

SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key"),
    (re.compile(r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----"), "Private Key"),
    (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"), "OpenAI/API Secret Token"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "GitHub Personal Access Token"),
]


class SubagentSecurityScanner:
    """Audits subagent candidates against security policies, tool restrictions, and prompt safety."""

    def __init__(
        self,
        max_allowed_depth: int = 5,
        max_allowed_cost_usd: float = 100.0,
        max_allowed_turns: int = 200,
    ) -> None:
        self.max_allowed_depth = max_allowed_depth
        self.max_allowed_cost_usd = max_allowed_cost_usd
        self.max_allowed_turns = max_allowed_turns

    def audit(
        self,
        candidate: SubagentCandidate,
        registered_tools: Optional[List[str]] = None,
        registered_skills: Optional[List[str]] = None,
    ) -> SubagentSecurityAuditResult:
        """Executes a full security audit on a subagent candidate."""
        spec_dict = candidate.proposed_spec or {}
        violations: List[str] = []
        details: Dict[str, Any] = {
            "tool_violations": [],
            "skill_violations": [],
            "memory_violations": [],
            "prompt_violations": [],
            "budget_violations": [],
            "depth_violations": [],
        }

        # 1. Tool Permissions Audit
        tool_passed = True
        allowed_tools = spec_dict.get("allowed_tools", [])
        if not isinstance(allowed_tools, list):
            tool_passed = False
            v = "allowed_tools must be a list of strings."
            violations.append(v)
            details["tool_violations"].append(v)
        else:
            for tool in allowed_tools:
                tool_str = str(tool).strip()
                if tool_str.lower() in FORBIDDEN_TOOLS:
                    tool_passed = False
                    v = f"Tool [{tool_str}] is in the forbidden dangerous tools blacklist."
                    violations.append(v)
                    details["tool_violations"].append(v)
                elif registered_tools is not None and tool_str not in registered_tools:
                    tool_passed = False
                    v = f"Tool [{tool_str}] is not found in the registered tool catalog."
                    violations.append(v)
                    details["tool_violations"].append(v)

        # 2. Skill Whitelist Audit
        skill_passed = True
        allowed_skills = spec_dict.get("allowed_skills", [])
        if not isinstance(allowed_skills, list):
            skill_passed = False
            v = "allowed_skills must be a list of strings."
            violations.append(v)
            details["skill_violations"].append(v)
        else:
            if registered_skills is not None:
                for skill_id in allowed_skills:
                    skill_str = str(skill_id).strip()
                    if skill_str not in registered_skills:
                        skill_passed = False
                        v = f"Skill [{skill_str}] is not found in active registered skill manifests."
                        violations.append(v)
                        details["skill_violations"].append(v)

        # 3. Memory Scope Audit
        memory_passed = True
        mem_dict = spec_dict.get("memory_access", {})
        if isinstance(mem_dict, dict):
            write_scopes = mem_dict.get("allowed_write_scopes", [])
            max_items = mem_dict.get("max_memory_items", 20)

            # Check for unapproved GLOBAL write
            if "GLOBAL" in write_scopes or MemoryScope.GLOBAL in write_scopes:
                if candidate.risk_level != SubagentRiskLevel.CRITICAL and not candidate.is_high_risk:
                    memory_passed = False
                    v = "GLOBAL memory write scope requires explicit HIGH/CRITICAL risk classification and human governance."
                    violations.append(v)
                    details["memory_violations"].append(v)

            if isinstance(max_items, int) and (max_items < 1 or max_items > 100):
                memory_passed = False
                v = f"max_memory_items [{max_items}] out of safe bounds [1, 100]."
                violations.append(v)
                details["memory_violations"].append(v)

        # 4. Prompt Safety & Secret Scanning
        prompt_passed = True
        system_supplement = str(spec_dict.get("system_supplement", "") or "")
        objective = str(spec_dict.get("objective", "") or "")
        combined_text = f"{objective}\n{system_supplement}"

        for pattern, desc in PROMPT_INJECTION_PATTERNS:
            if pattern.search(combined_text):
                prompt_passed = False
                v = f"Prompt safety violation: detected pattern '{desc}'."
                violations.append(v)
                details["prompt_violations"].append(v)

        for pattern, desc in SECRET_PATTERNS:
            if pattern.search(combined_text):
                prompt_passed = False
                v = f"Secret detection: detected exposed '{desc}' in system supplement."
                violations.append(v)
                details["prompt_violations"].append(v)

        # 5. Budget Ceiling Audit
        budget_passed = True
        budget_dict = spec_dict.get("max_budget", {})
        if isinstance(budget_dict, dict):
            max_turns = budget_dict.get("max_turns")
            if max_turns is not None and int(max_turns) > self.max_allowed_turns:
                budget_passed = False
                v = f"Budget max_turns [{max_turns}] exceeds safety limit [{self.max_allowed_turns}]."
                violations.append(v)
                details["budget_violations"].append(v)

            max_cost = budget_dict.get("max_cost_usd")
            if max_cost is not None and float(max_cost) > self.max_allowed_cost_usd:
                budget_passed = False
                v = f"Budget max_cost_usd [${max_cost}] exceeds safety limit [${self.max_allowed_cost_usd}]."
                violations.append(v)
                details["budget_violations"].append(v)

        # 6. Recursion Depth Ceiling Audit
        depth_passed = True
        max_depth = spec_dict.get("max_depth", 2)
        try:
            depth_val = int(max_depth)
            if depth_val < 1 or depth_val > self.max_allowed_depth:
                depth_passed = False
                v = f"max_depth [{depth_val}] is out of bounds [1, {self.max_allowed_depth}]."
                violations.append(v)
                details["depth_violations"].append(v)
        except (ValueError, TypeError):
            depth_passed = False
            v = f"Invalid max_depth value [{max_depth}]."
            violations.append(v)
            details["depth_violations"].append(v)

        # Compute overall risk score and verdict
        overall_passed = (
            tool_passed
            and skill_passed
            and memory_passed
            and prompt_passed
            and budget_passed
            and depth_passed
            and len(violations) == 0
        )

        risk_score = min(1.0, len(violations) * 0.25)

        return SubagentSecurityAuditResult(
            passed=overall_passed,
            tool_permission_passed=tool_passed,
            skill_permission_passed=skill_passed,
            memory_scope_passed=memory_passed,
            prompt_safety_passed=prompt_passed,
            budget_ceiling_passed=budget_passed,
            depth_ceiling_passed=depth_passed,
            violations=violations,
            risk_score=risk_score,
            details=details,
        )

