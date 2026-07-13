# ADR 0001: Three-Level Model Pinning Architecture

## Status
Accepted

## Context
In a multi-agent system, using a single global model for all agents is inefficient and inflexible. Conversely, allowing agents or the router to dynamically change models or fall back to different model families mid-run can cause unpredictable behavior, incompatibilities with prompt templates, and tool-calling protocol failures. We need a reliable mechanism to pin models while still allowing provider failover (e.g., switching from OpenRouter to Anthropic Bedrock for the same Claude model) and respecting agent-specific capabilities.

## Decision
We will implement a three-level model pinning (locking) hierarchy:

### 1. Conversation Lock
Established upon the first user request in a conversation. It locks:
- The canonical model for the **Hermes Orchestrator**.
- The routing policy version.
- The default permission mode (e.g., standard, safe, autonomous).
- The set of allowed provider candidates for each canonical model.
- The context compaction policy.

### 2. Parent-Task Lock
Created when a parent task is instantiated. It inherits the conversation's general policies but freezes:
- The task plan version (`plan_version`).
- Required capabilities for this task.
- Concurrency limit and budget constraints.
- Allowed agent types.
- The snapshot of available models.

Any modification to a running plan must generate a new `plan_version` rather than updating the running DAG in-place.

### 3. Agent-Session Lock
Every sub-agent is assigned a canonical model exactly once when spawned.
- For example:
  - Coder Agent $\rightarrow$ `qwen3-coder-480b`
  - Browser Agent $\rightarrow$ `gemini-2.5-pro`
  - Orchestrator $\rightarrow$ `claude-3-5-sonnet`
- **Wind Router Invariant**: The router is strictly bound to the canonical model. It may rotate/failover between provider bindings (e.g., from Bedrock to OpenRouter for `claude-3-5-sonnet` if Bedrock returns HTTP 429), but **cross-model fallback is disabled by default**.

## Consequences
- **Predictability**: Prompt templates and tool protocols remain stable throughout an agent's session lifecycle.
- **Resilience**: The system can survive provider outages without degrading capabilities or switching to a less capable model.
- **Auditability**: All routing attempts and model assignments are explicitly logged against a specific lock version.
