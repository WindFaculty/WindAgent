# Audit and Redaction (Phase 26 §14.7)

Gate: `VP26_SECURITY_VERIFIED` — scenario **SE01** provides redaction
evidence; the evidence-mode verifiers (Phase 21–26) enforce the rest.

## 1. Audit records

Canonical audit trails capture `actor / action / target / revision / result`
without secrets:

- **Approval ledger** (`orchestration/.../approvals.py`): actor, gate,
  revision id, target content hash, timestamp — append-only and idempotent.
- **Cancellation audit** (`cancellation.py`): actor, reason, provider-cancel
  evidence.
- **Artifact invalidation audit** (`storage/.../invalidation.py`): change
  type, artifact, previous status → STALE/SUPERSEDED, actor, clock.
- **Permission audit** (`SecurityAuditContext`): decision id shared between
  the permission event and the audit record.
- **Outbox journal**: every published event with dedup key and event id
  (replay idempotent).

## 2. What is never logged

- raw secrets, cookies, tokens or payment details;
- browser profile paths or `AppData`/`C:\Users` absolute paths;
- provider credentials embedded in URLs;
- screenshot account/payment areas are redacted or not captured
  (`BrowserActionPolicy` SCREENSHOT is bounded to controlled workspace paths;
  SE01 proves screenshot-metadata canaries are redacted).

## 3. Redaction (canary-tested)

- `redact_text` / `redact_dict` (core) mask key patterns and sensitive-key
  values; `redact_shell_output` composes the core redactor (SE01 evidence;
  SEC-001 closed by this fix).
- Every receipt/evidence file is validated by `evidence_lib`:
  - `evidence_locator` must not contain token/secret markers or local
    profile paths;
  - `input_hashes`/`output_hashes` must be real SHA-256 values (no
    placeholders);
  - media files must carry real container magic (no mock byte-strings).

## 4. Evidence portability and tamper evidence

- `evidence_manifest.json` is **content-addressed**: every file's SHA-256,
  size, container and locator are recorded and the manifest carries its own
  self-hash. A modified receipt, injected file, or rewritten manifest is
  detected by `validate_evidence_manifest`.
- Evidence locators are relative (`phase_26/<sha>/…`) — portable, no local
  absolute paths.
- Verifiers are **read-only by default** and snapshot the evidence directory
  before/after to prove no mutation (a verifier that writes is a failed
  gate).
- The phase verdict is **derived by the verifier** — never hard-coded by the
  producer — and bound to the candidate SHA (wrong SHA ⇒ `BLOCKED`).

## 5. Cross-project audit isolation

- Every event envelope carries `project_id`; consumers scope by project
  (SE11 proves a project-A event is refused on a project-B channel).
- Media delivery uses opaque tokens (`tok_*`), never storage paths (SE11
  proves traversal/`../`/non-token values are denied 403).
