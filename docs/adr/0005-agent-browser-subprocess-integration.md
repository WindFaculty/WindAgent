# ADR 0005: agent-browser CLI Subprocess Integration

## Status
Accepted

## Context
WindAgent needs real browser automation for social media research (Facebook, YouTube, TikTok). The `vercel-labs/agent-browser` project provides a CLI executable (`agent-browser`) that drives Chrome via CDP and exposes JSON stdin/stdout protocol. Integration options considered:

1. **Embed Node.js SDK directly** — requires Node runtime in Python process, adds Node dependency, complex error boundary across language boundary.
2. **MCP server** — `agent-browser` ships an MCP server. Requires running persistent server, adds network hop, operational complexity.
3. **CLI subprocess (argv, no shell)** — spawn `agent-browser` binary via argv array, communicate via JSON over stdin/stdout. No shell interpolation, clear process boundary, timeout via `asyncio.wait_for`, kill on timeout, portable across Windows/Linux/container.

## Decision
Use **CLI subprocess (argv, no shell)** as the transport layer. Adapter lives in `tools/windagent_tools/browser/agent_browser.py` behind `AgentBrowserProcessPort` interface for unit testing without Chrome.

Key design points:
- `SubprocessAgentBrowserProcess` implements `AgentBrowserProcessPort`
- `asyncio.create_subprocess_exec` with explicit argv array (no shell)
- `asyncio.wait_for` enforces per-command timeout
- Process killed on timeout via `process.kill()` + `await process.wait()`
- Error taxonomy: `BinaryNotFound`, `ProcessStartFailed`, `Timeout`, `NonZeroExit`, `PolicyViolation`
- CI pins `agent-browser@0.33.1` (SHA-256 verified in workflow)
- Canonical WindAgent tool names preserved: `open_url`, `click_xy`
- Workflow orchestration unchanged — only browser tool backend swapped

## Consequences
- **Pros**: Clean process isolation, no Node in Python process, testable via port, works in container/desktop/CI, no MCP server ops
- **Cons**: Process spawn overhead per command (~50-150ms), no persistent browser session across tool calls (session reuse via `--session` flag mitigates)
- **Risk mitigation**: Session reuse, connection pooling planned for Phase 2; benchmark CLI vs daemon vs MCP in Phase 1 gate

## Compatibility Matrix (Planned)
| Platform | Status |
|----------|--------|
| Linux (headless) | ✅ CI verified |
| Windows 11 | 🔲 Planned |
| Docker/container | ✅ CI verified |
| Packaged desktop | 🔲 Planned |

## Upgrade Policy
- Pin exact version + SHA in CI workflow
- Upgrade only after: changelog review, CI re-run, smoke test on all platforms
- Breaking-change matrix tracked in ADR appendix

## License & Dependency Review
- `agent-browser` MIT license — compatible with WindAgent MIT
- SBOM scan: no critical CVEs at 0.33.1
- Dependencies: `chrome-launcher`, `chrome-remote-interface`, `yargs` — all permissive

## References
- PR #10 diff: 15 files, 2230+/42-
- CI workflow: `.github/workflows/agent-browser-social-e2e.yml`
- Adapter: `tools/windagent_tools/browser/agent_browser.py`
- Tools: `tools/windagent_tools/browser/tool.py`