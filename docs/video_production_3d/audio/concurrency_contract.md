# Concurrent Audio — Concurrency Contract

Stage E, Phase 10, backlog 1 & 8. Authority: `docs/video_production/3d_animation_plans/stage_e_concurrent_audio.md`.

> Fan-in chỉ xảy ra trước final animation timing/lip-sync. Asset, environment
> và animation library lookup không phải đợi TTS.

## Luồng orchestration

```
ScreenplayLocked
├── ProduceAudio
│   ├── PrepareDialogue
│   ├── CastVoice / ResolveVoiceProfile
│   ├── SynthesizeTTS
│   ├── ForcedAlign
│   └── PublishDialogueTrack
└── Prepare3DProduction
```

`ProduceAudio` chạy song song với `Prepare3DProduction`. Không có dependency
ngang trước lip-sync. Mỗi line là một node audio DAG độc lập; line khác nhau
tổng hợp song song theo `ConcurrencyPolicy`.

## Provider / capability (backlog 1)

`TtsProviderPort` (contracts) + `TtsProviderCapability` (domain). Provider
quảng cáo:

- `supported_locales` — ngôn ngữ hỗ trợ;
- `modes` — `LOCAL` / `API`;
- `sample_rates`, `channels`;
- `features` — `WORD_TIMESTAMPS`, `TOKEN_TIMESTAMPS`, `PHONEME_TIMING`,
  `EMOTION`, `MULTI_SAMPLE_RATE`;
- `emotion_labels`.

Không bao giờ giả định một capability provider không quảng cáo. Đặc biệt:
provider không có `PHONEME_TIMING` → forced aligner là một adapter riêng, KHÔNG
bịa confidence.

## Per-provider chính sách (backlog 8)

`ConcurrencyPolicy`:

- `max_concurrency` — số line tổng hợp đồng thời cho provider đó;
- `retry_budget` — số lần retry trước khi fail node;
- `timeout_seconds` — budget thời gian một synthesis call;
- `cancellation_grace_seconds` — thời gian chờ cho cancellation.

Node bị `CANCELLED` không bao giờ publish partial file.

## Nhánh 3D được bảo vệ

Nhánh audio fail → DAG state của branch 3D không bị mất. `AudioConcurrencyState`
version theo `revision_hash`; node audio được ghi riêng biệt, restart worker
chỉ nối tiếp line còn thiếu.
