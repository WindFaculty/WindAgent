# Independent Requirements — WindAgent Director Layer

Derived from clean-room observation of ViMax behaviors. No ViMax source, prompt, schema, or fixture used. Each requirement describes a problem and expected behavior, not an implementation.

## Format

```
DIR-REQ-NNN
problem_statement
input_contract
output_contract
invariants
failure_behavior
acceptance_test
source_of_observation
independent_design_notes
```

---

## DIR-REQ-001: Screenplay to Shot Decomposition

**Problem:** A structured screenplay must be decomposed into individual camera shots with framing, movement, and timing before any rendering can begin.

**Input contract:**
- Screenplay with ordered scenes, each containing: scene_id, location_id, character_ids[], dialogue[], action_description.
- Creative brief with: genre, tone, target_duration, aspect_ratio.

**Output contract:**
- Ordered shot list: shot_id, scene_id, shot_type (WIDE/MEDIUM/CLOSE_UP/EXTREME_CLOSE_UP/ESTABLISHING), camera_movement (STATIC/PAN/DOLLY/TRACK/CRANE/HANDHELD), duration_seconds, framing_description, transition_type.

**Invariants:**
- Every scene produces at least 1 shot.
- Shot count >= scene count.
- Total shot duration must sum to target_duration +/- 10%.
- Shot ordering preserves scene ordering.

**Failure behavior:**
- Scene with ambiguous spatial description: produce multiple candidate shots, flag for human review.
- Scene exceeding duration budget: compress shot durations proportionally, flag for review.

**Acceptance test:** Given a 3-scene screenplay with 120s target, verify output has >= 3 shots, ordered by scene, sum within 108-132s.

**Source of observation:** BHV-001 (ViMax Script2VideoPipeline screenplay-to-storyboard decomposition).

**Independent design notes:** WindAgent uses `CinematicPlanner` as the planning component. Shot types and camera movements defined in WindAgent domain model (`core/windagent_core/domain/video_production/`). No ViMax class hierarchy or prompt templates used.

---

## DIR-REQ-002: Shot Dependency Graph

**Problem:** Shots within a scene have continuity dependencies (character position, lighting, props). These must be modeled as a directed acyclic graph so the render scheduler can parallelize independent shots and serialize dependent ones.

**Input contract:**
- Ordered shot list from DIR-REQ-001.
- Character registry from DIR-REQ-003.
- Location bible with spatial layout.

**Output contract:**
- `ShotDependencyGraph`: DAG where nodes are shots, edges are typed dependencies: `CHARACTER_CONTINUITY`, `LIGHTING_MATCH`, `PROP_CONTINUITY`, `SPATIAL_ADJACENCY`.

**Invariants:**
- Graph is acyclic.
- Each shot has at most 1 parent per dependency type.
- Dependency edges only between shots in same or adjacent scenes.

**Failure behavior:**
- Circular dependency detected: insert neutral establishing shot to break cycle, flag for review.
- Shot with no parent: treated as independent, eligible for parallel generation.

**Acceptance test:** Given 5 shots where shot 3 and 4 both reference shot 2 for character continuity, verify graph has edges (2→3, CHARACTER_CONTINUITY) and (2→4, CHARACTER_CONTINUITY) and no edge between 3 and 4. Verify no cycles.

**Source of observation:** BHV-002 (ViMax camera tree).

**Independent design notes:** WindAgent names this `ShotDependencyGraph` not "camera tree". Dependency types are WindAgent domain enums. Topological sort used for render ordering.

---

## DIR-REQ-003: Identity Reference Catalog

**Problem:** Characters must maintain visual consistency across all shots. A catalog must store canonical reference images and traits per character, with explicit triggers for appearance changes (costume change, aging, injury).

**Input contract:**
- Character bible: character_id, name, visual_traits {age, gender, height, build, hair, eyes, skin_tone, distinguishing_features}, costume_descriptions[], reference_prompt_templates.

**Output contract:**
- `IdentityReferenceCatalog`: character_id → {canonical_portrait_set, trait_vector, appearance_events[{shot_id, change_description, new_traits}]}.

