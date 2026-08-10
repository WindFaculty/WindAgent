# B0 Evidence — Reuse Ledger (consume freeze)

Audit date: 2026-08-09 (Asia/Saigon). Baseline: `9a09375700db02a64315068f008b15e43ba5f42d`.
Plan B phase B0 (consume freeze) — inventory, classify, and freeze reuse decisions **before any code moves**.

Classification values:

- **REUSE** — reuse the symbol unchanged (possibly composed/aliased) in a new canonical stage.
- **WRAP** — reuse the implementation behind a new compatibility wrapper/adapter inside `story/**` or `video/**`; no behavior change at the legacy boundary.
- **MIGRATE** — copy/adapt the proven pattern into a new canonical artifact (the old module stays public).
- **DEPRECATE** — old path stays operational for V2/legacy reads; new callers are forbidden (guard: `scripts/check_story_b0_legacy_boundary.py`).
- **VP3D-ONLY** — production planning/rendering layer; Plan B reads/tests but never depends on it; it is not Story authority.

Ownership follows `40_FILE_OWNERSHIP_MATRIX.md`: B owns content models/prompts/schemas/handlers; A owns envelope/hash/lock/ports/persistence/orchestration; C owns API/UI/schemas.

## 1. Core content models (B-owned, `core/windagent_core/domain/video_production/`)

| Symbol | Ref | Decision | Rationale / B stage |
|---|---|---|---|
| `CreativeBrief` | `screenplay.py:29` | REUSE → WRAP in B1/B3 | Content-only (no envelope fields — see consumer test `test_content_models_carry_no_envelope_fields`). B3 normalizes with `language`, `audience` band, `theme`/`tone`, `constraints`, `prohibited_content`; today `audience`/`tone`/`genre` are free strings and `target_duration_seconds` exists. |
| `StoryConcept` | `screenplay.py:45` | DEPRECATE (single-concept) + MIGRATE pattern | B3 replaces "one concept" with a 3–5 `IdeaCandidateSet`; `StoryConcept` remains a compatibility projection with explicit loss metadata. Frozen artifact `IdeaCandidateSet` is new. |
| `DialogueLine` | `screenplay.py:58` | REUSE (compose/alias) | B6 structured scenes embed dialogue with timing + source refs; current `DialogueLine` fields (`scene_id`, `character_id`, `order`, `text`, `delivery`) map cleanly. |
| `Screenplay` | `screenplay.py:71` | REUSE as V2 read/text model; MIGRATE authority | B6 makes structured JSON draft the authority; `Screenplay` becomes a derived view. V2 text parser/serializer stay (see §4). |
| `Scene` | `scene.py` | REUSE within structured scenes | Stable `scene_id`/`order`, character/location/dialogue refs carry into `EpisodeOutline`/`ScreenplayDraft`. |
| `CharacterBible` | `character.py` | REUSE as mapping input → WRAP | B4 `CharacterCanon` needs stable IDs, roles, goals, traits, relationships, appearance/voice; `CharacterBible` supplies identity/role/traits/costume today. |
| `LocationBible` / `PropBible` | `location.py:22` / `location.py:36` | REUSE as mapping input | B4 `WorldBible` recurring locations/objects; identity/description/lighting/atmosphere map losslessly. |
| `StyleBible` | `location.py:48` | REUSE via `StyleDesigner` output | Maps into `WorldBible` style constraints; preserve blocking style-constraint semantics. |
| `VideoProductionPackage` | `package.py:68` | REUSE patterns (canonical serialization + content hash + major-version fail-closed) | B8 `LockedScreenplayPackage` is a distinct Studio artifact but must reuse hash/lineage semantics; never copies a mutable draft (rule 7). |

## 2. Approval / revision primitives (A-owned)

| Symbol | Ref | Decision | Rationale |
|---|---|---|---|
| `ReviewResult` | `approval.py:33` | REUSE hash-bound semantics only | A adds `ApprovalPolicy`/checkpoint modes in `core/.../domain/studio/**`; B consumes, does not own. |
| `ApprovalDecision` | `approval.py:47` | REUSE | Hash/revision-bound already; stale hash rejected by A. |
| `ApprovalState` | `approval.py:63` | REUSE | `has_approval_for_hash` semantics carry. |
| `ProductionRevision` / `RevisionService` | `project.py:60` / `project.py:89` | REUSE (A migrates) | Parent/hash/lock/invalidation-intent semantics; A extends to `SeriesProject -> Episode -> ProductionRevision`. |

## 3. Intelligence services (B-owned legacy, `intelligence/windagent_intelligence/video/`)

