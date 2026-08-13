# Threat Model — Video Production Platform (Phase 26)

Gate: `VP26_SECURITY_VERIFIED`. This document is the machine-readable
`threat_model_manifest.json` written in prose form. Every finding is tied to
the canonical trust boundaries in the Phase 26 plan (§13) and exercised by a
scenario in the security test matrix (§15).

## 1. Assets

| Asset | Where it lives | Why it matters |
|---|---|---|
| Browser account / session / profile / cookie | browser profile store | account takeover → cost abuse, data exposure |
| API / provider secrets | environment, state encryption store | secret leak → impersonation, billing abuse |
| Project screenplay / media (unreleased) | content-addressed store | IP / embargo leak |
| Real-person likeness / voice | audio assets, consent metadata | privacy / right-of-publicity |
| Cost / payment state | cost ledger, budget approvals | financial integrity |
| Approvals / audit evidence | approval ledger, outbox, evidence bundle | release traceability, tamper |
| Local filesystem / database | workspace, SQLite/PostgreSQL | integrity + confidentiality |

## 2. Trust boundaries

```text
internet assets        → downloader quarantine          (SE05)
model output           → structured validator           (SE07)
browser UI             → browser runtime adapter / state machine   (SE03, SE08, SE09, SE10)
browser profile        → worker / session store         (SE02)
media files            → decoder / FFmpeg sandbox       (SE06, SE08)
API clients            → authorization / domain cmds    (SE11, SE12)
evidence / logs        → redaction / access control     (SE01)
local filesystem       → path sandbox                   (SE04)
storage                → retention / invalidation       (SE13)
cost                   → hash-bound approvals           (SE12)
```

Each boundary has a **fail-closed** control; the `test` column is the
scenario in `security_test_receipts/` that proves it.

## 3. Findings (all low residual risk, none release-blocking)

| ID | Boundary | Threat | Control | Test | Residual |
|---|---|---|---|---|---|
| SEC-TM-001 | evidence/logs | secret canary in logs/events/errors/screenshots | canonical redaction + shell masking | SE01 | low |
| SEC-TM-002 | browser profile | profile readable at rest | AES-GCM at rest + isolated copies | SE02 | low |
| SEC-TM-003 | browser UI | off-domain navigation / malicious redirect | domain allowlist + redirect revalidation | SE03 | low |
| SEC-TM-004 | local filesystem | `../` / absolute / symlink escape | canonical path sandbox (resolve-based) | SE04 | low |
| SEC-TM-005 | internet assets | SSRF to private/metadata endpoints | SSRF-safe URL/IP + DNS rebinding guard | SE05 | low |
| SEC-TM-006 | media files | exec/polyglot/bomb/metadata payloads | ordered validation pipeline + EXIF strip | SE06 | low |
| SEC-TM-007 | model output | injection text becomes an instruction | typed envelopes + typed FFmpeg plan + shell policy | SE07 | low |
| SEC-TM-008 | browser UI / media | eval / cookie export / destructive shell | bounded action policy + forbidden shell patterns | SE08 | low |
| SEC-TM-009 | browser UI | unapproved upload | approved asset store enforcement | SE09 | low |
| SEC-TM-010 | browser UI / API | auto-confirmed terms/payment/delete/publish | confirmation-gated policy + approval gating | SE10 | low |
| SEC-TM-011 | API clients | cross-project media/command/event | media token gate + idempotency + revision check + project-scoped events | SE11 | low |
| SEC-TM-012 | API / cost | stale approval reopens a gate | hash-bound approvals + estimate-hash binding | SE12 | low |
| SEC-TM-013 | storage | data outlives retention / deletion leaks | retention cleanup + non-destructive invalidation + content-free receipts | SE13 | low |

## 4. Pen-test posture

- A pen-test finding that is critical/high and exploitable **in release scope**
  blocks release (plan §15). Current findings are all `low` with a release
  decision of `acceptable-for-0.1`; `SEC-001` (shell redaction gap) was found
  by SE01 and **closed by fix** in this phase.
- Hosts without symlink privilege record the SE04 symlink sub-observation as
  N/A; the boundary check itself (`Path.resolve()` containment) is
  platform-independent and CI-on-Linux covers the symlink case.

## 5. Coverage proof

`threat_model_manifest.json` lists all boundaries above and the verifier
(`verify_phase26_security.py`) fails `VP26_SECURITY_VERIFIED` if any
boundary is missing from the manifest or any finding lacks a control, test,
severity and release decision.
