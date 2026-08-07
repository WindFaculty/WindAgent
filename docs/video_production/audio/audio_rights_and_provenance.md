# Audio Rights & Provenance (plan 06 §7, §8.2, §8.3, §8.5) — Phase 21

Gate: `VP21_AUDIO_PIPELINE_VERIFIED`

## 1. Mục đích

Mọi audio asset (voice profile, TTS asset, SFX/BGM cue) phải truy được nguồn
(provenance) và quyền sử dụng (rights/license). PoC không publish audio không
có nguồn gốc rõ ràng (plan §5, §8.5).

## 2. Voice likeness (plan §7, §8.2)

- Dùng voice/likeness người thật → bắt buộc `rights_state != UNKNOWN` và
  `rights_metadata` (consent/terms) + approval.
- `approve()` **không tự khai báo license**: approval là quyết định của con
  người, không thay đổi `rights_state`; nếu `UNKNOWN` thì giữ `UNKNOWN` — chỉ
  metadata/voucher quyền mới nâng cấp.
- `VoiceRightsState`: `UNKNOWN | LICENSED | CONSENTED` (+ nơi cần `REJECTED`).

## 3. TTS asset provenance (plan §8.3)

`TtsAudioAsset` mang:

```text
content_hash        sha256 content (64 hex) — identity của file
source_request_hash request_hash của request đã tạo ra nó
sample_rate / channel_layout / duration_seconds
byte_size
```

Traceability: `DialogueTrack.audio -> TtsAudioAsset -> source_request_hash ->
TtsSynthesisRequest (dialogue_id + voice_profile_hash) -> CharacterVoiceProfile
(character_id) -> DialogueLine`. Một segment audio bất kỳ truy được về
request/voice/character/line.

## 4. SFX/BGM license (plan §8.5)

- Mỗi `SoundEffectCue`/`MusicCue` mang `license_state` (`LICENSED`/`REJECTED`/
  `UNKNOWN`) + `provenance` (nguồn/order/track).
- License `UNKNOWN`/`REJECTED` → issue `UNKNOWN_CUE_LICENSE`, cue không
  publish.
- Cue gắn timeline/shot + fade intent; đổi BGM chỉ invalidate mix/final cut
  (`MIX_ONLY`), không invalidate clip.

## 5. Kiểm chứng (verifier)

- `provenance_receipt.json`: asset content-hashed + source_request_hash;
  cue license LICENSED pass / UNKNOWN block; approve không nâng rights; BGM
  change chỉ invalidate MIX_ONLY; dialogue change invalidate TRACK_AND_MIX.
