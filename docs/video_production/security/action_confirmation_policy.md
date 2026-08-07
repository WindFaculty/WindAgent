# Action Confirmation Policy (Phase 26 §14.5)

Gate: `VP26_SECURITY_VERIFIED` — scenario **SE10** provides the evidence;
`api_authorization_report.json` also records the publish/delete approval path.

## 1. Human confirmation gates

Automation never confirms, pays, deletes or publishes on its own. The
following actions always require a human:

| Action | Browser policy gate | Permission-engine gate |
|---|---|---|
| Terms acceptance | `BrowserActionPolicy` marker → `REQUIRE_CONFIRMATION` | — |
| Payment / credit purchase / checkout / subscribe | marker → `REQUIRE_CONFIRMATION` | — |
| Account / security setting (destructive) | marker → `REQUIRE_CONFIRMATION` | — |
| Project / account delete (permanent) | marker → `REQUIRE_CONFIRMATION` | high/critical risk → `REQUIRE_APPROVAL` |
| External publish (`PUBLISH_DELIVERABLE`) | not a marker word — enforced at the permission layer | destructive high-risk → `REQUIRE_APPROVAL` |
| Destructive overwrite | marker → `REQUIRE_CONFIRMATION` | destructive → `REQUIRE_APPROVAL` |

The marker set in `BrowserActionPolicy` matches `pay|checkout|purchase|
billing|subscribe|terms of service|accept terms|agree and continue|delete
account|permanently delete|irreversible` (case-insensitive). SE10 drives each
of these targets through the real policy and asserts `REQUIRE_CONFIRMATION`
with `requires_confirmation=True`.

## 2. Permission engine

`PermissionEngine` (`tools/windagent_tools/security/permission_engine.py`):

- **hard-deny** rules (`bypass_auth`, `drop_production_db`, …) can never be
  overridden (SE10: `DENY` even with an operator role);
- **unknown / unhandled actions default to DENY**;
- **destructive** actions (high/critical risk, `is_destructive`) return
  `REQUIRE_APPROVAL` unless an explicit `user_approved` flag is present;
- approvals are recorded per decision id shared with the audit record.

SE10 proves: terms/payment/delete targets require confirmation, publish and
delete require approval, unknown actions deny, hard-deny rules deny, and an
explicitly approved destructive action is the only path to `ALLOW`.

## 3. Idempotency and optimistic concurrency (API layer)

The workspace command API (`v2_production_workspace.py`) adds belt-and-braces
for confirmation-bearing commands (SE11/SE12):

- `X-Idempotency-Key` replay returns the **same** `command_id` — a double
  click or retry cannot double-execute a confirmation;
- a command against a stale `revision_id` is rejected `409
  REJECTED_STALE` — a confirmation built on an outdated workspace cannot
  apply;
- approvals are bound to the exact revision hash and estimate hash, so a
  stale approval never re-opens a gate (SE12).

## 3b. CSRF disposition (plan §15 matrix)

The workspace command API authenticates with backend bearer tokens (no cookie
sessions), so classic CSRF is non-applicable; replay is additionally protected
by `X-Idempotency-Key` dedup and optimistic `revision_id` checks (SE11/SE12).
The disposition is recorded in `api_authorization_report.json` (`csrf_note`)
and the threat-model manifest.

## 4. Automation non-bypass

- CAPTCHA / fingerprint / rate / quota controls are never bypassed by
  automation (see `reliability/recovery_invariants.md` CH09 zero-bypass
  human CAPTCHA).
- The browser action policy is deterministic and offline — it cannot be
  talked into a confirmation by prompt text.
