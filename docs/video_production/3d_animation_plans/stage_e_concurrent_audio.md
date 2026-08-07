# Stage E — Audio chạy song song

## 1. Kết quả cần đạt

Ngay sau khi screenplay revision được khóa, audio production chạy độc lập và song song với asset/scene/animation. Mỗi character giữ cùng voice identity qua các episode; TTS, forced alignment và timing tạo dữ liệu trực tiếp cho facial animation thay vì chỉ tạo một file âm thanh cuối.

## 2. Điều kiện đầu vào

- Screenplay/dialogue dùng ID ổn định và revision immutable.
- `CharacterMasterId` đã có mapping tới `CharacterVoiceProfile` hoặc trạng thái cần casting.
- Các model hiện có `DialogueTrack`, `WordTimestamp`, `AudioMixPlan` và `TtsProviderPort` được giữ làm nền tảng.
- Policy quyền giọng nói/likeness và approval actor được định nghĩa.

## 3. Phase 10 — Concurrent Audio Production

### Luồng orchestration

```text
ScreenplayLocked
├── ProduceAudio
│   ├── PrepareDialogue
│   ├── CastVoice / ResolveVoiceProfile
│   ├── SynthesizeTTS
│   ├── ForcedAlign
│   └── PublishDialogueTrack
└── Prepare3DProduction
```

Fan-in chỉ xảy ra trước final animation timing/lip-sync. Asset, environment và animation library lookup không phải đợi TTS.

### Backlog

1. Giữ `TtsProviderPort` provider-neutral; thêm capability metadata cho language, emotion, sample rate, timestamps và local/API mode.
2. Version `CharacterVoiceProfile` theo character ID, provider/model/voice/version, locale, rights state và approval.
3. Canonicalize request hash từ dialogue revision + voice profile hash + synthesis parameters; retry không synthesize trùng.
4. Validate output sample rate, channel layout, duration, decode và content hash trước publish.
5. Tạo `ForcedAlignmentPort`; lưu word/phoneme timestamps, confidence, tool/model/version và alignment hash.
6. Với line dài hơn shot: tạo typed proposal `EXTEND_SHOT`, `SHORTEN_TEXT`, `CHANGE_PACING` hoặc `HUMAN_REVIEW`; không tự cắt câu.
7. Persist DAG state để worker restart tiếp tục line còn thiếu mà không làm lại audio đã hoàn thành.
8. Thiết lập per-provider concurrency, retry budget và cancellation. Nhánh audio fail không được làm mất trạng thái nhánh 3D.
9. Invalidation: đổi dialogue/voice invalidates track + alignment + facial + mix/final; đổi BGM chỉ invalidates mix/final.

## 4. Kiểm thử bắt buộc

- Cùng character và voice revision cho request hash/voice identity ổn định qua episode.
- Đổi display name không đổi voice binding; đổi voice revision tạo artifact mới.
- TTS timeout, invalid bytes, duration 0, unsupported locale và low-confidence alignment fail đúng loại.
- Hai line chạy song song nhưng output ordering theo screenplay vẫn deterministic.
- Restart giữa các line reuse completed audio; cancel không publish partial file.
- Real-voice profile thiếu consent không thể chuyển từ preview sang final.
- Secret/API token được redact khỏi receipts.

## 5. Deliverables và evidence

```text
docs/video_production_3d/audio/
├── concurrency_contract.md
├── voice_identity_policy.md
├── forced_alignment_contract.md
└── timing_resolution_policy.md

artifacts/video_production_3d/phase_10/
├── dialogue_fixture_matrix.json
├── voice_identity_receipt.json
├── tts_contract_receipt.json
├── alignment_receipt.json
├── concurrency_recovery_receipt.json
└── phase_verdict.json
```

Gate nội bộ `VP3D_P10_CONCURRENT_AUDIO_VERIFIED` pass khi một fixture nhiều nhân vật chứng minh parallel execution, voice identity, alignment, resume và rights gate trên cùng revision.

## 6. Rủi ro và giới hạn

- TTS open-source có thể không cung cấp phoneme timing; forced aligner phải là adapter riêng, không giả confidence.
- Synthesis nhanh nhưng alignment chậm có thể trở thành critical path; đo thời gian từng node.
- Voice/model version có thể biến mất; artifact phải pin đủ provenance và lưu audio đã được phê duyệt để reuse.
