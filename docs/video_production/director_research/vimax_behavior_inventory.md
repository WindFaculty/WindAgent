# ViMax Behavior Inventory — Clean-Room Observation

## Source

- Repository: `HKUDS/ViMax`
- Reference: `pipelines/script2video_pipeline.py` (Script2VideoPipeline)
- Observation date: 2026-07-31
- Method: Black-box behavioral analysis of publicly documented capabilities. No source code, prompts, schemas, or fixtures copied into WindAgent.

## Observed Behaviors

### BHV-001: Screenplay to Storyboard Decomposition

**What it does:** Takes a structured screenplay (scenes with dialogue, descriptions) and produces a shot-by-shot storyboard with camera framing, movement, and timing.

**Input:** Screenplay with scenes, character dialogue, location descriptions.
**Output:** Ordered list of shots, each with: shot type (wide/medium/close-up), camera movement (pan/dolly/static), duration estimate, framing description.
**Invariant:** Every scene maps to at least one shot. Shot count >= scene count.
**Failure mode:** Scene with ambiguous spatial description produces shots with conflicting camera positions.
**Checkpoint/resume:** Storyboard cached per screenplay hash; re-run on screenplay change.

### BHV-002: Camera Tree / Shot Dependency Graph

**What it does:** Builds a dependency tree where later shots can reference earlier shots for continuity (character position, lighting, props).

**Input:** Ordered storyboard shots.
**Output:** Directed acyclic graph linking shots by dependency type (character_continuity, lighting_match, prop_continuity, spatial_adjacency).
**Invariant:** Graph is acyclic. Every shot has at most one parent per dependency type.
**Failure mode:** Circular dependency when two shots reference each other for character position — detected and broken by inserting a neutral establishing shot.
**Checkpoint/resume:** Tree cached; re-computed on storyboard change.

### BHV-003: Character Portrait Registry

**What it does:** Maintains per-character reference images and trait descriptions. Reuses existing portraits across shots unless character appearance changes (age, costume, injury).

**Input:** Character bible (name, visual traits, reference prompts).
**Output:** Keyed registry: character_id → {portrait_images, trait_vector, last_shot_used}.
**Invariant:** One canonical portrait set per character per scene, unless explicit appearance change trigger.
**Failure mode:** Registry stale — character appearance drifts across long sequences. Mitigated by re-generation trigger on appearance change events.
**Checkpoint/resume:** File-exists check on registry path (identified as insufficient for content-aware invalidation — see Phase 18 in roadmap).

### BHV-004: Reference Image Selection

**What it does:** For each shot, selects or generates reference images that guide the video generation model (style reference, composition reference, character pose reference).

**Input:** Shot description, character registry, location bible.
**Output:** Per-shot reference bundle: {style_ref, composition_ref, character_pose_refs[]}.
**Invariant:** Reference count per shot bounded by generation model limits.
**Failure mode:** Reference selection chooses images with conflicting lighting or art style — produces inconsistent generated frames.
**Checkpoint/resume:** References cached per shot; re-selected on shot description change.

### BHV-005: Render Checkpoint and Resume

**What it does:** Skips already-rendered frames, clips, or final video if output file exists on disk.

**Input:** Output path, generation parameters.
**Output:** Skip or proceed decision.
**Invariant:** Skip decision based solely on file existence — no content hash verification.
**Failure mode:** Stale artifact reused after input change because file still exists. **This is a known anti-pattern.** WindAgent Phase 18 replaces this with content-addressed artifact storage (SHA256 of canonical input + parameters).
**Note:** Documented as insufficient for production use. Roadmap Phase 18 specifies content-addressed invalidation.

### BHV-006: Parallel Generation

**What it does:** Generates multiple shots or frames concurrently when no dependency exists between them.

**Input:** Shot dependency graph, available parallelism budget.
**Output:** Parallel dispatch of independent generation tasks.
**Invariant:** Shots with dependency edges never run in parallel; independent branches run concurrently.
**Failure mode:** Resource exhaustion when parallelism budget exceeds provider rate limits.
**Checkpoint/resume:** Per-shot checkpoint; failed shots retried independently without blocking sibling shots.

### BHV-007: Text Planning Separated from Rendering

**What it does:** Complete text planning (storyboard, shot descriptions, camera tree, character references) finishes before any pixel-generation begins.

**Input:** Screenplay + creative brief.
**Output:** Complete shot plan with all references and dependencies, ready for rendering.
**Invariant:** No render call before planning phase completes. Planning phase produces deterministic output for same input.
**Failure mode:** Planning phase hangs on LLM timeout — no partial render possible. Mitigated by planning checkpoint at each phase boundary.

### BHV-008: Camera Continuity Across Shots

**What it does:** Enforces camera rules: 180-degree rule, match on action, eyeline continuity, consistent screen direction.

**Input:** Shot sequence with camera positions.
**Output:** Validated or corrected camera positions, continuity warnings.
**Invariant:** Adjacent shots of same subject maintain consistent screen direction unless explicit crossing shot inserted.
**Failure mode:** False positive on 180-degree rule when deliberate crossing shot is stylistic choice.
**Checkpoint/resume:** Continuity computed per scene; cached with scene hash.

## Summary of Learnings

| Behavior | Useful for WindAgent | Anti-pattern to avoid |
|---|---|---|
| BHV-001: Screenplay → Storyboard | Yes — core Director capability | — |
| BHV-002: Camera Tree | Yes — ShotDependencyGraph | — |
| BHV-003: Character Registry | Yes — IdentityReferenceCatalog | File-exists invalidation |
| BHV-004: Reference Selection | Yes — ReferenceBindingPlanner | Conflicting reference selection |
| BHV-005: Render Checkpoint | Partial — concept useful | File-exists only; no content hash |
| BHV-006: Parallel Generation | Yes — Workflow concurrency | No rate-limit awareness |
| BHV-007: Plan-then-Render | Yes — Two-phase architecture | No partial render on planning failure |
| BHV-008: Camera Continuity | Yes — ContinuityValidator | False positive on stylistic breaks |