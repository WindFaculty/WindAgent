# Approval & Review UX Specification

## 1. Candidate Comparison & Override Panel

1. **Multi-Candidate Review**: All generated candidates for a shot are presented side-by-side.
2. **Dimension Scores & Defects**: Each candidate displays per-dimension evaluation scores (motion smoothness, prompt fidelity, aesthetic quality, lighting consistency), blocking defect tags, and confidence scores.
3. **Override Action**: If the user overrides an automated rating, the UI MUST require an explicit reason string before enabling the `Override & Approve` button. Aggregate scores alone must not conceal underlying defect details.

## 2. Cost Approval & Observability Widgets

1. **Credit Metrics Display**: The UI prominently displays:
   - Estimated credits for planned pipeline run.
   - Reserved credits currently locked.
   - Observed debits billed.
   - Remaining credit balance.
2. **Over-budget Safety Gate**: If an action exceeds the approved budget ceiling, mutating action buttons (e.g. `Approve & Generate`) are automatically disabled with an explanation modal.

## 3. Stale Approval Guard

1. **Revision Binding**: Approval widgets bind strictly to `target_revision_id` and artifact hashes.
2. **Automatic Invalidation**: If a background event or upstream edit updates the underlying revision (e.g. screenplay change), any open approval prompt is instantly disabled and marked `STALE_REVISION`.

## 4. Human Takeover & Resume Panel

1. **Takeover Triggers**: When a browser automation session encounters a CAPTCHA, login challenge, or account flag, the UI displays a `Human Action Required` panel.
2. **Takeover Instructions**: Step-by-step guidance instructs the user on completing the challenge.
3. **Resume Button**: Once the user completes the action, clicking `Clear & Resume` triggers a safe reconciliation request without submitting duplicate jobs.
