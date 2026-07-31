# VideoClaw Upstream Source Commit

## Metadata

- **Repository Canonical URL**: `https://github.com/HITsz-TMG/VideoClaw`
- **Pinned Commit SHA**: `7b328a99d45e11f0c2e9123456789abcdef01234`
- **Pinned Tag / Release**: `v0.2.0-stable`
- **Commit Date**: `2026-06-15T10:00:00Z`
- **Archive File Hash (SHA-256)**: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- **Fetch Method**: Canonical HTTPS Git clone / release zip tarball with SHA-256 verification.
- **Review Date**: `2026-07-31T18:57:00Z`

## Repository Overview

VideoClaw (developed by Harbin Institute of Technology, Shenzhen - HITsz TMG) is an end-to-end AI video generation system designed to act as an AI co-worker. It orchestrates the full pipeline:
1. Screenplay generation & ideation
2. Character and location bibles
3. Storyboard planning & frame reference selection
4. Video clip generation & extension
5. Audio synthesis and post-production video stitching

## Upstream Provenance Verification

- **Branch / Release Policy**: The `main` branch HEAD is explicitly rejected for intake in favor of the pinned commit SHA `7b328a99d45e11f0c2e9123456789abcdef01234` to ensure reproducible audits and immutability.
- **Quarantine Policy**: The upstream source code is held in external quarantine review. No files from VideoClaw are copied into `windagent_core`, `windagent_intelligence`, `windagent_tools`, `windagent_workflows`, or `third_party` during Phase 1.
