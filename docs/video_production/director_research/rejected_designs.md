# Rejected Designs — WindAgent Director Layer

Designs explicitly excluded from WindAgent, with reasons. Each rejection is a deliberate architectural decision, not an omission.

## REJ-001: File-Exists Artifact Cache

**What was rejected:** Checking `os.path.exists(output_path)` to decide whether to skip generation.

**Why rejected:** File existence proves nothing about content validity. An artifact exists but may be stale (input changed, prompt version changed, reference images changed). This is the primary anti-pattern observed in ViMax.

**What WindAgent does instead:** Content-addressed artifact storage. Every artifact keyed by `SHA256(canonical_input + prompt_version + reference_hashes + model + parameters)`. File existence is never used as a validity signal. See DIR-REQ-005 and Phase 18.

**When to revisit:** Never. This is a solved problem.

---

## REJ-002: Monolithic End-to-End Pipeline

**What was rejected:** Single script/class that runs from screenplay input to final MP4 output in one process.

**Why rejected:** Monolithic pipeline cannot be stopped, inspected, or resumed at intermediate stages. No human review gate between planning and expensive generation. No partial re-run — any failure means restart from beginning.

**What WindAgent does instead:** Two-phase architecture: (1) planning phase produces immutable `VideoProductionPackage v1`, (2) execution phase consumes package and dispatches to providers. Human review gate between phases. Each phase checkpoints independently.

**When to revisit:** Never. Two-phase architecture is the canonical WindAgent pattern.

---

## REJ-003: LLM Prompt as String Templates

**What was rejected:** Concatenating user screenplay text into raw LLM prompt strings with `f"...{screenplay}..."`.

**Why rejected:** Prompt injection risk. No structured validation. Cannot version-control prompt logic separately from text content. Cannot audit what the LLM actually received.

**What WindAgent does instead:** Structured `PromptSpec` objects with typed fields: system_message, user_message, context, examples. Fields are validated against schema. Prompt assembly is deterministic and auditable. User content is passed as a separate message role, never concatenated into system instructions.

**When to revisit:** Never. Structured prompts are a security requirement.

---

## REJ-004: Web UI and Chat Bot Connectors

**What was rejected:** React-based web dashboard and WeChat/Feishu bot integration for triggering video generation.

**Why rejected:** WindAgent has its own UI (web + desktop) and CLI. Adding a second UI framework duplicates the interaction surface. Chat bot connectors are out of scope for the video production platform.

**What WindAgent does instead:** WindAgent web/desktop workspace (Phase 23) provides the production UI. CLI provides scriptable access. No external chat bot integration.

**When to revisit:** If a future requirement demands chatbot-initiated video generation, add a WindAgent-native bot adapter. Do not vendor upstream chat connectors.

---

## REJ-005: Dynamic Module Imports

**What was rejected:** `importlib.import_module()` on user-supplied or config-supplied module names.

**Why rejected:** Arbitrary code execution risk. No static analysis possible. Impossible to audit what code runs in production.

**What WindAgent does instead:** Explicit provider registry. Every supported provider is a registered class with a known import path. Provider selection is a lookup in the registry, not a dynamic import.

**When to revisit:** Never. Dynamic imports are a security anti-pattern.

---

## REJ-006: Auto-Update from Remote

**What was rejected:** Script that checks GitHub for newer version and downloads/executes it at runtime.

**Why rejected:** Supply chain attack surface. Breaks reproducibility (same version number may produce different behavior). Violates WindAgent's version-pinned, frozen-release policy.

**What WindAgent does instead:** All releases are version-pinned. Updates happen through the standard WindAgent release process. No runtime self-update.

**When to revisit:** Never. Auto-update is a security anti-pattern.

---

## REJ-007: Silent Provider Fallback

**What was rejected:** When primary generation provider fails, silently switching to an alternative public endpoint.

**Why rejected:** User must know which provider generated their content (attribution, cost, quality). Silent fallback hides failures and makes debugging impossible. Public endpoint fallback is a security risk.

**What WindAgent does instead:** Fail fast on provider error. Explicit provider configuration in project settings. If fallback is configured, it is explicit and logged. Provider identity is recorded in generation metadata.

**When to revisit:** If explicit provider fallback chains are needed, implement as `ProviderFallbackPolicy` with explicit ordering and logging. Never silent.

---

## REJ-008: Pickle Serialization

**What was rejected:** Using `pickle.load()` for cached embeddings or model artifacts.

**Why rejected:** Arbitrary code execution on deserialization. Not safe for cross-version or cross-machine artifact sharing.

**What WindAgent does instead:** JSON for structured data. Pydantic for schema validation. Custom binary formats only when strictly necessary (model weights), with hash verification.

**When to revisit:** Never. JSON/Pydantic covers all WindAgent serialization needs.

---

## REJ-009: Frame-Level Planning

**What was rejected:** Planning at individual video frame granularity (e.g., "frame 47 of shot 3").

**Why rejected:** Over-specification. Video generation models work at shot level, not frame level. Frame-level planning creates false precision and bloats the planning output.

**What WindAgent does instead:** Plans at shot level. Each shot specifies: duration, shot type, camera movement, framing description. Frame-level details are left to the generation model.

**When to revisit:** If future models support frame-accurate control, add optional frame hints as additive fields. Do not change the base shot-level planning model.

---

## Summary

| Rejected Pattern | Reason | Replacement |
|---|---|---|
| File-exists cache | No content validity | Content-addressed storage |
| Monolithic pipeline | No inspection/resume | Two-phase architecture |
| String prompt templates | Injection risk | Structured PromptSpec |
| Web UI + chat bots | Duplicate UI surface | WindAgent native UI |
| Dynamic imports | Code execution risk | Provider registry |
| Auto-update | Supply chain risk | Version-pinned releases |
| Silent fallback | Hidden failures | Explicit provider config |
| Pickle serialization | Security risk | JSON + Pydantic |
| Frame-level planning | Over-specification | Shot-level planning |