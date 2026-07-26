# Risk Register — Phase 12

## Risks and Mitigations

1. **Credential Exposure Risk**: Diagnostic messages or error tracebacks could expose database passwords or API keys.
   - *Mitigation*: Implemented regex-based secret masking (`_attach_suggested_action_and_mask_secrets`) across `HealthCheckResult` messages, details, and remediation actions.

2. **Exit Code Misinterpretation**: Automation scripts relying on non-zero exit codes could break if CLI doctor exit codes are ambiguous.
   - *Mitigation*: Standardized exit codes strictly (`0` = UP, `1` = DEGRADED, `2` = DOWN, `3` = Invalid CLI args/config invocation).
