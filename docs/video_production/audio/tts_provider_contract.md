# TTS Provider Contract (plan 06 §8.3) — Phase 21

Gate: `VP21_AUDIO_PIPELINE_VERIFIED`

## 1. Mục đích

`TtsSynthesizer` (`intelligence/.../video/audio/tts.py`) gọi TTS qua một
**port** (`TtsProviderPort`), không import provider trực tiếp — provider-
neutral (plan §4 clean-room). Request mang đủ dialogue ID + voice profile hash
+ synthesis parameters; output phải đạt validation trước khi publish.

## 2. Port (Protocol)

```text
TtsProviderPort.synthesize(request: TtsSynthesisRequest) -> TtsSynthesisResult
```

`TtsSynthesisRequest` (frozen dataclass, provider-neutral):

```text
request_id          TtsRequestId
dialogue_id         str
text                str (prepared text — đã chuẩn hóa §8.1)
voice_profile_hash  sha256 của voice identity (§8.2)
language            vi-VN
locale              vi-VN
synthesis_params    dict (mode, sample_rate, channels)
request_hash        str — deterministic, chống duplicate cost
```

`TtsSynthesisResult`:

```text
content            bytes (WAV/PCM thô cho PoC)
sample_rate        int
channel_layout     str
duration_seconds   float
timed_out          bool
```

## 3. Fail-closed rules (plan §8.3)

Một output chỉ được publish thành `TtsAudioAsset` khi **tất cả**:

```text
- không timeout (timed_out == False)              -> TTS_TIMEOUT      nếu có
- content không rỗng                              -> TTS_EMPTY_OUTPUT nếu rỗng
- sample_rate > 0, channel_layout hợp lệ,
  duration_seconds > 0, content_hash là SHA-256 64 hex  -> TTS_INVALID_OUTPUT
```

- **Invalid output không bao giờ publish**: mọi lỗi thành `AudioIssue` typed;
  không tạo asset, không ghi vào track.
- `request_hash = sha256(dialogue_id|text|voice_profile_hash|language|locale|
  synthesis_params)` — deterministic: cùng request → cùng hash → tránh gọi TTS
  trùng → tránh duplicate cost (gate cost §19).
- `TtsAudioAsset` bắt buộc `content_hash` (64 hex), `sample_rate > 0`,
  `duration_seconds > 0` — validation tại domain, không phụ thuộc provider.
- Retry bounded theo budget §19; pipeline chỉ gọi TTS cho profile **approved**.

## 4. Kiểm chứng (verifier)

- `tts_contract_receipt.json`: valid output → asset đầy đủ hash/duration;
  timeout/empty/invalid → issue typed, **không asset**; cùng input → cùng
  `request_hash`; dialogue khác → hash khác.
