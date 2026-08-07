# Browser Evidence & Redaction Policy (Phase 12)

**Plan:** 04 §8.5 · **Contract owner:** `tools/windagent_tools/browser/evidence_capture.py`

## 1. Principle

Every bounded browser action writes a structured evidence record. Evidence
**never** contains raw screenshots, full page text, URLs with credentials,
cookies, tokens, payment data, local profile paths, or any secret material —
only **hashes** of captured content plus sanitized semantics.

## 2. Evidence schema (plan §8.5)

```text
action_id                 deterministic? no — per-action uuid
session_id                session identity
operation                 typed operation name
target_semantics          sanitized target string (URL secrets redacted)
started_at / finished_at  timestamps
result_state              SUCCESS | BLOCKED | FAILED | CANCELLED | TIMED_OUT | HUMAN_REQUIRED
redacted_screenshot_hash  sha256 of screenshot bytes (never the image)
snapshot_hash             sha256 of accessibility snapshot text
error_class               exception class name (bounded length)
```

## 3. Redaction rules

1. **URL query secrets** are redacted by `BrowserAuditLogger.sanitize_url_string`
   (`token=`, `api_key=`, `auth=`, `secret=`, `password=`, `cred=`, … → `[REDACTED]`).
2. **Screenshot content** is never stored: only `redacted_screenshot_hash`
   (sha256 over the file bytes) is recorded.
3. **Snapshot content** is never stored: only `snapshot_hash`.
4. **Target semantics** are truncated to 512 chars and sanitized.
5. `error_class` is the exception class name (≤128 chars), never the message
   with secrets.
6. Local profile paths never appear in evidence — the runtime only holds the
   opaque `profile_key`.

## 4. Result-state coverage

Evidence is written for **every** outcome — success, policy block, action
failure, cancellation, timeout — so an audit trail is never partial.

## 5. Testability

`BrowserEvidenceRecorder` accepts a `redact_screenshot` hook so tests can
inject a deterministic fake redactor; the recorder itself never inspects
screenshot content.
