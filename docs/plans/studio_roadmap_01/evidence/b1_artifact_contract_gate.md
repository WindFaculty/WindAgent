# B1 Evidence — STORY_ARTIFACT_CONTRACT_GATE

Gate owner: Plan B (A/C consumers co-review). Baseline: see `b0_*` evidence.

## 1. Registry and duplicate-model check

- Registered artifact types: **13/13** (all frozen types).
- Duplicate canonical models: **none**.

| Artifact type | Content model | Validator | Golden | Invalid fixtures |
|---|---|---|---|---|
| `BeatSheet` | `BeatSheet` | `validate_beat_sheet` | `golden/BeatSheet.json` | 10 invalid cases exercise the registry |
| `CharacterCanon` | `CharacterCanon` | `validate_character_canon` | `golden/CharacterCanon.json` | 10 invalid cases exercise the registry |
| `CreativeBrief` | `CreativeBrief` | `validate_creative_brief` | `golden/CreativeBrief.json` | 10 invalid cases exercise the registry |
| `EpisodeOutline` | `EpisodeOutline` | `validate_episode_outline` | `golden/EpisodeOutline.json` | 10 invalid cases exercise the registry |
| `IdeaCandidateSet` | `IdeaCandidateSet` | `validate_idea_candidate_set` | `golden/IdeaCandidateSet.json` | 10 invalid cases exercise the registry |
| `LockedScreenplayPackage` | `LockedScreenplayPackage` | `validate_locked_package` | `golden/LockedScreenplayPackage.json` | 10 invalid cases exercise the registry |
| `LockedScreenplayReceipt` | `LockedScreenplayReceipt` | — | `golden/LockedScreenplayReceipt.json` | 10 invalid cases exercise the registry |
| `ReviewReport` | `ReviewReport` | `validate_review_report` | `golden/ReviewReport.json` | 10 invalid cases exercise the registry |
| `RevisionProposal` | `RevisionProposal` | `validate_revision_proposal` | `golden/RevisionProposal.json` | 10 invalid cases exercise the registry |
| `ScreenplayDraft` | `ScreenplayDraft` | `validate_screenplay_draft` | `golden/ScreenplayDraft.json` | 10 invalid cases exercise the registry |
| `SelectedIdea` | `SelectedIdea` | `validate_selected_idea` | `golden/SelectedIdea.json` | 10 invalid cases exercise the registry |
| `StoryBible` | `StoryBible` | `validate_story_bible` | `golden/StoryBible.json` | 10 invalid cases exercise the registry |
| `WorldBible` | `WorldBible` | `validate_world_bible` | `golden/WorldBible.json` | 10 invalid cases exercise the registry |

## 2. Golden fixture report (Vietnamese rabbit-and-kite slice, 5-8, 240 s)

- All 13 golden artifacts: deterministic serialization round trip + registered validator pass.
- Canon ID traceability: `ch_rabbit`, `ch_kite`, `loc_field`, `loc_river`, `prop_kite`, beats `b1-b4`, outline scenes `s1-s4`, draft scenes `dscn_1-4`.
- Draft duration: 40+80+60+60 = **240 s** (target 240, tolerance 15) — inside the 180-300 s envelope.
- Golden file checksums: `story_artifacts/checksums.json` (13 files).

## 3. Invalid fixture report (fail-closed)

- **10** invalid fixtures; every one is rejected at parse time or fails validation:
  - candidate count rule (2 candidates) — parse rejection
  - duplicate candidate IDs — validation BLOCKING
  - unknown schema version `studio.artifact/v2` — fail closed
  - unknown artifact type — discriminator rejection
  - malformed JSON — parse rejection
  - dialogue attribution violation — `DIALOGUE_ATTRIBUTION` BLOCKING
  - outline duration 400 s — `DURATION_BOUND` BLOCKING
  - package manifest missing lineage — `MANIFEST_MISSING_REF` BLOCKING
  - envelope-field leak in content — flagged by the boundary checker (never a canonical artifact)
  - oversized scene text — `FIELD_TOO_LONG` WARNING (fails strict pass)

## 4. Compatibility matrix

| Legacy symbol | B1 decision | Canonical home | Adapter |
|---|---|---|---|
| `CreativeBrief` (video) | REUSE -> WRAP | `story/ideation/models.py` | `from_video_brief` (lossless + documented defaults) |
| `StoryConcept` | DEPRECATE single-concept | projection from `IdeaCandidate` | `to_story_concept` with explicit loss metadata |
| `DialogueLine` | REUSE (compose) | `DraftDialogueLine` (same field vocabulary) | `from_video_screenplay` + `dialogue_line_loss` |
| `Screenplay` (V2 text) | REUSE as read model; structured draft is authority | `story/screenplay/models.py` | `from_video_screenplay` (loss-reporting) |
| `CharacterBible`/`LocationBible`/`PropBible` | REUSE as mapping input | `CharacterCanon`/`WorldBible` entries | B4 mapping adapters (future) |
| `VideoProductionPackage` | REUSE hash/lineage semantics | `StoryContent.content_hash()` + package manifest | registry + envelope hash |
| A `IdeaCandidate`/`IdeaCandidateSet` placeholders | REPLACED by B canonical aliases | `story/ideation/models.py` | A envelope re-exports (one canonical model) |

## 5. A envelope wrapping

- `StoryArtifactEnvelope.build(...)` wraps canonical B content; envelope hash == `canonical_content_hash` (verified in tests).
- Content models carry zero envelope fields (checked per registered model).
- `story_task_io.json` (B0) remains `proposal-awaiting-a-approval`; this gate pins the content schemas behind it.

## 6. Gate verdict

**`STORY_ARTIFACT_CONTRACT_GATE`: PASS (B-side evidence).**

- Schema bundle: 13 JSON Schemas generated from the registered canonical models (`story_artifacts/schemas/`).
- Golden + invalid fixture checksums: `story_artifacts/checksums.json`.
- Duplicate-model check: none (see §1).
- C-side: TypeScript fixture generation and API mapping remain C's half of the gate (Plan C phase), to be co-signed at contract review.
