# B9 Evidence — PLAN_B_HANDOFF_GATE + SCREENPLAY_RUNTIME_GATE (B-side)

Gate owner: Plan B (+ A runtime seam). Baseline: A5 STORY_WORKER_GATE (real
SQL queue + independent worker), A6 real model route, B3-B8 handlers,
B8 lock package. Fixtures: `fixtures/studio_contract_v0.1/story_chain/`.

## 1. Handler manifest (all nine frozen task types)

- Model-port tasks (7): studio.story.beats.generate, studio.story.bible.generate, studio.story.idea.generate, studio.story.outline.generate, studio.story.review, studio.story.revise, studio.story.screenplay.generate.
- Pure tasks (2): studio.story.idea.evaluate, studio.story.lock.
- Input/output artifact types per handler match `story_task_io.json`
  (asserted by `tests/contracts/test_story_b9_handoff_gate.py`).

## 2. Full chain through the real runtime seam (SQL queue + worker)

Chain executed node by node through `SqlDurableTaskQueue` +
`ProductionWorker` + `StudioRuntimeAdapter` + `StudioUnitOfWork`; every task
finalizes and persists content-addressed artifacts. Fixture model responses
exist ONLY at the provider boundary; every content artifact is produced by
the live services, and the lock lineage references the ACTUAL persisted
artifact hashes of this run.

| Node | Task | Inputs | Outputs | Output hashes |
|---|---|---|---|---|
| `idea.generate` | `studio.story.idea.generate` | CreativeBrief | IdeaCandidateSet | e5c416383aa4 |
| `idea.evaluate` | `studio.story.idea.evaluate` | IdeaCandidateSet | IdeaCandidateSet | 5ca950192bee |
| `bible.generate` | `studio.story.bible.generate` | SelectedIdea | StoryBible,WorldBible,CharacterCanon | be395a3c7205,8bc657275bbc,7142bc363c31 |
| `beats.generate` | `studio.story.beats.generate` | StoryBible,WorldBible,CharacterCanon | BeatSheet | f64db297f2ba |
| `outline.generate` | `studio.story.outline.generate` | BeatSheet | EpisodeOutline | 6e6653b711b7 |
| `screenplay.generate` | `studio.story.screenplay.generate` | EpisodeOutline | ScreenplayDraft | dde24760a196 |
| `review` | `studio.story.review` | ScreenplayDraft | ReviewReport | 006f52382047 |
| `revise` | `studio.story.revise` | ScreenplayDraft,ReviewReport | RevisionProposal,ScreenplayDraft | 945a117ded7b,7e0f33992a53 |
| `review2` | `studio.story.review` | ScreenplayDraft | ReviewReport | ba691b70e50b |
| `lock` | `studio.story.lock` | ScreenplayDraft,ReviewReport | LockedScreenplayReceipt,LockedScreenplayPackage | 2c1b11fa6bb0,305c803b0fe3 |

- Vietnamese rabbit/kite slice: ages 5-8, target 240s, `vi`.
- Selection replayed deterministically on the evaluated candidate set (no
  canned SelectedIdea); revised draft `draft_rabbit_kite_r2` + clean review
  PASS; A-issued receipt (AUTO) drives the final lock.

## 3. Final LockedScreenplayPackage

- Package ref hash: `305c803b0fe30226…`
  (artifact `art_305c803b0fe30226`), persisted by the worker and
  validated by `LockService` + `validate_locked_package` before persistence.
- Post-lock mutation refused (`HASH_MISMATCH` -> derived revision, B8);
  package immutable + idempotent (B8 evidence).

## 4. No canned final content

- The final package manifest hashes are computed from artifacts the worker
  persisted from live handler output; a pre-baked fixture response could
  never reproduce them (gate test re-runs the chain and compares).
- Certification profile rejects fixture providers (`assert_not_fixture`);
  this evidence run is the non-certification stub path (A5 convention).

## 5. No tolerant free-text parsing on canonical paths

Tolerant-parser scan (B2, whole story tree):
**0 violation(s)**.

## 6. Gate verdict

**`PLAN_B_HANDOFF_GATE` + `SCREENPLAY_RUNTIME_GATE`: PASS (B-side evidence).**

- Chain: `chain_run.json` (checksum
  `096c822918acb948…`).
- Manifest: `handler_manifest.json`; checksums: `checksums.json`.
- A-side (full-DAG auto-drive with receipt issuance at the lock node) and
  C-side (consumer schemas) halves are co-signed by their plan owners at
  contract review; C schema compile is asserted in C0/C2 gates.
