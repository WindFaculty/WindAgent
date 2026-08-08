# Timing Resolution Policy

Stage E, Phase 10, backlog 6 & 9. Authority: `stage_e_concurrent_audio.md`.

## Overlong line — không tự cắt câu (backlog 6)

`LineTimingResolver.resolve()` — khi line dài hơn shot, emit `TimingResolutionIssue`
với typed proposal, theo thứ tự ưu tiên an toàn:

1. `EXTEND_SHOT` — kéo dài shot;
2. `SHORTEN_TEXT` — rút gọn text;
3. `CHANGE_PACING` — đổi nhịp đọc;
4. `HUMAN_REVIEW` — mặc định khi không có option cơ học nào an toàn.

KHÔNG bao giờ auto-cắt một câu. Line trong tolerance (≤ shot):
`OverlongLineError` (không phải proposal).

## Invalidation map (backlog 9)

`invalidate_audio_scope()`:

| Thay đổi | Scope invalidate |
|---|---|
| `dialogue` | `TRACK_AND_MIX` — track + alignment + facial + mix/final |
| `voice` (voice profile hash đổi) | `TRACK_AND_MIX` — track + alignment + facial + mix/final |
| `BGM` | `MIX_ONLY` — mix/final, KHÔNG đụng visual clips |
| `SFX` / `AMBIENCE` | `MIX_ONLY` |

Dialogue/voice thay đổi → máy track + alignment + facial + mix/final cũ bị
invalid, cần tái tạo. BGM thay đổi → chỉ mix/final mới bị invalid, clip hình
giữ nguyên.
