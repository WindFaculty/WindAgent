# Event Catalog — Video Production Protocol

Source: `core/windagent_core/events/video_production.py`

## Envelope

Every event carries:

```text
event_id          unique opaque UUID
event_type        dotted taxonomy (video_production.*)
schema_version    MAJOR.MINOR.PATCH (fail closed on unknown MAJOR)
project_id        stable project ID
revision_id       revision the event belongs to
aggregate_id      owning aggregate
causation_id      event that caused this one (optional)
correlation_id    correlation chain (default random UUID)
occurred_at       UTC timestamp
payload           event-specific data
```

## Catalog

| Event | Dotted type |
|---|---|
| `VideoProjectCreated` | `video_production.project_created` |
| `ConceptApproved` | `video_production.concept_approved` |
| `ScreenplayGenerated` | `video_production.screenplay_generated` |
| `ScreenplayLocked` | `video_production.screenplay_locked` |
| `CharacterBibleApproved` | `video_production.character_bible_approved` |
| `LocationBibleApproved` | `video_production.location_bible_approved` |
| `CinematicPlanGenerated` | `video_production.cinematic_plan_generated` |
| `ShotPlanLocked` | `video_production.shot_plan_locked` |
| `GenerationSubmitted` | `video_production.generation_submitted` |
| `GenerationCompleted` | `video_production.generation_completed` |
| `GenerationRejected` | `video_production.generation_rejected` |
| `HumanActionRequired` | `video_production.human_action_required` |
| `SequenceCompleted` | `video_production.sequence_completed` |
| `FinalVideoPublished` | `video_production.final_video_published` |

## Valid transitions

```text
project_created
  → concept_approved
  → screenplay_generated
  → screenplay_locked
  → character_bible_approved ┐
  → location_bible_approved ─┤ (either order, both may precede)
  → cinematic_plan_generated ↓
  → shot_plan_locked
  → generation_submitted
      ├→ generation_completed → sequence_completed → final_video_published
      ├→ generation_rejected → generation_submitted | human_action_required
      └→ human_action_required → generation_submitted | generation_rejected
screenplay_generated → screenplay_generated  (revision cycle)
final_video_published is terminal
```

Enforcement: `VideoProductionEventTransitions.validate_sequence(events)`.

## Idempotency

Consumers MUST be idempotent by `event_id`:

- `EventIdempotencyGuard.process(event)` returns `True` only the first time a
  given `event_id` is seen.
- Duplicate events never create duplicate generations or approvals.

## Security

- Event payloads are redacted through the canonical
  `redact_event_payload` before persistence.
- No selectors, cookies, Flow project URLs, or browser session objects ever
  appear in event payloads or the event catalog.
