# B1 Evidence — Story Validation-Code Catalog

Contract: `studio.contract/v0.1`; artifact schema `studio.artifact/v1alpha1`; generated 2026-08-09T00:00:00Z.

Stable machine codes (frozen B0 taxonomy + B1 artifact codes). Translated labels never replace codes (C contract invariant 3).

| Code | Dimension | Default severity | Description |
|---|---|---|---|
| `AGE_FIT` | AGE_FIT | WARNING | Content/lexicon/theme appropriate to the age band. |
| `BEAT_COVERAGE` | BEAT_COVERAGE | BLOCKING | Outline/screenplay covers every beat. |
| `BEAT_ORPHAN` | BEAT_COVERAGE | WARNING | Beat is not referenced by any outline scene. |
| `BRIEF_ADHERENCE` | BRIEF_ADHERENCE | WARNING | Theme/tone/constraints/language coverage vs normalized brief. |
| `CANON_REFERENCE_INTEGRITY` | CANON_REFERENCE_INTEGRITY | BLOCKING | Every ID traces to bibles/canon; no free-form names alone. |
| `CAUSAL_ORDER` | CAUSAL_ORDER | WARNING | Beat/scene causal and temporal order. |
| `CONTINUITY` | CONTINUITY | WARNING | Cross-scene continuity. |
| `DIALOGUE_ATTRIBUTION` | FORMAT_VALIDITY | BLOCKING | Dialogue references a character not present in the scene. |
| `DIALOGUE_EMPTY` | FORMAT_VALIDITY | BLOCKING | Dialogue text empty. |
| `DIFF_MISMATCH` | FORMAT_VALIDITY | BLOCKING | Diff summary does not match the actual change list. |
| `DUPLICATE_NAME` | CANON_REFERENCE_INTEGRITY | WARNING | Distinct IDs share a display name. |
| `DURATION_BOUND` | DURATION_FIT | BLOCKING | Total planned duration outside the 180-300 second envelope. |
| `DURATION_FIT` | DURATION_FIT | WARNING | Estimated duration fits the configured target budget. |
| `DURATION_SUM` | DURATION_FIT | BLOCKING | Sum of scene/beat seconds outside the configured tolerance. |
| `FIELD_EMPTY` | FORMAT_VALIDITY | BLOCKING | Required field is empty. |
| `FIELD_TOO_LONG` | FORMAT_VALIDITY | WARNING | Field exceeds the documented maximum length. |
| `FORMAT_VALIDITY` | FORMAT_VALIDITY | BLOCKING | Structured schema validity incl. dialogue attribution and scene/order/ID stability. |
| `IDEA_COUNT` | FORMAT_VALIDITY | BLOCKING | Candidate set holds exactly 3-5 distinct candidates. |
| `IDEA_DUPLICATE` | FORMAT_VALIDITY | BLOCKING | Duplicate candidate IDs or near-duplicate titles. |
| `IDEA_REQUIRED_FIELD` | FORMAT_VALIDITY | BLOCKING | Required idea field missing/empty. |
| `ID_STABILITY` | FORMAT_VALIDITY | BLOCKING | Scene/beat/dialogue ordering or ID stability violated. |
| `ID_UNIQUE` | FORMAT_VALIDITY | BLOCKING | Duplicate stable ID within an artifact. |
| `LANGUAGE_CONSISTENCY` | LANGUAGE_CONSISTENCY | WARNING | Single language/register across the artifact. |
| `LOCK_STATE` | FORMAT_VALIDITY | BLOCKING | Receipt/package state not READY_FOR_PRODUCTION. |
| `MANIFEST_DUPLICATE` | CANON_REFERENCE_INTEGRITY | BLOCKING | Manifest lists the same artifact more than once. |
| `MANIFEST_HASH` | CANON_REFERENCE_INTEGRITY | BLOCKING | Manifest entry hash is not a 64-char SHA-256 hex digest. |
| `MANIFEST_MISSING_REF` | CANON_REFERENCE_INTEGRITY | BLOCKING | Locked package manifest misses a required lineage artifact. |
| `ORDER_SEQUENCE` | FORMAT_VALIDITY | BLOCKING | Order values must be unique and start at 1. |
| `REF_MISSING` | CANON_REFERENCE_INTEGRITY | BLOCKING | Reference points to a missing canon/artifact ID. |
| `RELATIONSHIP_CYCLE` | CANON_REFERENCE_INTEGRITY | WARNING | Relationship cycle detected in canon. |
| `REVIEW_VERDICT` | NARRATIVE_QUALITY | BLOCKING | Review verdict inconsistent with findings (blocking findings present but PASS). |
| `REVISION_BUDGET` | NARRATIVE_QUALITY | BLOCKING | Revision iteration budget exhausted; iteration_exhausted terminal state. |
| `REVISION_STALE` | NARRATIVE_QUALITY | BLOCKING | Revision proposal references findings not present in the reviewed report. |
| `SAFETY_AGE_UNSUITABLE` | SAFETY | BLOCKING | Content unsuitable for the declared audience band. |
| `SAFETY_PROHIBITED` | SAFETY | BLOCKING | Prohibited content detected; artifact fails closed. |
| `SCENE_COUNT_BOUND` | DURATION_FIT | WARNING | Scene count outside the configured min/max band. |
| `SCENE_ORPHAN` | BEAT_COVERAGE | WARNING | Outline scene references an unknown beat. |
| `UNKNOWN_REF_KIND` | CANON_REFERENCE_INTEGRITY | WARNING | Reference kind is not part of the frozen vocabulary. |
| `WORLD_RULE_COMPLIANCE` | WORLD_RULE_COMPLIANCE | WARNING | World-rule consistency; conflicts surfaced, never auto-mutated. |
