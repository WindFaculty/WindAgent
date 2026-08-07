# Account Safety Policy Contract — Phase 16

## 1. Overview

Account safety policies protect user credentials, prevent quota abuse, enforce strict evidence redaction, and limit automated activity to safe operational parameters.

## 2. Zero Bypass Rule

- Automated CAPTCHA solving, OCR Extraction of challenges, proxy/account rotation, fingerprint spoofing, and automatic payment or terms acceptance are strictly prohibited.
- Attempting any automated action matching these patterns immediately raises `FlowHumanBypassAttemptedError`.

## 3. Evidence Redaction

- Screenshots, log snippets, and UI observation markers are sanitized prior to persistence or display.
- Sensitive strings (tokens, cookies, auth headers, email addresses, credit card patterns) are replaced with `[REDACTED]` or `[REDACTED_SECRET]`.

## 4. Session Circuit Breaker

- A session tracking intervention counts will trip its circuit breaker if interventions exceed `max_interventions_per_session` (default: 3).
- Tripped sessions raise `FlowCircuitBreakerTrippedError` and require manual review.

## 5. Enforced Automation Limits

- `begin_automated_action(session_id, operation_token)` first checks that the
  session is not paused for human takeover, then reserves a bounded account
  slot.
- A different operation token is rejected with
  `FlowConcurrencyLimitExceededError` when `max_concurrency` is reached
  (default: 1). Nested navigator calls reuse their parent token rather than
  consuming a second slot.
- A session exceeding `rate_limit_per_minute` (default: 10) raises
  `FlowRateLimitExceededError`; releasing the concurrency slot does not reset
  that minute's budget.
