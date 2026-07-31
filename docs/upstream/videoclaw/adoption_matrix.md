# VideoClaw Adoption Matrix

## Adoption Classification Policy

Each capability or file group from `HITsz-TMG/VideoClaw` is assigned a classification:
- **`ADOPT_AND_REFACTOR`**: Source/logic is adapted and refactored into WindAgent standards. MIT copyright notice retained.
- **`REWRITE_FOR_WINDAGENT`**: Clean-room implementation of contract/functionality without direct code copying.
- **`REFERENCE_ONLY`**: Retained in research docs as behavioral reference; no code in runtime.
- **`REJECT`**: Excluded entirely from runtime, imports, and distribution.
- **`UNKNOWN`**: Unclassified (MUST BE ZERO to pass Gate VP1).

---

## Master Adoption Matrix

| Item ID | Upstream Path | Capability | Classification | Target WindAgent Module | License Obligation | Approver |
|---|---|---|---|---|---|---|
| ADOPT-001 | `videoclaw/screenplay/` | Screenplay Gen | `REWRITE_FOR_WINDAGENT` | `windagent_intelligence/video/screenplay/` | MIT Notice | Lead Architect |
| ADOPT-002 | `videoclaw/character/` | Character Bible | `REWRITE_FOR_WINDAGENT` | `windagent_intelligence/video/ideation/` | MIT Notice | Lead Architect |
| ADOPT-003 | `videoclaw/location/` | Location Bible | `REWRITE_FOR_WINDAGENT` | `windagent_intelligence/video/ideation/` | MIT Notice | Lead Architect |
| ADOPT-004 | `videoclaw/storyboard/` | Storyboard Planner | `REWRITE_FOR_WINDAGENT` | `windagent_intelligence/video/shot_planner/` | MIT Notice | Lead Architect |
| ADOPT-005 | `videoclaw/assets/` | Reference Asset Selector | `ADOPT_AND_REFACTOR` | `windagent_tools/video_preproduction/` | Retain MIT header in source | Lead Architect |
| ADOPT-006 | `videoclaw/editing/` | Video Stitcher (FFmpeg) | `REWRITE_FOR_WINDAGENT` | `windagent_tools/ffmpeg/` | MIT Notice | Lead Architect |
| ADOPT-007 | `videoclaw/audio/` | Voiceover / TTS | `REWRITE_FOR_WINDAGENT` | `windagent_tools/media_assets/` | MIT Notice | Lead Architect |
| ADOPT-008 | `videoclaw/web/` | Web UI | `REJECT` | N/A | None | Product Owner |
| ADOPT-009 | `videoclaw/connectors/` | Feishu/WeChat Bots | `REJECT` | N/A | None | Product Owner |
| ADOPT-010 | `videoclaw/pipeline/` | Monolithic Pipeline | `REJECT` | N/A (Replaced by `windagent_workflows`) | None | Lead Architect |

---

## Compliance Verification Summary

- **Total Items Evaluated**: 10
- **Items classified ADOPT_AND_REFACTOR**: 1
- **Items classified REWRITE_FOR_WINDAGENT**: 6
- **Items classified REFERENCE_ONLY**: 0
- **Items classified REJECT**: 3
- **Items classified UNKNOWN**: 0

> [!SUCCESS]
> Zero items have `UNKNOWN` classification. All MIT notices and obligations are assigned to appropriate target WindAgent modules.
