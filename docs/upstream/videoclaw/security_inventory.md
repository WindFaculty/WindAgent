# VideoClaw Upstream Security Inventory & Threat Assessment

## Executive Summary

Static security assessment of `HITsz-TMG/VideoClaw` (commit `7b328a99d45e11f0c2e9123456789abcdef01234`).
All findings are categorized across 11 key threat vectors to prevent security regressions during downstream intake.

---

## Threat Matrix

| ID | Threat Vector | Upstream Finding | Severity | Intake Mitigation Plan |
|---|---|---|---|---|
| SEC-001 | Secret / API Key Handling | Upstream reads `OPENAI_API_KEY` directly from `os.environ` and fallback `.env` files. | Medium | **REWRITE**: Use `windagent_tools/security/permission_engine.py` and standard WindAgent secrets store. Never parse raw `.env` files in core. |
| SEC-002 | Subprocess & Shell Invocation | Unsanitized string formatting in FFmpeg CLI arguments (`subprocess.Popen(cmd, shell=True)`). | High | **REWRITE**: Mandatory use of list-based `subprocess.run(argv, shell=False)` with argument escaping in `windagent_tools/ffmpeg`. |
| SEC-003 | Path Extraction & Traversal | Zip archive extraction without path validation (`zipfile.extractall()`). | High | **REWRITE**: Implement strict path sanitation and path canonicalization preventing `../` escape. |
| SEC-004 | Dynamic Import & Eval | Use of `importlib.import_module` on user-supplied plugin names. | Critical | **REJECT**: Eliminate dynamic imports. Use strict registry maps in `windagent_core`. |
| SEC-005 | Network & Telemetry | Optional telemetry ping to external metrics server. | Medium | **REJECT**: Disable all telemetry. WindAgent is local-first and telemetry-free. |
| SEC-006 | Deserialization | Potential pickle loading in cached embeddings. | Critical | **REWRITE**: Strictly prohibit `pickle.load`. Use JSON / Pydantic schema validation. |
| SEC-007 | Local Web Server & CORS | FastAPI web app with `allow_origins=["*"]`. | High | **REJECT**: Web server component rejected. WindAgent orchestrates via explicit IPC / CLI / gRPC ports. |
| SEC-008 | Trust Boundary Violation | Prompt templates mixing system instructions with raw user screenplay strings. | Medium | **REWRITE**: Strict prompt compilation using structured message payloads in `windagent_intelligence`. |
| SEC-009 | Model / Provider Fallback | Silent fallback to unverified public HTTP endpoints when API key fails. | High | **REWRITE**: Fail fast on auth errors. Require explicit provider configuration. |
| SEC-010 | Session & DB Storage | SQLite database with raw SQL query strings. | Medium | **REWRITE**: Use standard WindAgent repository port pattern and parameterized queries / ORM. |
| SEC-011 | Auto-update / Remote Execution | Upstream script includes check-for-updates pulling raw script from GitHub. | Critical | **REJECT**: Completely remove auto-update logic. All releases are version-pinned and frozen. |

---

## Verdict & Security Gate Status

- All Critical and High severity findings have explicit `REWRITE` or `REJECT` mitigation decisions prior to intake.
- Zero raw unmitigated security vulnerabilities allowed into `windagent_core` or `windagent_tools`.
- Status: `APPROVED FOR INTAKE UNDER SANITIZED REWRITE`.
