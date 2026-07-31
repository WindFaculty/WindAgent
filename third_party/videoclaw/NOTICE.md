# NOTICE — VideoClaw upstream snapshot (quarantined)

## Source

- Repository: https://github.com/HITsz-TMG/VideoClaw
- Pinned commit: `5a16ae23a4f1cb6886c44c0205f7b7e52a34c276` (main, 2026-07-17)
- License: MIT (see `LICENSE` in this directory)
- Copyright: Copyright (c) 2026 Video-Claw

## Status

This directory contains an **immutable, quarantined snapshot** of the upstream
VideoClaw source for audit and characterization only. It is **NOT** a runtime
dependency of WindAgent and must never be imported from canonical packages.

## Usage scope

- `upstream/` — the verbatim upstream snapshot (no formatting, no line-ending
  normalization, no source edits during intake).
- `PATCHES.md` — log of any patches applied to the snapshot. Every patch must
  record a reason, a hash, and an issue link. No patches exist yet.
- `UPSTREAM_MANIFEST.json` — machine-readable pin, archive/content hashes, file
  count, and quarantine policy.

## Excluded from WindAgent runtime

Per the adoption matrix (`docs/upstream/videoclaw/adoption_matrix.md`), the
following upstream capabilities are REJECTED and excluded from the WindAgent
kernel:

- Upstream video generation and final editing (`REJECT`).
- Upstream project/session/task authority and local JSON task DB.
- Upstream WebUI, provider config, and composition root (`REJECT`).
- Upstream storyboard/orchestration authority.
- Feishu/WeChat bot connectors (`REJECT`).
- Any direct runtime import from `third_party`.

## License obligations

Capabilities adapted from this snapshot (`ADOPT_AND_REFACTOR` /
`REWRITE_FOR_WINDAGENT`) MUST retain the MIT copyright notice and record the
obligation in the target WindAgent module. Nothing in this directory grants an
implied license to WindAgent's own materials.
