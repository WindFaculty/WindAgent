# Voice Profile Policy (plan 06 §7-§8.2) — Phase 21

Gate: `VP21_AUDIO_PIPELINE_VERIFIED`

## 1. Mục đích

`CharacterVoiceProfile` (`core/.../video_production/audio.py`) gắn voice với
**character ID/revision**, không gắn bằng display name — character đổi tên
không làm mất mapping voice. `VoiceCastingService`
(`intelligence/.../video/audio/voice.py`) chọn voice theo profile/style, có
human approval khi cần, và **không reuse voice gây nhầm identity** nếu policy
cấm.

## 2. Ràng buộc domain (plan §7)

- `profile.character_id` là identity binding duy nhất; `character_name` chỉ là
  thông tin hiển thị.
- `provider`, `model`, `voice_id`, `voice_version` + `language`/`locale` được
  ghi đầy đủ.
- `profile_hash()` deterministic theo identity + version:
  `sha256(provider|model|voice_id|voice_version|language|locale|character_id)`.
  Cùng voice + cùng tham số → cùng hash; thay đổi bất kỳ thành phần → hash mới
  → TTS request mới (không nhầm cache/duplicate).
- `rights_state` + `rights_metadata` bắt buộc khi dùng voice/likeness người
  thật (xem `audio_rights_and_provenance.md`).
- `approved` + `preview_only`: **preview không bao giờ thành final track nếu
  chưa có human approval**.

## 3. Casting rules (plan §8.2)

Thứ tự chọn voice cho mỗi character:

```text
1. approved profile trong catalog dành riêng cho character đó
2. nếu không có → kiểm tra approvals dict (character_id -> actor)
3. nếu vẫn chưa có → preview + issue PREVIEW_NOT_APPROVED
   (pipeline sẽ KHÔNG chạy TTS cho preview)
```

- **VOICE_REUSE_FORBIDDEN**: hai character approved dùng chung `voice_key`
  (provider|model|voice_id) → issue chặn, không im lặng gán trùng.
- Mapping multi-character deterministic theo `profile_id` (tie-break ổn định);
  không bao giờ tráo voice giữa hai character.
- `approve()` có **audit**: ghi `actor` + `approved_at`; approval không đổi
  `rights_state` (không tự ý khai báo license) — quyền là sự thật riêng, chỉ
  người/voucher quyền mới ghi.

## 4. Kiểm chứng (verifier)

- `tts_contract_receipt.json`: mapping multi-character không tráo; preview
  không final; voice reuse bị chặn; approve giữ nguyên `rights_state`.
