# Equivalence Policy — Video Pre-production Kernel (Phase 6)

Source: plan 02 `§16.4`. This policy is **ratified before** the Phase 6
verdict runs; thresholds are never lowered after seeing results.

## 1. Principle

The canonical kernel does not need to reproduce upstream byte-for-byte. It
must be **semantically equivalent** on the fields that the downstream
Director layer and asset pipeline depend on. Comparison is done on semantic
fields, never on raw text.

## 2. Blocking equivalence fields

| Capability | Blocking equivalence |
|---|---|
| Brief | objective, audience, duration/constraint present and not lost |
| Outline | scene/beat coverage and valid ordering |
| Screenplay | enough scenes, dialogue attribution, narration present |
| Entity extraction | precision/recall on golden fixture ≥ threshold |
| Style | mandatory style constraints preserved |
| Continuation | does not break locked facts and existing IDs |

### 2.1 Brief

`CreativeBrief` must preserve, from the golden fixture's idea/meta:

- `title` non-empty;
- `audience` / `tone` / `genre` non-empty when the source declares them;
- `target_duration_seconds` and `aspect_ratio` preserved or defaulted.

### 2.2 Outline

`StoryConcept` must:

- preserve `premise` + `synopsis` (non-empty when source has them);
- keep `themes` non-empty and fully sorted (deterministic);
- preserve `beats` (in authored order) in `metadata["beats"]`.

### 2.3 Screenplay

`Screenplay` must:

- contain the same number of scenes as the golden source (±0);
- preserve scene order (blocking);
- attribute every dialogue line to a stable character ID;
- include narration (`<action>` content) for scenes that have it.

### 2.4 Entity extraction

Measured on the golden fixture meta:

- **Characters** — precision = correctly attributed characters ÷ extracted
  total; recall = correctly attributed ÷ golden source total. Threshold:
  **precision ≥ 0.9 and recall ≥ 0.9** per golden fixture.
- **Locations** — measured by **recall ≥ 0.9** (every golden setting must be
  present). Extra locations are *expected and permitted*: the kernel
  intentionally folds screenplay scene locations that the meta omits so every
  `scene.location_id` has a matching `LocationBible` (package validation), so
  precision is not a blocking metric for locations.
- Duplicate display names must produce distinct IDs (never merged).

### 2.5 Style

`StyleBible` must keep every mandatory style constraint declared in the brief
(e.g. a `style` value like "anime" or a listed palette). A style response
that drops a declared constraint fails.

### 2.6 Continuation

`ContinuationResult` must:

- preserve all existing scenes and their order from the locked screenplay;
- not renumber existing episode numbers;
- keep existing IDs stable (no regeneration);
- declare an invalidation intent.

## 3. Non-blocking variation (allowed)

- Wording / phrasing of dialogue text (semantic content must match the
  golden fixture attribution, not exact wording).
- Prompt `content_hash` (a new prompt version may change the hash without
  breaking equivalence).
- Whitespace / line wrapping / list ordering beyond the deterministic
  ordering guarantees.

## 4. How the verifier measures it

`verify_phase6_kernel.py`:

1. Builds the golden comparison from the three Phase 5 fixtures (brief +
   pinned provider responses) by running the offline capabilities with a
   deterministic fake model port.
2. For each fixture computes the blocking equivalence fields above.
3. Records a pass/fail per field and per fixture in
   `golden_comparison.json`.
4. `VP6` gate requires every fixture's blocking fields to pass and the
   package validation to succeed.

## 5. Thresholds (ratified, immutable for this phase)

| Metric | Threshold |
|---|---|
| Character precision | ≥ 0.9 |
| Character recall | ≥ 0.9 |
| Location recall | ≥ 0.9 (screenplay-derived extras permitted) |
| Scene order | exact match |
| Scene count | exact match |
| Continuation fact preservation | no locked fact mutated |
