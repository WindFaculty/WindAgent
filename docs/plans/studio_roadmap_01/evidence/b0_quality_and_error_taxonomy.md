# B0 Evidence — Quality Dimensions, Severities, and Error/Retry Taxonomy

Frozen B-level taxonomy for scoring, review, findings, approval, and failure classification. Supplements the A-owned envelope/error contract (`studio_contract_v0.1/errors.json`) with Story-specific content semantics.

## 1. Quality dimensions (B3 idea, B6/B7 screenplay)

| ID | Dimension | Stage | Deterministic / model-assisted | Notes |
|---|---|---|---|---|
| `AGE_FIT` | Age suitability (final slice: ages 5–8) | B3/B6/B7 | deterministic check + model reviewer secondary | Content/lexicon/theme appropriate to age band. |
| `SAFETY` | Safety / prohibited content | B3/B6/B7 | deterministic (blocking) | Prohibited content makes an artifact fail closed. |
| `BRIEF_ADHERENCE` | Adherence to normalized brief | B3 | deterministic rubric | theme/tone/constraints/lang coverage. |
| `CLARITY` | Clarity of logline/premise | B3 | model-assisted | |
| `EMOTIONAL_ARC` | Emotional arc completeness | B3 | model-assisted | |
| `ORIGINALITY` | Originality | B3 | model-assisted | |
| `DURATION_FIT` | Fits stated duration budget | B3/B5/B6 | deterministic formula | 180–300 s planning. |
| `PRODUCTION_FEASIBILITY` | Provider-neutral feasibility | B3/B5/B6/B7 | deterministic signals | no engine code. |
| `CANON_REFERENCE_INTEGRITY` | All IDs trace to bibles/canon | B4/B5/B6 | deterministic (blocking) | no free-form names alone. |
| `WORLD_RULE_COMPLIANCE` | World-rule consistency | B4/B6/B7 | deterministic | conflicts surfaced as findings, not auto-mutation. |
| `LANGUAGE_CONSISTENCY` | Single language/register | B4/B6 | model-assisted | |
| `CAUSAL_ORDER` | Beat/scene causal & temporal order | B5/B6 | deterministic | |
| `BEAT_COVERAGE` | Outline covers every beat | B6/B7 | deterministic | |
| `FORMAT_VALIDITY` | Structured schema validity | B6/B7 | deterministic (blocking) | includes dialogue attribution, scene/order/ID stability. |
| `CONTINUITY` | Cross-scene continuity | B6/B7 | deterministic reviewer + model reviewer | reuse `ContinuityLedgerService` semantics. |
| `NARRATIVE_QUALITY` | Model-assisted narrative review | B7 | model-assisted | human-required when policy says so. |

Weights, thresholds, tie-breaking, and the age/duration formula are deterministic, versioned, and testable outside a provider (rule 5).

## 2. Finding severity model

| Severity | Meaning | Approval effect |
|---|---|---|
| `INFO` | Observation only | never blocks; reported in `ReviewReport`. |
| `WARNING` | Risk/non-conformance | approvable **only** if `ApprovalPolicy` permits warnings; decision is hash/revision bound. |
| `BLOCKING` | Must fix before lock | draft cannot lock; produces a `RevisionProposal`. |

Finding shape (frozen): stable `code`, `severity`, `location` (JSON-pointer / model path), `evidence`, `remediation`, `source` (deterministic reviewer / model reviewer / human).

## 3. Error / retry taxonomy (Story boundary)

Terminal (never silently retried; terminal `StudioTaskResult.error`, failure closed):

- `STORY_VALIDATION_FAILURE` — domain/structure invalid; repair budget exhausted or content unsafe.
- `STORY_SCHEMA_FAILURE` — output does not match the declared schema after exactly one repair attempt.
- `STORY_SAFETY_FAILURE` — prohibited/age-unsafe content.
- `STORY_STALE_INPUT` — input artifact hash/revision stale (maps to A `STALE_REVISION`/`ARTIFACT_HASH_MISMATCH`).
- `STORY_LOCKED_MUTATION` — post-lock edit without a derived revision (`LockedScreenplayMutationError`).
- `STORY_CAPABILITY_MISSING` — capability not available (maps to A `CAPABILITY_UNAVAILABLE`).

Transient (provider retry budget, counted separately from creative revision):

- `STORY_PROVIDER_TRANSIENT` — provider I/O/route failure (maps to A `PROVIDER_UNAVAILABLE`).
- `STORY_EMPTY_RESPONSE` / `STORY_PARSE_TRANSIENT` — empty/broken-but-repairable output (reuse `EmptyResponseError`/`ResponseParseError` retryable semantics).

Non-separation guard (rule/R1): provider retry attempt count and creative revision iteration count are DIFFERENT fields/events. A review/revision loop that consumes retries or runs forever fails deterministically (`iteration_exhausted`).

## 4. Policy knobs (frozen for B7)

- `maximum_review_revisions` (creative iterations) — approval policy `ApprovalPolicy.maximum_review_revision_iterations`.
- `maximum_provider_retries` — separate provider-level budget.
- Threshold map: checkpoint → dimension → pass threshold / confidence floor / blocking rule (reuse `reviewers/dimensions.py` pattern, Story dimension set).
- Human override path: only Plan A's hash/revision-bound approval command; never lowers thresholds or auto-approves (rule 6).

## 5. Consumption

- B3 scoring engine uses the dimension weights (§2 of ledger) — drafts `ScoreRubricVersion`.
- B7 `ReviewReport` uses severities + finding shape; `RevisionProposal` references `input_hash` + accepted findings.
- Lock (B8) requires zero blocking findings + policy-required approvals; `LockedScreenplayPackage` checksummed.
