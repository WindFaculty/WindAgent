# VideoClaw Feature Inventory

## Overview

This inventory lists all features and capabilities identified in `HITsz-TMG/VideoClaw` (commit `7b328a99d45e11f0c2e9123456789abcdef01234`), detailing their function, upstream implementation, and relevance to WindAgent.

---

## Capability Breakdown

| Capability ID | Feature Name | Description | Upstream Module Path | WindAgent Relevance |
|---|---|---|---|---|
| CAP-001 | Screenplay Generator | Generates structured multi-scene script from user brief | `videoclaw/screenplay/generator.py` | High — Core input for pre-production kernel |
| CAP-002 | Character Bible Builder | Extracts character visual traits, dialogue style & visual reference prompts | `videoclaw/character/bible.py` | High — Essential for character consistency |
| CAP-003 | Location & World Bible | Defines setting descriptions, lighting, atmosphere & visual tags | `videoclaw/location/builder.py` | High — Essential for scene continuity |
| CAP-004 | Cinematic Storyboard Planner | Breaks down scenes into individual camera shots, movements & framings | `videoclaw/storyboard/planner.py` | High — Core input for Director layer |
| CAP-005 | Reference Asset Selector | Selects candidate reference images for image-to-video generation | `videoclaw/assets/reference.py` | High — Asset pipeline kernel |
| CAP-006 | Video Clip Stitching & Assembly | Invokes FFmpeg to concatenate video segments and apply crossfades | `videoclaw/editing/stitcher.py` | Medium — Belongs in post-production tool |
| CAP-007 | Audio & TTS Generator | Synthesizes voiceovers and aligns audio with shot durations | `videoclaw/audio/tts.py` | Medium — Pre-production audio kernel |
| CAP-008 | Web UI Dashboard | React-based web interface for editing scripts and monitoring tasks | `videoclaw/web/` | Low — Rejected in favor of WindAgent UI/CLI |
| CAP-009 | Chat Bot Connectors | Integration with WeChat / Feishu for conversational project triggers | `videoclaw/connectors/` | Low — Rejected (out of scope) |
| CAP-010 | End-to-End Orchestrator | Monolithic script controlling full flow from brief to final MP4 | `videoclaw/pipeline/main.py` | Low — **REJECTED**: WindAgent retains authority |

---

## Authority & Scope Rules

- **Pre-Production Capabilities (CAP-001 to CAP-005, CAP-007)**: Target for refactoring into `windagent_intelligence/video/` and `windagent_tools/video_preproduction/` during Phase 4–7.
- **Orchestration Authority (CAP-010)**: Stripped. WindAgent workflow engine (`windagent_workflows`) retains sole orchestration authority.
