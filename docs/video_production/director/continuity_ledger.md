# Continuity Ledger (Phase 10)

- **Gate:** `VP10_CONTINUITY_LEDGER_VERIFIED`
- **Owner:** `core/windagent_core/domain/video_production/continuity.py` (models +
  validator) and `intelligence/windagent_intelligence/video/continuity/service.py`
  (builder)
- **Ratified by:** `../../intelligence/windagent_intelligence/video/director/` (plan 03 đã retired) §17-§21

## 1. Purpose

The ledger tracks the visual/cinematic state flowing through the shot graph
and turns continuity into a constraint that can be **compiled, reviewed and
invalidated** — not just prose. Blocking defects fail closed before rendering;
approved human overrides are audited; every change is traceable to a source.

## 2. Ledger model (plan §18)

The ledger is not a single final snapshot. Each shot records:

```text
incoming_state        — state entering the shot (screenplay/bible/predecessor)
required_state        — fields that MUST hold a value (identity, references)
allowed_changes       — fields the shot is allowed to mutate
planned_changes       — changes the shot proposes (with before/after/source)
outgoing_state        — state after the shot
continuity_assertions — reviewed invariants (180-degree, identity hash, …)
```

State fields cover at minimum: character identity / age / hair / clothing /
injury / emotion, frame position, eyeline, screen direction, prop possession /
location / state, location / lighting / weather / time / scene geography,
door / vehicle / room state, camera side and the 180-degree rule.

Every important field records a **source**:

```text
SCREENPLAY_FACT | BIBLE_FACT | APPROVED_REFERENCE | DIRECTOR_DECISION
| PREDECESSOR_OUTPUT | HUMAN_OVERRIDE
```

## 3. Initial state (plan §19.1)

`ContinuityLedgerService` builds the initial state deterministically from the
package:

- character identity = the approved portrait reference (`APPROVED_REFERENCE`);
- appearance / clothing = `CharacterBible.visual_traits` / `costume_descriptions`
  (`BIBLE_FACT`);
- prop possession / state from `PropBible` (`BIBLE_FACT`);
- approved reference hashes from `assets[].content_hash` (`APPROVED_REFERENCE`);
- scene time-of-day (`SCREENPLAY_FACT`) and location lighting / atmosphere
  (`BIBLE_FACT`).

Missing required identity/reference values become issues rather than guesses.

## 4. State transition (plan §19.2)

- Shots are walked in **deterministic topological order**; the outgoing state
  of a predecessor becomes the incoming state of its dependents.
- A **scene boundary** resets location / weather / time and camera side
  (`NEUTRAL`, re-establish geography) while **identity continues across scenes**.
- A planned change outside the shot's `allowed_changes` is a **blocking**
  `CHANGE_OUTSIDE_ALLOWED` defect.
- A prop change without a screenplay action is a **blocking**
  `PROP_UNEXPLAINED_CHANGE` defect.
- An identity/reference mismatch against the approved hash is a **blocking**
  `IDENTITY_HASH_MISMATCH` defect.
- A camera-side flip inside a scene (180-degree rule) is a **blocking**
  `CAMERA_SIDE_VIOLATION` defect.
- Parallel shots (no blocking edge between them) writing conflicting canonical
  state produce a **blocking** `PARALLEL_CONFLICT` issue until a merge rule
  exists.

## 5. Diff & review (plan §19.3)

`ContinuityDiff` records machine-readable diffs:

```text
field | before | expected | observed | source | severity | blocking
```

Human overrides (`HumanContinuityOverride`) carry `actor`, `reason`,
`target_revision`, `field`, `before/after` and `timestamp`. An override is
**appended** as evidence — it never rewrites the recorded incoming/outgoing
states of earlier shots (no retroactive mutation).

## 6. Invalidation intent (plan §19.4)

The ledger ties every changed field to its source shot and revision, so later
phases can determine which shots, sequences and prompts/frames/clips become
stale when a reference, wardrobe/prop, camera-side or override changes.

## 7. Determinism & hash

`compute_ledger_hash` is a deterministic SHA-256 over the canonical ledger
payload + ledger version + source graph/plan/package hashes. Same inputs →
same hash; any entry/override/diff/version/source change → new hash. The
ledger is fully deterministic and never calls a provider.
