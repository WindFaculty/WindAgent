# Mix Policy (plan 06 §8.5) — Phase 21

Gate: `VP21_AUDIO_PIPELINE_VERIFIED`

## 1. Mục đích

`MixPlanner` (`intelligence/.../video/audio/mix.py`) tạo `AudioMixPlan` —
versioned mix policy (dialogue ducking, loudness target, peak ceiling) + SFX/BGM
cues có license/provenance + command/parameter manifest. Mix chỉ publish khi
**mọi cue qua license gate và loudness/peak qua technical checks**.

## 2. Domain (plan §7)

```text
SoundEffectCue   kind=SFX      shot_id + timeline position + fade intent
MusicCue         kind=BGM      license_state + provenance
AudioMixPlan     ducking/loudness/peak + mix_policy_version + command_manifest
```

## 3. Rules (plan §8.5)

- **License gate (fail closed)**: cue có `license_state == UNKNOWN | REJECTED`
  → issue `UNKNOWN_CUE_LICENSE`, cue **không publish**; mix vẫn tạo nhưng kèm
  issue blocking (bên gọi quyết định không dùng khi có blocking issue).
- **Versioned policy**: `dialogue_ducking_db`, `loudness_target_lufs`
  (default -16.0), `peak_ceiling_db` (default -1.0) và `mix_policy_version`
  ("1.0.0") nằm trong domain, không hard-code trong verifier/pipeline.
- **Invalidation scope** (`AudioMixPlan.invalidated_scope`): BGM/SFX/ambience
  đổi → `MIX_ONLY` (chỉ invalidate mix/final cut, **không invalidate clip**);
  dialogue đổi → `TRACK_AND_MIX` (track + mix + final cut). Invalidation nằm
  trong core để không phụ thuộc UI.
- **Mix output có manifest**: `command_manifest` chứa command/parameter để
  FFmpeg post-production (§13) render reproducibly.
- `mix_hash = sha256(project|revision|mix_payload|mix_policy_version)` —
  deterministic; revision thay đổi → hash mới.

## 4. Kiểm chứng (verifier)

- `loudness_receipt.json`: default targets đúng (-16.0 / -1.0 / version 1.0.0);
  cue license UNKNOWN → blocking issue; cue LICENSED → pass; BGM change →
  `MIX_ONLY`; dialogue change → `TRACK_AND_MIX`; mix_hash deterministic; manifest
  present.
