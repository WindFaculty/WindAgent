# Voice Identity Policy

Stage E, Phase 10, backlog 2 & 3. Authority: `stage_e_concurrent_audio.md §2, §3`.

## Nguyên tắc

- Voice bind theo `character_id`, KHÔNG theo display name.
- `CharacterVoiceProfileId` → `VoiceBinding` version theo:
  `character_id + provider/model/voice_id/voice_version + locale + rights + approval`.
- Đổi display name → **không** đổi voice binding, **không** tạo artifact mới.
- Đổi voice revision (voice_id/voice_version) → **tạo** key mới, **tạo** artifact
  mới (track + alignment + facial + mix/final bị invalidate).

## Rights gate (stage_e §4)

- `preview_only=True` → không bao giờ thành final.
- Real voice (`voice_id` bắt đầu `real:`) → cần `CONSENTED` + `approved` +
  `approval_actor`. Thiếu một trong ba → `VoiceConsentMissingError`, fail closed
  trước publish.

## Canonical request hash (backlog 3)

`TtsSynthesisRequest.request_hash()` = SHA-256(canonical JSON) của:

- `dialogue_revision_hash`,
- `voice_profile_hash`,
- `provider_id`,
- `text`, `locale`, `language`, `sample_rate`, `emotion`.

Hai request giống hệt (`same revision + same voice + same params`) → cùng hash →
retry REUSE artifact, không re-synthesize. Đổi dialogue revision hoặc voice
revision → hash đổi → `TtsAudioAsset` mới.

## Secret redaction

API key / token / secret / bearer / password được redact thành `<redacted>`
trước khi vào receipt (`redact_secrets`).