**Invariants:**
- One canonical portrait set per character per scene unless appearance change event exists.
- Portrait set must include: front-facing, profile, three-quarter view.
- Reference images carry content hash for invalidation.

**Failure behavior:**
- Missing character portrait: generate from reference prompt before any shot using that character.
- Stale portrait after appearance change: invalidate downstream shots, flag for re-generation.

**Acceptance test:** Given character with 2 appearance change events at shots 5 and 12, verify catalog returns 3 portrait sets (shots 1-4, 5-11, 12+). Verify content hashes differ between sets.

**Source of observation:** BHV-003 (ViMax character portrait registry).

**Independent design notes:** WindAgent names this `IdentityReferenceCatalog`. Replaces file-exists check with content-addressed storage (Phase 18). Appearance change events are explicit domain events, not implicit file timestamps.

---

## DIR-REQ-004: Reference Binding

**Problem:** Each shot needs reference images (style, composition, character pose) to guide generation. These must be selected or generated based on shot description, character catalog, and location bible, with consistency checks across adjacent shots.

**Input contract:**
- Shot from DIR-REQ-001.
- IdentityReferenceCatalog from DIR-REQ-003.
- Location bible: location_id → {visual_description, lighting_profile, atmosphere_tags}.

**Output contract:**
- `ReferenceBinding`: shot_id → {style_reference, composition_reference, character_pose_references[character_id], lighting_reference}.

**Invariants:**
- Reference count per shot <= provider model limit.
- Adjacent shots of same location share lighting_reference.
- Style reference consistent across entire scene.

**Failure behavior:**
- Conflicting references (mismatched lighting between style_ref and location): flag conflict, select location lighting as authority.
- Provider model limit exceeded: prioritize character pose references, drop composition reference.

**Acceptance test:** Given 2 adjacent shots in same location with same character, verify both shots share lighting_reference and character_pose_reference for that character. Verify no conflicting style references.

**Source of observation:** BHV-004 (ViMax reference image selector).

**Independent design notes:** WindAgent names this `ReferenceBindingPlanner`. Reference selection uses explicit priority rules, not LLM prompt heuristics. References are content-addressed.

---

## DIR-REQ-005: Render Checkpoint and Resume

**Problem:** Long video generation jobs must survive process restarts and avoid re-generating completed work. However, file-existence alone is insufficient — must verify content hash matches expected output.

**Input contract:**
- Generation job: job_id, shot_id, provider, model, parameters, input_hash.
- Artifact store with content-addressed lookup.

**Output contract:**
- Decision: SKIP (artifact exists with matching hash), GENERATE (no artifact or hash mismatch), or INVALIDATED (artifact exists but input changed).

**Invariants:**
- Skip decision requires content hash match, not just file existence.
- Input change always invalidates downstream artifacts (see invalidation graph in DIR-REQ-008).
- Artifact metadata includes: input_hash, provider, model, parameters, created_at.

**Failure behavior:**
- Hash mismatch: treat as GENERATE, log staleness event.
- Artifact store unavailable: fail job, do not silently skip.

**Acceptance test:** Given artifact with hash H1 from input I1, re-submit with input I2 (I2 != I1). Verify decision is GENERATE (not SKIP). Given artifact with hash H1 from input I1, re-submit with same input I1. Verify decision is SKIP.

**Source of observation:** BHV-005 (ViMax render checkpoint) — concept adopted, file-exists anti-pattern replaced.

**Independent design notes:** This is the anti-pattern fix. WindAgent uses content-addressed storage from Phase 18. ViMax file-exists approach is explicitly documented as what NOT to do.

---

## DIR-REQ-006: Parallel Generation Scheduling

**Problem:** Independent shots (no dependency edges in ShotDependencyGraph) should generate concurrently. Dependent shots must serialize. Provider rate limits must be respected.

**Input contract:**
- ShotDependencyGraph from DIR-REQ-002.
- Provider rate limit configuration: max_concurrent_requests, requests_per_minute.
- Per-shot generation job from DIR-REQ-005.

