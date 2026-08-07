# Human States Contract — Phase 16

## 1. Overview

Phase 16 models browser challenges (login, CAPTCHA, 2-step verification, terms acceptance, payment/credit billing) as durable, observable, and resumable human states rather than attempting automated bypasses or entering infinite retry loops.

## 2. Typed Human States

The system defines 5 typed human states:

1. `HUMAN_LOGIN_REQUIRED`: Session requires user authentication.
2. `HUMAN_CAPTCHA_REQUIRED`: Browser presents a bot challenge (reCAPTCHA, hCaptcha, Turnstile).
3. `HUMAN_ACCOUNT_VERIFICATION_REQUIRED`: Security verification or 2FA challenge is requested.
4. `HUMAN_TERMS_ACCEPTANCE_REQUIRED`: Terms of service or privacy policy update requires explicit user acceptance.
5. `HUMAN_PAYMENT_CONFIRMATION_REQUIRED`: Credit purchase, billing, or subscription changes require manual confirmation.

## 3. Human Action Record Schema

Each human intervention trigger produces a durable record:

```json
{
  "human_action_id": "ha_a1b2c3d4e5f6",
  "session_id": "sess_16",
  "project_id": "vp_1",
  "generation_id": "gen_123",
  "human_state": "HUMAN_CAPTCHA_REQUIRED",
  "reason": "CAPTCHA challenge detected on navigation to Flow workspace.",
  "detected_at": "2026-08-02T01:00:00.000000+00:00",
  "safe_resume_state": "PROJECT_OPEN",
  "redacted_evidence": {
    "url": "https://accounts.google.com/v3/signin",
    "markers": ["[REDACTED]"]
  },
  "status": "PENDING",
  "resolved_by": null,
  "resolved_at": null
}
```

Records are atomically persisted as `flow_human_actions.json` in the same
state directory as the Flow job registry. On process restart, every `PENDING`
record rebuilds its session pause before any browser action can be reserved.

## 4. Takeover & Interruption Policy

- When a human challenge is detected, session scheduler actions are immediately paused (`FlowHumanActionBlockedError` raised on any automated attempt).
- Headed browser sessions and profile locks remain intact.
- Clear instructions are presented to the operator without revealing session tokens, passwords, or credentials.
- `FlowNavigator` records challenges before navigation and after a navigation
  step. Image and video generators record them while polling and immediately
  before every candidate download; they mark the attached job
  `HUMAN_ACTION_REQUIRED` and do not issue another browser/fetch action.
