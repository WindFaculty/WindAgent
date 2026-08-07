# API V2 Workspace Contract Specification

## 1. Overview

The Production Workspace API V2 router (`/api/v2/video-production/workspace`) exposes versioned REST endpoints for snapshot fetching, mutating command execution, and authorized media delivery.

## 2. Endpoints

### 2.1 `GET /api/v2/video-production/workspace/snapshot`
Returns a complete, consolidated `WorkspaceSnapshot` for a project or production session.
- **Parameters**: `project_id` (required), `revision_id` (optional).
- **Response**: Snapshot object containing project state, creative brief, screenplay, shot graph, candidate reviews, cost ledger, and human action status.

### 2.2 `POST /api/v2/video-production/workspace/commands`
Processes mutating workspace actions with strict idempotency and optimistic concurrency controls.
- **Headers**: `X-Idempotency-Key` (required UUID/hash string).
- **Request Body**:
  ```json
  {
    "command_type": "APPROVE_CANDIDATE | REJECT_CANDIDATE | OVERRIDE_CANDIDATE | AUTHORIZE_COST | HUMAN_TAKEOVER | CANCEL_JOB | PUBLISH_DELIVERABLE",
    "project_id": "vp_...",
    "target_revision_id": "rev_...",
    "entity_id": "cand_... | job_...",
    "reason": "Explicit justification text",
    "payload": {}
  }
  ```
- **Response**: Command receipt containing execution status (`COMPLETED | REJECTED_STALE | FAILED`), updated revision ID, and result payload.

### 2.3 `GET /api/v2/video-production/workspace/media/{media_token}`
Delivers authorized, time-limited media streams for browser preview.
- **Security Rule**: Media URLs MUST use tokenized delivery URLs (`/media/tok_...`). Raw file system paths (`file:///...` or `D:\...`) are strictly forbidden to prevent server path leakage.

## 3. Optimistic Concurrency & Stale Commands

Every mutating command MUST specify `target_revision_id`. If the server's current production revision differs from `target_revision_id`, the command is rejected immediately with status `REJECTED_STALE` and HTTP code `409 Conflict`.
