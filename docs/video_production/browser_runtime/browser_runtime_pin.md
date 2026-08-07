# Upstream Runtime Pin & Compatibility (Phase 12)

**Plan:** 04 §8.1 · **Contract owner:** `tools/windagent_tools/browser/agent_browser.py`

## 1. Principle

The browser runtime depends on `vercel-labs/agent-browser` (a headed
Chrome/Chromium driver) plus a persistent local Chrome profile. The upstream
runtime is **pinned** and verified; WindAgent never downloads a new executable
in production outside an approved update flow.

## 2. Pin policy

- Pin the `agent-browser` version and lock/checksum via the existing build
  mechanism (`pyproject.toml` / lockfile). The binary name and session flags
  are configured through `AgentBrowserConfig` (`AGENT_BROWSER_BIN`,
  `AGENT_BROWSER_SESSION`, …).
- Do **not** bundle or auto-install Chrome. Use the installed headed
  Chrome/Chromium; the profile is persistent and explicit
  (`authenticated=True` + `AGENT_BROWSER_PROFILE`).
- Verify license and update policy before bumping the pinned version.

## 3. Compatibility matrix

| Platform | Chrome/Chromium | `agent-browser` | Notes |
|---|---|---|---|
| Windows (win32) | installed headed Chrome | pinned version | `taskkill /T /F` process-tree cleanup on timeout/cancel |
| CI (linux) | headed Chromium (fixture/fake process in unit tests) | pinned version | tests never launch a real browser |
| macOS | installed Chrome | pinned version | POSIX kill path |

## 4. Driver contract

- `SubprocessAgentBrowserProcess.run(argv, timeout_seconds, env)` executes the
  CLI with **argv only** — no shell interpolation.
- Every command is bounded by `timeout_seconds`; on timeout or cancellation
  the process tree (CLI + Chrome daemon) is killed on Windows.
- `AgentBrowserConfig.process_env()` strips secret-marked environment
  variables (`API_KEY`, `AUTH_TOKEN`, `ACCESS_TOKEN`, `SECRET`, `PASSWORD`)
  before passing env to the child — no secrets travel through argv/env.

## 5. Update flow

Version bumps require:

1. license re-check;
2. compatibility matrix update;
3. full Phase 12 test suite (fake-process contract) green;
4. an explicit approved live smoke (if a browser is involved).

This document is the evidence artifact referenced by the Phase 12 verifier
(`browser_runtime_pin` check).
