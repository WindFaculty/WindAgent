# End-to-End Production Runbook (Release 0.1 Scope)

## 1. Overview

This runbook defines the controlled 14-step end-to-end execution sequence for Release 0.1 of the WindAgent Video Production Pipeline.

## 2. Release 0.1 Scope & Constraints

- **Duration**: 30–45 seconds.
- **Scenes**: 2 scenes.
- **Shots**: 6 planned shots.
- **Characters**: Maximum 2 characters.
- **Location**: 1–2 locations.
- **Aspect Ratio**: 16:9 (1920x1080 main, 1280x720 proxy).
- **Candidates**: Maximum 2 candidates per shot.
- **Concurrency**: 1 job at a time.
- **Automation Rate**: Minimum 80% shots completed without manual media editing.

## 3. The 14-Step Runbook Execution Pipeline

```text
Step  1: CREATE_PROJECT / freeze run manifest
Step  2: Idea → concepts → selected concept
Step  3: Screenplay → approval/lock
Step  4: Character/location bibles → references → approval
Step  5: Cinematic plan → shot graph/continuity → approval/lock
Step  6: Cost estimate → approval/reserve
Step  7: Flow image generation → candidate review
Step  8: Flow video generation (one job at a time)
Step  9: Technical/VLM/cross-shot review
Step 10: TTS/alignment/audio mix
Step 11: FFmpeg assembly
Step 12: Final media quality verification
Step 13: Final-cut approval
Step 14: Publish final deliverable + production report
```

## 4. Checkpoint & Evidence Rules

Every step must emit a content-addressed checkpoint receipt before advancing to the next step. If any step fails verification or exceeds the approved budget reserve, execution halts immediately with status `BLOCKED`.
