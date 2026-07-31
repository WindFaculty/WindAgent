# Capability Contracts — Video Pre-production Kernel (Phase 6)

Source: plan 02 `§14-§18` (`02_phase_04_07_videoclaw_preproduction_kernel.md`).
Status: ratified for `VP6_PREPRODUCTION_KERNEL_CANONICAL`.

This document is the canonical contract for every capability exposed by
`intelligence/windagent_intelligence/video/`. It is the single source of
truth the Phase 6 verifier (`verify_phase6_kernel.py`) checks against.

## 0. Cross-cutting rules (plan 02 §16.1, §16.2)

Every capability:

1. **Provider neutral** — talks to models only through the
   `PreproductionModelPort` protocol (`video/ports.py`). No provider SDK
   object, endpoint, or session ever enters the kernel.
2. **Versioned, hashed prompts** — any capability that uses a model declares a
   `PromptSpec` (semantic version + deterministic content hash) and returns
   `prompt_version` + `prompt_hash` with its output (see
   `prompt_versioning.md`).
3. **Typed failures** — broken/empty/partial provider responses raise typed
   `VideoKernelError` subclasses (fixes DEF-001, DEF-002, DEF-005). No silent
   `None` fallbacks.
4. **Deterministic identity** — entities get stable canonical IDs via
   `StableIdFactory`; identity is never merged on display name (fixes
   DEF-003); name lists are fully sorted (fixes NONDET-005).
5. **No authority** — a capability never writes a project/session DB, never
   locks a screenplay, never approves assets, and never calls video
   generation.
6. **Validated before publish** — any artifact assembled into a
   `VideoProductionPackage v1` passes the Phase 3 canonical validator
   (`VideoProductionPackageValidator`); failure is a typed
   `ValidationFailureError` and never a partial package.

## 1. Capability matrix

| # | Capability | Service | Model-backed | Domain output | Prompt spec |
|---|---|---|---|---|---|
| 1 | Creative brief / idea expansion | `CreativeBriefExpander` | yes | `CreativeBrief` | `BRIEF_EXPANSION_PROMPT_V1` |
| 2 | Story outline | `StoryOutliner` | yes | `StoryConcept` | `OUTLINE_PROMPT_V1` |
| 3 | Multi-scene screenplay | `ScreenplayWriter` | yes | `Screenplay` | `SCREENPLAY_PROMPT_V1` |
| 4 | Dialogue and narration | `DialogueNarrator` | no (offline) | `DialogueLine[]`, narration blocks | n/a |
| 5 | Character / location / prop extraction | `EntityExtractor` | no (offline) | `CharacterBible[]`, `LocationBible[]`, `PropBible[]` | n/a |
| 6 | Style bible | `StyleDesigner` | yes | `StyleBible` | `STYLE_DESIGN_PROMPT_V1` |
| 7 | Plot continuation / revision proposal | `ContinuationService` | yes | `ContinuationResult` | `CONTINUATION_PROMPT_V1` |
| 8 | Asset prompt specification | `AssetPromptSpecBuilder` | no (offline) | `AssetPromptSpecResult[]` | 3 built-in specs |
| 9 | Assemble `VideoProductionPackage` | `PackageAssembler` | no (offline) | `PackageAssemblyReceipt` | n/a |

## 2. Capability contracts

### 2.1 CreativeBriefExpander

- **Input:** `idea: str` (raw user idea).
- **Output:** `{brief: CreativeBrief, prompt_version, prompt_hash, capability}`.
- **Contract:** brief must carry non-empty `title`; `genre` accepts a string
  or list (normalized to comma-joined); `target_duration_seconds` and
  `aspect_ratio` have defaults when absent.
- **Failure:** empty model response → `EmptyResponseError`; missing `title` →
  `ResponseParseError`; missing model config → `MissingModelConfigError`
  (BM-010 preflight, fail fast before any provider call).

### 2.2 StoryOutliner

- **Input:** `brief: CreativeBrief`.
- **Output:** `{concept: StoryConcept, beats, prompt_version, prompt_hash,
  capability}`.
- **Contract:** themes are `sorted(set(...))` (deterministic full ordering,
  fixes NONDET-005); beats preserved in authored order in
  `concept.metadata["beats"]`.

### 2.3 ScreenplayWriter

- **Input:** `concept: StoryConcept`.
- **Output:** `{screenplay: Screenplay, dialogue_lines, episodes,
  prompt_version, prompt_hash}`.
- **Contract:** the provider returns canonical screenplay TEXT which is parsed
  by `split_episodes` (Unicode/Vietnamese/CJK tolerant — fixes DEF-002,
  DEF-005). Scenes are emitted in order; scene order is preserved; characters
  and locations get stable IDs; dialogue lines bind to stable character IDs
  (fixes DEF-003). An empty or unparseable response raises
  `EmptyResponseError` / `ResponseParseError`.

### 2.4 DialogueNarrator

- **Input:** `screenplay_text: str`, `scenes: List[Scene]`.
- **Output:** `{dialogue_lines, narration_blocks, character_map, episodes}`.
- **Contract:** fully offline; attribution is deterministic; narration blocks
  keyed by scene id; speaker → `CharacterId` mapping fully sorted.

### 2.5 EntityExtractor

- **Input:** `screenplay: Screenplay`, `meta_response: str` (JSON).
- **Output:** `{characters, locations, props, prompt_version, capability}`.
- **Contract:** missing/empty `characters` → typed `ResponseParseError`
  (fixes BM-025); duplicate display names keep distinct stable IDs
  (fixes DEF-003); locations fold in screenplay scene locations when meta
  omits them; bibles sorted deterministically.

### 2.6 StyleDesigner

- **Input:** `brief: CreativeBrief`, `screenplay: Screenplay`.
- **Output:** `{style_bible, prompt_version, prompt_hash, capability}`.
- **Contract:** required style constraints from the brief are preserved
  (blocking equivalence — see `equivalence_policy.md`); metadata records the
  prompt version + hash.

### 2.7 ContinuationService

- **Input:** locked `screenplay`, `brief`, plus `project_id`,
  `parent_revision_id`, `created_by`, optional `invalidation_intent`.
- **Output:** `ContinuationResult` (revision `proposal`).
- **Contract:** never mutates the locked screenplay (raises
  `LockedScreenplayMutationError` when `require_locked=True` and status is not
  `LOCKED`); prior episodes are never renumbered; new scenes carry
  `continuation: true` metadata; proposal is a DRAFT; invalidation intent
  declared.

### 2.8 AssetPromptSpecBuilder

- **Input:** `CharacterBible`, `LocationBible`, `StyleBible` (or lists).
- **Output:** `AssetPromptSpecResult[]` (versioned, hashed prompt specs).
- **Contract:** deterministic; every result carries `capability`,
  `target_id`, `prompt_spec`, `rendered`.

### 2.9 PackageAssembler

- **Input:** project/revision/author ids + the pre-production parts.
- **Output:** `PackageAssemblyReceipt` (`package`, `content_hash`, `valid`).
- **Contract:** offline; assembles an immutable `VideoProductionPackage v1`,
  validates with the Phase 3 canonical validator; any issue →
  `ValidationFailureError` (never a partial package).

## 3. Determinism guarantees

- IDs: `StableIdFactory` SHA-256 over `(seed, seed_value, seq)`; never the
  display name alone.
- Ordering: name/theme lists are fully sorted.
- Parsing: `split_episodes` / `parse_scene_header` are pure functions.
- Hashing: `VideoProductionPackage.content_hash()` excludes approvals and
  provenance so identical logical content hashes identically.
