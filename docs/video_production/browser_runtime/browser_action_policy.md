# Browser Action Policy (Phase 12)

**Plan:** 04 §8.4 · **Contract owner:** `tools/windagent_tools/browser/action_policy.py`

## 1. Principle

The browser worker only ever performs **typed** bounded operations. Raw
browser instructions — arbitrary `eval`, cookie export, unapproved upload,
payment/terms confirmation, arbitrary filesystem reads, model-invented
commands — are rejected *before* any process or browser call is made. The
policy is deterministic and fully offline.

## 2. Allowlist

| Operation | `BrowserOperation` | Notes |
|---|---|---|
| Open URL | `OPEN_URL` | only `http(s)`; must be inside domain allowlist; no credentials in URL |
| Accessibility snapshot | `SNAPSHOT` | returns `@ref` targets |
| Semantic click | `CLICK` | non-empty target |
| Semantic fill | `FILL` | non-empty target |
| Semantic select | `SELECT` | non-empty target |
| Upload | `UPLOAD` | file must be inside the approved asset store |
| Screenshot | `SCREENSHOT` | written to a controlled workspace path |
| Bounded wait | `WAIT` | non-empty target |
| Download | `DOWNLOAD` | path resolved inside the workspace root |

## 3. Deny / require confirmation

| Request | Decision code | Behavior |
|---|---|---|
| Arbitrary `eval` | `deny_operation` | denied, evidence `BLOCKED` |
| Cookie export | `deny_operation` | denied, evidence `BLOCKED` |
| Arbitrary filesystem read | `deny_filesystem` | denied, evidence `BLOCKED` |
| Navigation outside allowlist | `deny_domain` | denied before browser call |
| URL with embedded credentials | `deny_credentials` | denied before browser call |
| Upload outside approved store | `deny_upload_path` | denied before browser call |
| Payment / terms / destructive target | `require_confirmation` | **never auto-confirmed**; requires human |
| Unknown operation | `deny_operation` | fail closed |

## 4. Fail-closed rules

- An **empty domain allowlist** denies every `OPEN_URL` (nothing is allowed
  until explicitly configured with allowed domains).
- An **empty approved asset store** denies every `UPLOAD`.
- An **unknown operation** is denied (`default_deny=True`).
- The runtime has **no execution branch** for deny-class operations: even a
  buggy caller cannot make the runtime run `eval` or export cookies.

## 5. Confirmation gate

Payment/terms-style targets (regex over `pay|payment|checkout|purchase|
billing|subscribe|terms of service|accept terms|delete account|…`) return
`REQUIRE_CONFIRMATION` with `requires_confirmation=True`. Human takeover is
Phase 16; until then the runtime raises `BrowserActionDeniedError` and records
`BLOCKED` evidence.
