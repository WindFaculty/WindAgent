# Agent Browser Social Research Integration

## Scope

This integration replaces WindAgent's simulated `open_url` implementation with
`vercel-labs/agent-browser` and adds a browser-to-report pipeline for public or
user-authorized Facebook, YouTube, and TikTok pages.

Model roles are deliberately separated:

- **Local extraction:** an Ollama-hosted Qwen 3.5 model converts rendered page
  text into normalized JSON records.
- **Independent synthesis:** a Google API Gemma 4 31B model analyzes the
  normalized records.
- **Verification synthesis:** a Google API Gemini 3.5 Flash Lite model produces
  a second synthesis with explicit uncertainty and source coverage.

Model names are runtime IDs, not assumptions. The command performs provider
model discovery before collection and fails closed when an ID is unavailable.
Use the command-line overrides when the provider publishes a different exact ID.

## Security model

- Commands are executed with `asyncio.create_subprocess_exec`; no shell is used.
- Navigation accepts only HTTP(S), rejects embedded credentials, and enforces a
  host allowlist before launching Chrome.
- Public, unauthenticated collection uses agent-browser native `--allowed-domains`
  containment.
- agent-browser currently rejects native domain containment when a Chrome
  profile, saved state, or restore session is used. Authorized Facebook/TikTok
  runs therefore use WindAgent preflight containment with `--authenticated`.
- Page content is wrapped and treated as untrusted evidence in every model
  prompt. Instructions found inside a page are not executed.
- Browser state files contain login tokens. They must remain outside Git and are
  ignored by the repository configuration.
- The integration does not bypass CAPTCHA, anti-bot controls, access controls,
  private groups, private messages, or platform rate limits.

## Installation

Pin the tested browser adapter version:

```powershell
npm install -g agent-browser@0.33.1
agent-browser install
agent-browser doctor
```

Install and verify the local model using the actual Ollama tag available in your
environment:

```powershell
ollama list
# Pull the exact Qwen 3.5 tag published for your Ollama registry, then pass it
# with --local-model when it differs from qwen3.5.
```

Set credentials only in the current PowerShell process:

```powershell
$env:GOOGLE_API_KEY = "<google-api-key>"
$env:OLLAMA_BASE_URL = "http://localhost:11434"
```

The Google key must be able to list and invoke both requested Google model IDs.
The CLI reports the discovered model list when preflight fails.

## Public YouTube smoke run

```powershell
windagent-social-report `
  --query "Summarize the main claims and engagement signals" `
  --url "https://www.youtube.com/watch?v=<video-id>" `
  --local-model "qwen3.5" `
  --gemma-model "<exact-google-gemma-model-id>" `
  --gemini-model "<exact-google-gemini-model-id>" `
  --json
```

## Authorized Facebook or TikTok run

Use a dedicated Chrome profile or a saved agent-browser state. Do not commit the
profile or state file.

```powershell
windagent-social-report `
  --query "Compare recurring user concerns across the supplied posts" `
  --url "https://www.facebook.com/<public-or-authorized-page>" `
  --url "https://www.tiktok.com/@<account>/video/<id>" `
  --browser-profile "Default" `
  --authenticated `
  --local-model "qwen3.5" `
  --gemma-model "<exact-google-gemma-model-id>" `
  --gemini-model "<exact-google-gemini-model-id>"
```

On Windows, close Chrome before profile reuse if profile files are locked.
Prefer a dedicated automation profile rather than a primary personal profile.

## Output contract

Each run writes a unique directory under `artifacts/social_research/`:

```text
<report-id>/
├── report.md
├── report.json
└── screenshots/
```

`report.json` includes model routes, source URLs, final URLs, capture SHA-256
hashes, extraction records, source errors, and both independent synthesis
outputs. A run is `COMPLETE` only when every source is normalized; otherwise it
is `PARTIAL_SOURCE_COVERAGE`. Report generation stops when no source can be
normalized or either required Google synthesis is empty.

## Deterministic E2E validation

The GitHub Actions workflow `Agent Browser Social E2E` installs the pinned Rust
CLI and Chrome, serves a local fixture page, invokes the real browser process,
normalizes the captured text through deterministic model doubles, and verifies
that Markdown and JSON reports are written.

Local equivalent:

```powershell
$env:RUN_AGENT_BROWSER_E2E = "1"
uv run pytest -q `
  tests/unit/tools/test_agent_browser_tool.py `
  tests/unit/workflows/test_social_research.py `
  tests/integration/test_agent_browser_social_e2e.py
```

A real-platform acceptance run remains environment-specific because Facebook
and TikTok authentication, consent dialogs, regional layouts, and rate limits
cannot be represented safely in public CI.
