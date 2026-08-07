# Browser Profile and Secret Policy (Phase 26 §14.1)

Gate: `VP26_SECURITY_VERIFIED` — scenario **SE02** (profile encryption at
rest) and **SE01** (secret redaction) provide the evidence.

## 1. Encryption at rest

- Browser state directories (profile, cookies, `Login Data`, tokens) are
  encrypted with **AES-GCM** into an `enc:v1:<nonce>:<ciphertext>` blob by
  `tools/windagent_tools/browser/state_encryption.py`.
- SE02 proves:
  - no plaintext cookie/token/canary marker exists in the encrypted file;
  - decrypt → round-trip integrity (per-file SHA-256 equality);
  - **wrong key is rejected** (AES-GCM authentication failure);
  - the isolated profile copy never mutates the source and is removed after
    use (`cleanup_isolated_profile`).

## 2. Key management

- Key source (in order): explicit key → `WINDAGENT_ENCRYPTION_KEY` /
  `WINDA_AGENT_ENCRYPTION_KEY` env var (base64 16/24/32-byte).
- Production fails closed when no key is configured (the in-process fallback
  is only allowed under `PYTEST_CURRENT_TEST` / `WINDAGENT_ALLOW_TEST_KEY`).
- The key is **never written into logs, events, support bundles or evidence**
  (see redaction below); rotate by re-encrypting states with the new key.

## 3. Profile isolation

- Every automated run uses `BrowserStateManager.create_isolated_profile_copy`
  — a temporary copy under a `windagent_profile_` temp dir — so the user's
  real profile is never polluted by automation (SE02 asserts source
  unchanged).
- Decrypted state lives only for the session duration and is removed on
  cleanup (SE02/SE13).
- Cookie/token/profile paths never enter event payloads, screenshot
  metadata or evidence locators; `evidence_lib` rejects locators containing
  `AppData`, `C:\Users`, `\profile\`, `token=`, etc.

## 4. Redaction (canary-tested)

`core/windagent_core/security/redaction.py` (`redact_text`, `redact_dict`)
and `tools/windagent_tools/shell/runner.py` (`redact_shell_output`) mask:

- `sk-*`, `nvapi-*`, `gsk_*`, `AIzaSy*` provider keys;
- `Bearer <token>`, `api_key=`, `token=`, `authorization:`, `password=`;
- nested dict values under sensitive keys (`secret`, `password`, `cred`,
  `auth_token`, `access_token`, `private_key`, …).

SE01 injects **canary values** through logs, error traces, events, shell
output and screenshot metadata and asserts **zero** survive. Note: the
shell-output gap for unquoted `password=`/API-key prefixes found by SE01 was
**fixed in this phase** (SEC-001 closed; `redact_shell_output` now composes
the core redactor).

## 5. Session deletion / rotation

- Retention: `BrowserStateRetentionPolicy` (age, count, total size) — SE13
  proves age- and count-based cleanup.
- Deletion follows the privacy lifecycle in `privacy_retention_deletion.md`:
  authorization → mark → remove references → delete unreferenced data →
  content-free receipt.
- Rotation: on secret rotation, old encrypted states are re-encrypted under
  the new key and expired states purged by the retention policy.
