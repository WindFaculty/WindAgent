# Web & Desktop Workspace Information Architecture

## 1. Overview

The WindAgent Production Workspace provides a unified, cross-platform (Web and Desktop) interface for supervising, approving, pausing/resuming, and overriding video production workflows. 

Strict Authority Boundary: The workspace UI is an observational view and command client over API V2. It NEVER directly mutates database files, storage artifacts, or maintains independent backend state authority.

## 2. Vertical UX Slices

The workspace interface is organized into three primary vertical slices:

### Slice 1 — Project & Creative Authority
- **Projects Dashboard**: Project listing, active run status, credit balance summary, and project selection.
- **Creative Brief Inspector**: Target audience, style parameters, aspect ratio, tone, duration limits, and brief locking state.
- **Screenplay Editor / Viewer**: Scene breakdown, dialogue lines, lock indicators, and screenplay revision history.
- **Character & Location Bibles**: Visual identity cards, voice profiles, likeness consent state, and reference image bindings.

### Slice 2 — Director & Generation Supervision
- **Storyboard & Shot Board**: Shot sequence graph, dependency status, camera decisions, prompt block inspection, and shot state tracking.
- **Continuity Inspector**: Cross-shot character appearance consistency, prop preservation, time-of-day alignment, and active continuity issue flags.
- **Flow Session & Generation Queue**: Active browser session status, worker pool health, pending generation jobs, and current retry attempts.

### Slice 3 — Review, Cost & Delivery
- **Candidate Comparison Panel**: Side-by-side video/image candidate comparison, per-dimension evaluation scores, defect flags, confidence rating, and human approval/override actions.
- **Cost Ledger & Budget Panel**: Estimated credits, reserved credits, observed debits, remaining budget, and credit top-up requests.
- **Timeline & Post-Production View**: EDL timeline, transition indicators, audio ducking tracks, subtitle bounds, and final render triggers.
- **Final Deliverable Review**: Media player for final MP4, proxy video, poster thumbnail, verification receipts, and final-cut approval button.

## 3. Navigation & Access Control

- All mutating actions (Approve Candidate, Override Candidate, Authorize Cost Reserve, Trigger Human Takeover, Cancel Run, Publish Final Cut) require explicit user role permissions.
- Action buttons are dynamically enabled or disabled based on optimistic revision state (`revision_id`) and remaining credit balance.
