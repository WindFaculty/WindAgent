"""Harness Assembler for Continual Harness (Phase 10 — ban_ke_hoach_v1 §15).

Combines the immutable base system prompt with active supplemental harness entries
(prompt rules, memory references, skill references, subagent specs, and routing policies)
into an authoritative runtime execution context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_core.domain.harness import HarnessEntryKind, HarnessVersion


@dataclass(frozen=True)
class AssembledHarnessContext:
    """Immutable snapshot of the assembled system prompt and execution context."""
    full_system_prompt: str
    base_prompt: str
    prompt_rules: List[str]
    memory_refs: List[Dict[str, Any]]
    skill_refs: List[Dict[str, Any]]
    subagent_specs: List[Dict[str, Any]]
    routing_policies: List[Dict[str, Any]]
    harness_version_id: str
    harness_version_number: int
    entry_count: int
    estimated_tokens: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class HarnessAssembler:
    """Assembles immutable base prompt and supplemental harness entries into executable context."""

    DEFAULT_BASE_PROMPT = (
        "You are WindAgent, a production-grade autonomous agent architecture. "
        "Adhere strictly to all security, validation, and domain invariants."
    )

    @classmethod
    def assemble(
        cls,
        base_prompt: Optional[str] = None,
        harness_version: Optional[HarnessVersion] = None,
        project_id: Optional[str] = None,
        domain: Optional[str] = None,
        extra_memories: Optional[List[Dict[str, Any]]] = None,
        extra_skills: Optional[List[Dict[str, Any]]] = None,
    ) -> AssembledHarnessContext:
        """Assembles base prompt and versioned harness state into complete runtime context."""
        effective_base = (base_prompt or cls.DEFAULT_BASE_PROMPT).strip()

        if not harness_version:
            # Baseline harness v0 with no supplemental entries
            return AssembledHarnessContext(
                full_system_prompt=effective_base,
                base_prompt=effective_base,
                prompt_rules=[],
                memory_refs=list(extra_memories or []),
                skill_refs=list(extra_skills or []),
                subagent_specs=[],
                routing_policies=[],
                harness_version_id="baseline_v0",
                harness_version_number=0,
                entry_count=0,
                estimated_tokens=cls._estimate_tokens(effective_base),
            )

        # Filter enabled entries matching scope and domain
        active_entries = [
            e for e in harness_version.entries
            if e.enabled
            and (e.scope == "global" or not project_id or e.scope == "project")
            and (not domain or not e.metadata.get("domain") or e.metadata.get("domain") == domain)
        ]

        # Sort by priority ascending (lower number = higher priority)
        active_entries.sort(key=lambda e: e.priority)

        prompt_rules: List[str] = []
        memory_refs: List[Dict[str, Any]] = list(extra_memories or [])
        skill_refs: List[Dict[str, Any]] = list(extra_skills or [])
        subagent_specs: List[Dict[str, Any]] = []
        routing_policies: List[Dict[str, Any]] = []

        for entry in active_entries:
            if entry.kind == HarnessEntryKind.PROMPT_RULE:
                rule_text = entry.content.get("rule") or entry.content.get("text") or str(entry.content)
                if rule_text:
                    prompt_rules.append(f"[{entry.name}]: {rule_text}")

            elif entry.kind == HarnessEntryKind.MEMORY_REF:
                mem_payload = dict(entry.content)
                mem_payload["entry_id"] = entry.entry_id
                mem_payload["name"] = entry.name
                memory_refs.append(mem_payload)

            elif entry.kind == HarnessEntryKind.SKILL_REF:
                skill_payload = dict(entry.content)
                skill_payload["entry_id"] = entry.entry_id
                skill_payload["name"] = entry.name
                skill_refs.append(skill_payload)

            elif entry.kind == HarnessEntryKind.SUBAGENT_SPEC:
                subagent_specs.append(
                    {
                        "entry_id": entry.entry_id,
                        "name": entry.name,
                        "spec": entry.content,
                    }
                )

            elif entry.kind == HarnessEntryKind.ROUTING_POLICY:
                routing_policies.append(
                    {
                        "entry_id": entry.entry_id,
                        "name": entry.name,
                        "policy": entry.content,
                    }
                )

        # Build full composite system prompt
        prompt_parts = [effective_base]

        if prompt_rules:
            prompt_parts.append("\n\n### Supplemental Operating Rules (Harness):")
            for rule in prompt_rules:
                prompt_parts.append(f"- {rule}")

        if skill_refs:
            prompt_parts.append("\n\n### Active Skill Capabilities:")
            for sk in skill_refs:
                desc = sk.get("description", sk.get("name", "skill"))
                prompt_parts.append(f"- {sk.get('name', 'skill')}: {desc}")

        if memory_refs:
            prompt_parts.append("\n\n### Active Memory & Context References:")
            for mem in memory_refs:
                summary = mem.get("summary") or mem.get("content") or mem.get("name", "memory")
                prompt_parts.append(f"- {mem.get('name', 'memory')}: {summary}")

        full_prompt = "\n".join(prompt_parts)

        return AssembledHarnessContext(
            full_system_prompt=full_prompt,
            base_prompt=effective_base,
            prompt_rules=prompt_rules,
            memory_refs=memory_refs,
            skill_refs=skill_refs,
            subagent_specs=subagent_specs,
            routing_policies=routing_policies,
            harness_version_id=harness_version.version_id,
            harness_version_number=harness_version.version_number,
            entry_count=len(active_entries),
            estimated_tokens=cls._estimate_tokens(full_prompt),
            metadata={
                "project_id": project_id,
                "domain": domain,
                "harness_parent_version": harness_version.parent_version,
            },
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Heuristic token estimator (approx ~4 chars per token)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

