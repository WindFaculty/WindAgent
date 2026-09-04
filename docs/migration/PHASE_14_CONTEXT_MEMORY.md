# Phase 14: Context Assembly Engine & Memory Bounded Context

## Overview

Phase 14 delivers two architecturally distinct capabilities mandated by the WindAgent V2 architecture:
1. **Context Assembly Engine** (located in `windagent.modules.agent_runtime.context`): Assembles, compacts, and budgets context for single model execution cycles.
2. **Memory Bounded Context** (located in `windagent.modules.memory`): Manages long-term, cross-session durable knowledge, memory scoping, write policies with secret scanning, learning admission gates, and optimistic concurrency versioning.

---

## Architecture & Separation of Concerns

Three distinct concepts are strictly decoupled:
* **Context**: Transient material prepared for the current model call (provenance-tracked, token-budgeted, auto-compacted, prompt-injection shielded).
* **Memory**: Durable multi-scope knowledge stored in PostgreSQL with CAS concurrency, TTL auto-eviction, and outbox event streaming.
* **State**: Current execution graph state managed by `AgentRuntimeService` (`Session`, `Run`, `Task`, `Workflow`).

---

## 1. Context Assembly Engine (`modules/agent_runtime/context`)

### A. Provenance Tracking & Sensitivity (`provenance.py`)
* `SourceType` (14 types): `REPOSITORY_INDEX`, `FILE_CONTENT`, `TOOL_OUTPUT`, `SESSION_CONTEXT`, `PROJECT_MEMORY`, `USER_MEMORY`, `WORKING_MEMORY`, `EPISODIC_MEMORY`, `SEMANTIC_MEMORY`, `PROCEDURAL_MEMORY`, `POLICY_MEMORY`, `BROWSER_CONTENT`, `EXTERNAL_API`, `USER_PROMPT`.
* `SensitivityLevel`: `PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`.
* `ContextItem`: Item container with token estimation, SHA-256 content hashing, and automatic prompt-injection warning markers when receiving external/untrusted content.
* `ProvenanceManifest`: Full trace of items input, filtered, compacted, and delivered to the model invocation.

### B. Token Budget Manager & Task Profiles (`budget.py`)
* Task-specific budgeting profiles:
  * `bugfix`: 32,000 total / 12,000 retrieval / 14,000 conversation
  * `feature`: 64,000 total / 24,000 retrieval / 28,000 conversation
  * `refactor`: 64,000 total / 30,000 retrieval / 20,000 conversation
  * `code_review`: 48,000 total / 24,000 retrieval / 16,000 conversation
  * `research`: 128,000 total / 60,000 retrieval / 50,000 conversation
  * `default`: 64,000 total / 24,000 retrieval / 28,000 conversation
* **Large File Protection**: Hard limits preventing single large documents from taking more than 25% of the retrieval token allocation.
* Prioritization heuristic: `confidence * freshness` with fallback to deterministic ordering.

### C. Context Compactor (`compaction.py`)
* Conversation compaction preserving critical keywords (`decision`, `blocked`, `invariant`, `rule`, `critical`, `architecture`, `do not`, `must`, `schema`, `constraint`).
* Tool output truncation replacing excessive logs with reversible artifact references (`artifact://compaction/tool_out_<hash>.txt`).

### D. 9-Stage Context Pipeline & ContextBuilder (`pipeline.py`, `builder.py`)
* 9-stage context pipeline:
  1. `input_normalization`
  2. `sensitivity_filtering`
  3. `deduplication`
  4. `budget_allocation`
  5. `compaction`
  6. `large_file_protection`
  7. `priority_fitting`
  8. `prompt_injection_shielding`
  9. `provenance_manifest_generation`
* Public `ContextBuilder` API for seamless integration with Agent Runtime sessions and runners.

---

## 2. Memory Bounded Context (`modules/memory`)

### A. Domain Model & Scope Taxonomy (`domain/`)
* **8 Extended Memory Scopes**:
  * `working` (active reasoning / execution scratchpad, default TTL: 1 hr)
  * `session` (session continuity, default TTL: 24 hrs)
  * `episodic` (episode traces and experience replay, default TTL: 7 days)
  * `project` (project facts, conventions, domain constants, persistent)
  * `user` (user preferences and settings, persistent)
  * `semantic` (validated reusable knowledge, persistent)
  * `procedural` (reusable skill specs and workflows, persistent)
  * `policy` (promoted behavioral rules, guidelines, persistent)
* **Validation Status Lifecycle**:
  `unvalidated` -> `proposed` -> `validated` -> `promoted` / `rejected` / `superseded`
* **MemoryWritePolicy**:
  * Regex secret scanning (rejects `sk-...`, bearer tokens, `ghp_...`, passwords, API credentials with 403 / permission denied).
  * Mandatory provenance check.
  * Scope isolation enforcement (project scope requires `project_id`, session scope requires `session_id`).
  * Learning admission gates: Requires `confidence >= min_confidence` (default 0.7) and `sample_size >= min_samples` (default 3) and `evidence_refs` / `source_run_ids` for promoted policy memories.

### B. Application Services & Outbox Events (`application/`)
* **`MemoryService`**:
  * Optimistic concurrency (CAS) via `optimistic_version` checking.
  * Deterministic content hashing (`compute_content_hash`) and deduplication.
  * Superseding lineage transitions: Saves new record while automatically transitioning superseded records to `ValidationStatus.SUPERSEDED` and emitting `memory.superseded`.
  * Background eviction job: `memory.evict_expired` for purging records past their TTL.
* **Transactional Outbox Events**:
  * `memory.created`
  * `memory.updated`
  * `memory.deleted`
  * `memory.superseded`
  * `memory.evicted`

### C. Infrastructure & Persistence (`infrastructure/`)
* `memory_records` table registered in shared metadata and Alembic migration `0011_memory.py`.
* `SqlMemoryStore` + `SqlTransactionScope` with transactional outbox integration.
* `InMemoryMemoryStore` + `InMemoryTransactionScope` for isolated unit testing.

### D. HTTP REST API (`/api/v4/memory`)
* 14 REST endpoints:
  * `POST /api/v4/memory`: Save memory record (with secret scanning & admission gating)
  * `POST /api/v4/memory/batch`: Batch save memory records
  * `GET /api/v4/memory`: List memories (filtered by scope, project, session, pagination)
  * `GET /api/v4/memory/lookup`: Lookup single memory by scope and key
  * `GET /api/v4/memory/stats`: Memory inventory stats grouped by scope
  * `GET /api/v4/memory/validated`: List validated knowledge records
  * `GET /api/v4/memory/policies`: List behavioral policies and rules
  * `GET /api/v4/memory/procedural`: List procedural workflows and recipes
  * `GET /api/v4/memory/episodic`: List episodic memory traces
  * `GET /api/v4/memory/search-tag`: Search memories by tag key/value
  * `GET /api/v4/memory/{id}`: Retrieve memory by ID
  * `DELETE /api/v4/memory`: Delete memory by scope & key
  * `POST /api/v4/memory/forget-pattern`: Forget memories matching key prefix
  * `POST /api/v4/memory/ttl`: Update memory TTL
  * `POST /api/v4/memory/evict`: Trigger eviction of expired records

---

## Verification Summary

* **Unit & Contract Tests**: 25 Phase 14 tests passing.
* **Full Test Suite**: 397 tests passing (397 passed in 34.06s).
* **Linter**: `ruff check` passed with 0 errors.
* **Type Safety**: `mypy` passed across all 426 source files with 0 issues.
