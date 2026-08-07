# Video Technical Validation — Flow Video Generation (Phase 15, plan 04 §23.3)

- **Gate:** `VP15_FLOW_VIDEO_GENERATION_VERIFIED`
- **Modules:**
  - `tools/windagent_tools/google_flow/video_inspection.py` (port + policy)
  - `tools/windagent_tools/google_flow/video_candidates.py` (downloader)
  - `tools/windagent_tools/video_probe.py` (real `ffprobe` adapter — ngoài
    `google_flow`, thuộc process boundary như Phase 12 runtime)

## Mục đích

Một video candidate chỉ được `COMPLETED` sau khi vượt **technical
validation**: stream video tồn tại, duration/resolution/frame rate hợp lệ
(plan 04 §23.3). Candidate invalid **không bao giờ** vào canonical store và
job **không bao giờ** COMPLETED với tập candidate invalid.

## VideoInspectorPort

```python
class VideoInspectorPort(Protocol):
    def inspect(self, data: bytes) -> VideoInspection: ...
```

- Offline-testable: tests/verifier inject fake deterministic.
- **Không raise** cho input hỏng — input hỏng cho `VideoInspection(
  has_video_stream=False)` (fail closed).
- `VideoProbeUnavailableError` khi không tìm thấy binary probe.

```python
VideoInspection(
    has_video_stream: bool,
    duration_seconds: float | None,
    width: int | None,
    height: int | None,
    frame_rate: float | None,
    container: str,
    codec: str,
    probe_error: str,
)
```

## VideoInspectionPolicy (fail closed)

```python
VideoInspectionPolicy(
    require_video_stream=True,
    min_duration_seconds=0.5, max_duration_seconds=600.0,
    min_width=64, min_height=64,
    max_frame_rate=240.0, min_frame_rate=0.1,
)
```

`violations(inspection)` trả tuple lý do; rỗng = accepted.

## VideoCandidateDownloader (plan 04 §23.3)

Pipeline có thứ tự, atomic:

1. `fetch(uri)` → nếu fail → `VideoCandidateFetchError`.
2. Ghi quarantine TRƯỚC validation (plan 02 §21.2 order).
3. `classify_payload` — zero-byte / executable / archive / SVG / polyglot
   → `VideoCandidateInvalidError`.
4. MIME — image payload hoặc MIME không phải video/octet-stream → reject.
5. `inspector.inspect(data)` → `policy.violations()` — bất kỳ violation nào
   → `VideoCandidateInvalidError` (không publish).
6. `ContentAddressedStore.publish(data)` — atomic, không partial artifact.
7. Trả `VideoCandidateAcquisition` (candidate_id, job_id, content_hash,
   mime, size, inspection, published=True).

## FfprobeVideoInspector (thật, ngoài google_flow)

- `subprocess.run(argv, timeout, check=False)` — argv list, **không shell
  interpolation**; bounded stdout/stderr (plan 04 §8.2).
- Phân loại: missing binary → `VideoProbeUnavailableError`; timeout →
  `VideoInspectionError`; start failure → `VideoInspectionError`; non-zero
  exit → `VideoInspection(has_video_stream=False)` (fail closed).
- Parse JSON `ffprobe -v error -print_format json -show_format
  -show_streams`; avg_frame_rate `"30000/1001"` → float; `"0/0"` → None.

## Guarantees

- Candidate invalid → không publish, không COMPLETED.
- Job `COMPLETED` chỉ sau atomic publish + `record_candidates`.
- Generator duyệt **mọi** candidate (không mặc định chọn candidate đầu).