| Symbol | Ref | Decision | Rationale / B stage |
|---|---|---|---|
| `PromptSpec` | `prompts.py:19` | **REUSE unchanged** | Already immutable/versioned/hashed (`content_hash` over capability+version+template) — the primitive for the B2 prompt catalog. |
| `PreproductionModelPort` / `ModelCompletionRequest` / `ModelCompletionResult` | `ports.py:50/19/38` | **REUSE unchanged** | The single provider boundary (contract: provider calls cross only this port). No production adapter exists yet (grep over providers/apps/orchestration/storage → zero hits); A supplies it. Deterministic fake OK for unit tests only. |
| `CreativeBriefExpander` | `ideation/brief_expander.py:43` | WRAP | Reuse for brief normalization sub-step (B3). Parses JSON via `parse_json_contract` (typed). Produces one brief; B normalizes into canonical brief artifact. |
| `StoryOutliner` | `ideation/outliner.py:44` | WRAP → B5 suggestion only | Produces exactly one `StoryConcept`; cannot serve 3–5 candidate generation. Beat strings land in `metadata["beats"]` — reuse for concept-to-beat suggestions. |
| `ScreenplayWriter` | `screenplay/writer.py:63` | DEPRECATE authority → MIGRATE to structured writer | Requests canonical TEXT and parses tolerantly (`split_episodes`) — insufficient for the frozen structured contract (plan observation). Keep text path for V2/legacy only; B6 structured JSON is the authority. |
| `DialogueNarrator` | `screenplay/narration.py:29` | REUSE (offline, deterministic) | Deterministic dialogue attribution + narration extraction; reuse inside structured draft derivation (B6). |
| `EntityExtractor` | `entity_extraction/extractor.py:32` | WRAP as internal adapter | Reuse for bible/canon entity mapping (B4) where outputs map losslessly; otherwise replace with structured stages. |
| `StyleDesigner` | `style_design/designer.py:45` | WRAP | Reuse for style → world/style constraints (B4); leave old pipeline path intact. |
| `ContinuationService` | `continuation/service.py:69` | MIGRATE pattern | Never-mutate revision-proposal pattern is exactly B7's `revise` semantics (new immutable draft, existing facts preserved). The locked-immutability guard maps to `LockedScreenplayMutationError`. |
| `PackageAssembler` | `assembly/assembler.py:60` | DEPRECATE (old package assembly) | Assembles `VideoProductionPackage v1` (production pre-production), not the Studio story flow. Its validate-before-publish receipt pattern is reused conceptually in B8 package assembly. |
| `VideoDirectorService` | `director/service.py:59` | **VP3D-ONLY** | Production planning from a locked package; Plan B ends at `READY_FOR_PRODUCTION` (no renderer). B must not import director/IR. |
| `DirectorPlanValidator` | `director/validator.py:63` | VP3D-ONLY (read for patterns) | Deterministic fail-closed validator pattern informs B6/B7 validators; not reused as dependency. |
| `DurationBudgetPolicy` | `director/duration.py:36` | REUSE (configurable formula) | Deterministic chars-per-second + frame rounding + tolerance; adapt constants/formula for B5 target-duration planning (180–300 s). Versioned. |
| `ScriptRevisionProposalFactory` | `director/revision.py:55` | MIGRATE pattern | Blocking issues → typed proposals never mutating source; the shape for B7 `RevisionProposal` + `ReviewReport` findings. |
| `ContinuityLedgerService` | `continuity/service.py:71` | REUSE (post-lock continuity) | Deterministic ledger + typed `ContinuityIssueCode` for B7 continuity dimension; works on structured draft + outline. |

## 4. V2 screenplay workspace (A/C compatibility surface)

| Symbol | Ref | Decision | Rationale |
|---|---|---|---|
| `ScreenplaySerializer` / `ScreenplayParser` | `screenplay_parser.py:33/77` | **REUSE** | Fountain-style text round-trip + legacy import; sidecar-ID preservation; loss-reporting conversion to structured draft (B6). |
| `ScreenplayValidationGate` | `screenplay_validation.py:44` | REUSE/adapt behind contract | V2 lock-gating + `AssetRequirement`; B8 adapts behind the new lock contract where rules match (synthetic lock hashes forbidden). |
| `ScreenplayDiffEngine` | `screenplay_diff.py:39` | REUSE pattern | Entity-level diff (added/deleted/moved/modified) → B7 structural diff on structured drafts. |
| `ProductionImpactAnalyzer` | `screenplay_impact.py:34` | MIGRATE pattern | Change → downstream invalidation intent; B7/back uses revision-derive semantics. |
| `ScreenplayCommandHandler` + V2 workspace handlers | `screenplay_command_handlers.py:19` | LEAVE (C owns workspace) | V2 workspace stays operational; B adapts read/diff/lock, never redefines. Files carry A/C WIP — B does not edit. |