**Output contract:**
- Execution plan: ordered batches of parallel shot groups. Shots within a batch have no mutual dependencies.
- Per-batch: shot_ids[], estimated_duration, provider_slot_allocation.

**Invariants:**
- No two shots with a dependency edge execute in the same batch.
- Batch size <= provider max_concurrent_requests.
- Batch rate <= provider requests_per_minute.

**Failure behavior:**
- Provider rate limit exceeded: batch is split, remaining shots deferred to next scheduling window.
- Shot failure: retry with exponential backoff, max 3 attempts. Sibling shots in batch unaffected.

**Acceptance test:** Given 5 shots where 2→3 and 2→4 are dependency edges, verify batch 1 contains shot 2, batch 2 contains shots 3 and 4 (parallel). Verify batch sizes within provider limits.

**Source of observation:** BHV-006 (ViMax parallel generation).

**Independent design notes:** WindAgent uses workflow engine concurrency primitives. Rate limiting is a first-class concern, not an afterthought. Retry with backoff is standard WindAgent pattern.

---

## DIR-REQ-007: Two-Phase Planning Architecture

**Problem:** All text planning must complete before any pixel generation begins. This ensures deterministic pre-production output and allows human review before spending generation credits.

**Input contract:**
- Screenplay + creative brief.

**Output contract:**
- Complete `VideoProductionPackage v1` containing: shot list, dependency graph, reference bindings, character catalog, location bible, continuity constraints.
- Package is immutable once planning phase completes.

**Invariants:**
- No render/API call to any generation provider during planning phase.
- Planning phase produces deterministic output for same input (same screenplay + creative brief = same package hash).
- Planning phase must complete or fail as a unit — no partial planning output.

**Failure behavior:**
- LLM timeout during planning: retry with backoff. If max retries exceeded, fail planning phase with partial output for debugging.
- Inconsistent planning output: schema validation fails, reject entire package.

**Acceptance test:** Run planning phase twice with identical input. Verify both outputs have identical hash. Verify no network calls to image/video generation APIs during planning.

**Source of observation:** BHV-007 (ViMax plan-then-render separation).

**Independent design notes:** WindAgent formalizes this as `ProductionPlanningWorkflow`. The planning phase is a pure function of its inputs. All generation API calls are gated behind the planning completion signal.

---

## DIR-REQ-008: Camera Continuity Enforcement

**Problem:** Consecutive shots must respect cinematographic continuity rules: 180-degree rule, match on action, eyeline continuity, consistent screen direction.

**Input contract:**
- Ordered shot list with camera positions.
- Scene geometry: character positions, movement vectors.

**Output contract:**
- Continuity report: per-shot-pair {rule_check, status (PASS/WARN/VIOLATION), detail}.
- Corrected camera positions where violations are unambiguous.

**Invariants:**
- Adjacent shots of same subject maintain consistent screen direction.
- 180-degree line is computed per scene; camera must stay on one side unless explicit crossing shot exists.
- Eyeline vectors must match between shot/reverse-shot pairs.

**Failure behavior:**
- Ambiguous violation (stylistic choice vs error): flag WARN, do not auto-correct.
- Clear violation (camera crosses 180-degree line without crossing shot): auto-correct camera position, flag for review.

**Acceptance test:** Given 2-shot dialogue scene with characters A (left) and B (right), verify shot 1 (A looking right) and shot 2 (B looking left) pass eyeline check. Reverse B's eyeline to right — verify VIOLATION.

**Source of observation:** BHV-008 (ViMax camera continuity).

**Independent design notes:** WindAgent implements this as `ContinuityValidator` in the Director layer. Rules are explicit geometric checks, not LLM heuristic. Stylistic exceptions are explicit domain events ("crossing shot"), not implicit.

---

## Cross-Reference: Terminology Mapping

See `terminology_mapping.md` for ViMax→WindAgent term translation.

## Cross-Reference: Rejected Designs

See `rejected_designs.md` for patterns explicitly excluded from WindAgent.