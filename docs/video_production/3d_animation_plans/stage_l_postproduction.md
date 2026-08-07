# Stage L — Post-production

## 1. Kết quả cần đạt

Image sequence, dialogue, music và SFX được ghép thành MP4 bằng FFmpeg theo edit/mix plan versioned; final deliverable có thể verify và tái tạo. Stage này tận dụng `InputNormalizer`, `AssemblyPlanner`, `FfmpegRunner`, `MediaVerifier` và `ReproducibilityAuditor` hiện có, nhưng bổ sung input image-sequence từ Blender.

## 2. Điều kiện đầu vào

- Render frame manifests Stage J đã complete và không có blocking finding Stage K.
- Audio tracks/mix plan Stage E đã approved; facial/body timing không còn pending repair.
- FFmpeg/ffprobe version được probe và policy encoding đã khóa.
- Output workspace tách theo project/revision/run, không dùng path tùy ý từ input.

## 3. Phase 24 — FFmpeg Assembly

### Backlog

1. Mở rộng input normalization để nhận PNG/EXR frame sequence + fps/color metadata; detect missing/duplicate/gap frame trước assemble.
2. Tạo edit decision list theo shot ordering, frame ranges, transition, audio offset, subtitle và final duration.
3. Chuẩn hóa dialogue/SFX/BGM sample rate/channel layout; mix theo loudness/peak policy đã versioned.
4. Build FFmpeg argv dạng list từ allowlisted operations; không interpolate shell hoặc chấp nhận raw filter text không trusted.
5. Output qua staging file, ffprobe/decode verify rồi atomic publish; failed output giữ quarantine evidence.
6. Tạo proxy, thumbnail, subtitle và final MP4 như các derived artifacts có key riêng.
7. Ghi exact input hashes, EDL/mix/profile hash, FFmpeg version, argv đã redact, stdout/stderr và output hash.
8. Reproducibility audit so manifest/technical properties; bit-exact chỉ bắt buộc khi tool/platform/profile giống nhau.
9. Invalidation: đổi một render shot rebuild timeline/final; đổi BGM chỉ rebuild mix/final; đổi subtitle không rerender frames.

## 4. Kiểm thử bắt buộc

- Missing/corrupt/wrong-dimension frame và wrong fps bị chặn.
- Shot transition giữ duration/ordering; ending không black/truncated.
- Final có codec, resolution, fps, duration và audio stream đúng policy.
- Loudness/true peak/subtitle bounds trong tolerance.
- Path có khoảng trắng, Unicode và Windows separator hoạt động mà không shell injection.
- Cancel/retry không overwrite deliverable đã verified; duplicate request reuse đúng artifact.
- Thay BGM/subtitle chứng minh visual frames được reuse.

## 5. Evidence và gate

```text
artifacts/video_production_3d/phase_24/
├── input_sequence_manifest.json
├── edit_decision_list.json
├── audio_mix_plan.json
├── ffmpeg_command_receipts/
├── ffprobe_raw.json
├── media_decode_receipt.json
├── reproducibility_report.json
├── final_media_manifest.json
└── phase_verdict.json
```

Gate nội bộ `VP3D_P24_FFMPEG_ASSEMBLY_VERIFIED` pass khi final MP4 được build từ image sequences thật, vượt ffprobe/decode/audio checks và tái chạy bằng manifest mà không thao tác thủ công.

## 6. Rủi ro

- EXR/color management sai có thể làm final khác preview; color transform phải explicit và test bằng fixture.
- Transition/filter phức tạp dễ làm duration drift; EDL timeline math có unit tests theo frame.
- FFmpeg command là attack surface; chỉ planner trusted sinh argv từ schema bounded.
