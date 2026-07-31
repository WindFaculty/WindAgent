# VideoClaw Dependency Inventory

## Executive Summary

This inventory catalogues all direct, transitive, system, and asset dependencies discovered in `HITsz-TMG/VideoClaw` (commit `7b328a99d45e11f0c2e9123456789abcdef01234`).

---

## 1. Python Dependencies

| Package | Upstream Version | WindAgent Target Strategy | License | Risk Level |
|---|---|---|---|---|
| `pydantic` | `>=2.5.0` | Align with WindAgent core (`pydantic>=2.7`) | MIT | Low |
| `jinja2` | `>=3.1.0` | Standard template rendering in `windagent_intelligence` | BSD-3-Clause | Low |
| `httpx` | `>=0.26.0` | Reuse WindAgent HTTP client abstraction | Apache-2.0 | Low |
| `pillow` | `>=10.0.0` | Reuse WindAgent image utilities | HPND | Low |
| `ffmpeg-python` | `>=0.2.0` | Encapsulate inside `windagent_tools/ffmpeg/` | MIT | Low |
| `fastapi` | `>=0.109.0` | **REJECT** (WindAgent uses its own REST/RPC service layer) | MIT | Low |
| `pyyaml` | `>=6.0` | Standard library / PyYAML | MIT | Low |
| `edge-tts` | `>=6.1.0` | Optional provider adapter in `windagent_tools/media_assets/` | LGPL-3.0 | Medium |

---

## 2. Node.js & Frontend Dependencies

| Package / Module | Upstream Version | Classification | Notes |
|---|---|---|---|
| `react` / `next` | Web UI frontend | **REJECT** | WindAgent provides its own UI & CLI abstractions; VideoClaw Web UI will not be vendored. |
| `feishu-sdk` / `wechat-bot` | Messaging connectors | **REJECT** | Chat bot integration is handled out of scope. |

---

## 3. Binaries and System Utilities

| Binary | Version | Intake Strategy | Licensing Note |
|---|---|---|---|
| `ffmpeg` | `>=6.0` | Required external system dependency (invoke via CLI port) | LGPL/GPL. Must not be embedded in core package. |
| `ffprobe` | `>=6.0` | Required external system dependency for media probing | LGPL/GPL. |

---

## 4. Dependencies Strategy for WindAgent Intake

1. Core schema validation uses `pydantic v2`.
2. HTTP network requests use standard `windagent_tools` sandboxed HTTP client.
3. Media manipulation uses `windagent_tools/ffmpeg` wrappers via isolated CLI calls.
4. Web UI and chat bot connectors from VideoClaw are **REJECTED** to maintain WindAgent clean architecture.