## 5. Reviewers (media-candidate layer)

| Symbol | Ref | Decision | Rationale |
|---|---|---|---|
| `reviewers/models.py` (`ReviewDimension`, `DimensionResult`, `BlockingDefect`, `CandidateReview`, `SelectionRecord`) | `reviewers/models.py:39..239` | **VP3D-ONLY** | Assess shot/media candidates; dimensions are media-centric (identity/location/prop/camera/dialogue-alignment). B7 defines Story review dimensions (age/safety/format/duration/continuity/beat coverage) + model-assisted narrative review separately. |
| `reviewers/dimensions.py` (`REVIEW_DIMENSIONS`, thresholds, blocking rules) | `reviewers/dimensions.py:43` | VP3D-ONLY (read patterns) | Versioned threshold-policy + blocking-over-aggregate pattern informs B7 quality policy; reuses the semantics, not the dimension set. |

## 6. Errors (taxonomy input)

| Symbol | Ref | Decision | Rationale |
|---|---|---|---|
| `intelligence/.../errors.py` (`VideoKernelError` + typed subclasses, `retryable` flag) | `errors.py` | REUSE/adapt | Parse/empty = transient (retryable); validation/missing-model/locked-mutation = terminal. B0.6 freezes the B-level taxonomy over this base. |
| `core/.../errors.py` domain errors | `errors.py` | REUSE (A-owned) | `LockedRevisionMutationError`, `UnsupportedMajorVersionError`, `BrokenReferenceError` map directly to envelope/lock failures. |

## 7. Caller inventory and zero-caller claims (verified 2026-08-09)

Method: knowledge-graph inbound traces + `rg` across production trees excluding tests/verification/docs/artifacts.

| Service | Production callers | Observed callers | Claim |
|---|---|---|---|
| `CreativeBriefExpander` | none | `scripts/verification/verify_phase6_kernel.py`, `scripts/verification/historical/evaluate_pipeline.py` (fixture/integration harnesses) | zero-caller (production) |
| `StoryOutliner` | none | same harnesses | zero-caller (production) |
| `ScreenplayWriter` | none | same harnesses | zero-caller (production) |
| `DialogueNarrator` | none | same harnesses | zero-caller (production) |
| `EntityExtractor` | none | same harnesses | zero-caller (production) |
| `StyleDesigner` | none | same harnesses | zero-caller (production) |
| `ContinuationService` | none | `scripts/verification/verify_phase6_kernel.py` | zero-caller (production) |
| `PackageAssembler` | none | same harnesses | zero-caller (production) |
| `VideoDirectorService` | none | verify_phase8/9/10/11 + `scripts/produce_phase2{5,6}_evidence.py` | zero-caller (production) |
| `PreproductionModelPort` | none (no production adapter) | unit-test fakes only | zero adapter (production) |

Conclusion: the story chain is reusable source material, not a live pipeline — matches finding F-11. No production dependency edge blocks extraction.

## 8. Owners per decision

| Symbol | Owner | Gate to re-check |
|---|---|---|
| `PromptSpec`, model port | B (reuse) | `STRUCTURED_MODEL_GATE` |
| legacy `video/**` story services | B (wrap/replace via `story/**`) | `B_CONTRACT_CONSUMER_GATE` (B0), `STORY_ARTIFACT_CONTRACT_GATE` (B1) |
| screenplay V2 workspace (`screenplay_parser`, `screenplay_diff`, `screenplay_validation`) | B adapts, C owns workspace | `SCREENPLAY_DRAFT_GATE` |
| `PreproductionModelPort` production adapter | A | `REAL_MODEL_RUNTIME_GATE` |
| envelope/approval/revision/lock authority | A | `LOCKED_SCREENPLAY_GATE` |
| media reviewers, `VideoDirectorService` | VP3D (protected) | regression only |

## Notes

- No code moved in B0. Compatibility = every listed module remains importable and current tests stay green (verified: `tests/contracts/test_story_b0_consumer_freeze.py` + `tests/architecture/test_story_b0_legacy_boundary.py`, 20 passed; A0/C0 contract suites 38 passed).
- New production callers of the soon-to-be-deprecated story services are forbidden by `scripts/check_story_b0_legacy_boundary.py`.
