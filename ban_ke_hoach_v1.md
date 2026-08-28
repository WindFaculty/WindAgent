Đã đủ thông tin để khóa kiến trúc. Tôi không cần hỏi thêm trước khi lập kế hoạch implementation.

Tôi cũng đã kiểm tra lại code trên nhánh `refactor/architecture-v3-hardening`. Có một điểm quan trọng: **kiến trúc mong muốn đã được mô tả trong repo, nhưng phần native WGC/D3D11/NVENC thực tế hiện vẫn chủ yếu là skeleton; production path hiện tại vẫn chạy qua FFmpeg `ddagrab`**.

## 1. Requirement được khóa

Từ đây Live Record được coi là có các invariant sau:

| Hạng mục              | Quyết định cuối                                         |
| --------------------- | ------------------------------------------------------- |
| Video source          | Chỉ màn hình / window, **không camera/webcam**          |
| Runtime               | **Tauri Desktop only**                                  |
| Capture               | **Direct Windows Graphics Capture**                     |
| GPU surface           | **D3D11**                                               |
| Encoder               | **Direct NVENC**, bắt buộc                              |
| CPU/software fallback | **Không cho production fallback**                       |
| Container             | **MKV segmented**                                       |
| Mic                   | Track riêng                                             |
| System Audio          | Track riêng                                             |
| Capture quality       | Quality-first                                           |
| Resource policy       | Có thể dùng tối đa CPU/GPU/RAM hợp lý để đạt chất lượng |
| Recording duration    | Chưa khóa; xác định bằng soak test thực tế              |
| AI Director           | Preview riêng ≤2 FPS, không chạm raw recording path     |

Pipeline cuối cùng:

```text
Windows Graphics Capture
        │
        ▼
    D3D11 Device
        │
        ▼
ID3D11Texture2D
        │
        ├──────────────────────────────┐
        │                              │
        ▼                              ▼
NVENC direct GPU                Preview pipeline
        │                       GPU downscale
        │                       ≤1280×720
        │                       1–2 FPS
        │                              │
        │                              ▼
        │                        Gemini Live
        │
        ▼
Encoded H264/HEVC
        │
        ├─────────────── Mic WASAPI
        │
        ├─────────────── System WASAPI loopback
        │
        ▼
     libavformat
        │
        ▼
 segmented MKV
        │
        ├── Video track
        ├── Microphone track
        └── System audio track
```

---

# 2. Audit lại code hiện tại

Các gap hiện tại khá rõ.

Cargo đã khai báo feature `wgc` và `nvenc`, nhưng chúng đang rỗng; dependency Windows/D3D11 còn bị comment.

`WgcCapture` hiện vẫn:

```rust
probe_available() -> false
poll_frame() -> None
```

tức chưa có WGC thực.

`NvencEncoder` cũng tương tự: probe trả `false`; `encode()` hiện tạo `EncodedPacket` mô phỏng dựa trên `data_len`, chưa gọi `nvEncodeAPI.dll`.

`LibavMuxer` hiện chưa phải libavformat thực; nó chủ yếu cộng `bytes_written` và tạo metadata segment.

Quan trọng hơn, `RecorderService` production hiện trực tiếp sở hữu:

```rust
FfmpegSegmentCapture
FfmpegPreview
```

và khi Start sẽ spawn FFmpeg capture.  Sau đó `start()` thực sự dựng `FfmpegCaptureConfig` rồi chạy `FfmpegSegmentCapture::start()`.

Audio hiện bị khóa hoàn toàn. `EngineProfile` có:

```rust
audio_enabled: false
```

và validation từ chối `audio_enabled=true`.

`WasapiCapture` cũng đang `probe_available() -> false` và `start()` trả `WASAPI_DISABLED`.

Frontend contract vẫn chứa `SOFTWARE_FALLBACK` và `audio_enabled: false`, nên contract này cũng phải được nâng version.

Vì vậy đây không phải task "polish Live Record". Đây là **native recording-engine completion/cutover**.

---

# 3. Nguyên tắc production mới

Tôi đề nghị khóa thêm 8 nguyên tắc.

### A. Zero-copy là mục tiêu bắt buộc

Hot path:

```text
WGC
 ↓
ID3D11Texture2D
 ↓
NVENC registered D3D11 resource
 ↓
Encoded bitstream
```

Không được có:

```text
GPU texture
 ↓
Readback RAM
 ↓
CPU BGRA frame
 ↓
Upload GPU
 ↓
NVENC
```

trong đường quay chính.

CPU readback chỉ được phép cho preview/debug cực thấp FPS nếu thực sự cần.

### B. FFmpeg CLI không còn là capture backend production

`ffmpeg_capture.rs` có thể được giữ:

```text
test
debug
legacy comparison
```

nhưng production build:

```text
WGC unavailable
       ↓
BLOCK RECORDING
```

Không được:

```text
WGC failure
 ↓
silently fallback ddagrab
```

### C. NVENC cũng fail-closed

Không có:

```text
NVENC
 ↓ failure
x264
```

Production phải báo:

```text
NVENC_UNAVAILABLE
```

và khóa Start.

### D. MKV là master

Không cần MP4 trong recording engine.

```text
take_xxx/
├── segment_000000.mkv
├── segment_000001.mkv
├── segment_000002.mkv
├── timeline.jsonl
├── manifest.json
└── recovery.json
```

MP4 sau này là export/post-production, không phải responsibility của hot recording path.

### E. Audio phải multi-track

Không mix trước khi lưu.

```text
MKV
├── Track 0: Video
├── Track 1: Microphone
└── Track 2: Desktop/System Audio
```

### F. Một clock authority

Video, Mic và System Audio phải cùng dựa trên:

```text
QueryPerformanceCounter / QPC
```

để chống A/V drift.

### G. Recording ưu tiên hơn AI

Nếu tài nguyên căng:

```text
Recording pipeline > Preview > Gemini observation
```

Không bao giờ giảm chất lượng file quay chỉ để giữ Gemini preview 2 FPS.

Preview có thể tự hạ:

```text
2 FPS
↓
1 FPS
↓
0.5 FPS
```

nhưng recorder vẫn giữ nguyên.

### H. Native status là source of truth

Không còn mock metric chen vào Tauri production.

---

# 4. PHASE 0 — Freeze Recording Engine V2 contract

Trước tiên sửa contract.

Hiện `RecordingEngineProfile` còn quá đơn giản.

Chuyển thành đại loại:

```ts
interface RecordingProfile {
  capture_source: {
    kind: "DISPLAY" | "WINDOW";
    id: string;
  };

  video: {
    width: number;
    height: number;
    fps: 30 | 60;

    encoder: "NVENC";
    codec: "H264" | "HEVC";

    rate_control: "CQP";
    cq: number;

    preset: "P5" | "P6" | "P7";
    multipass: "FULL_RES";
    lookahead: number;
    spatial_aq: boolean;
    temporal_aq: boolean;
    b_frames: number;
    gop_frames: number;
  };

  audio: {
    microphone: {
      enabled: boolean;
      device_id: string;
    };

    system: {
      enabled: boolean;
      device_id: string;
    };

    sample_rate: 48000;
    codec: "AAC";
  };

  container: {
    format: "MKV";
    segment_minutes: 5 | 10;
  };
}
```

### Default quality profile

Tôi đề xuất ban đầu:

```text
1920×1080
60 FPS

NVENC H.264
CQP
CQ 16
Preset P7
HQ tuning
Full-resolution multipass
Lookahead 32
Spatial AQ ON
Temporal AQ ON
B-frames 3
GOP 120 frames / 2 sec

Audio 48 kHz
AAC
Mic separate
System separate

MKV
5-minute segments
```

CQ nên cho phép khoảng:

```text
14 = cực cao
16 = high-quality default
18 = quality/storage cân bằng
20 = nhẹ hơn
```

Không nên dùng fixed `20 Mbps` làm authority nữa. Với quay code/text, **CQP phù hợp hơn CBR** vì nó ưu tiên chất lượng theo complexity.

### Gate

```text
LIVE_RECORD_V2_CONTRACT_FROZEN
```

---

# 5. PHASE 1 — Native dependencies

File trọng tâm:

```text
apps/desktop/native/recording-engine/Cargo.toml
```

Hiện Windows dependencies mới chỉ được comment.

Bổ sung Windows APIs cần thiết:

```text
Windows.Graphics.Capture
Direct3D11
DXGI
COM
WinRT
Media
MMDevice
WASAPI
QPC
```

Kiến trúc module nên chuyển thành:

```text
src/
├── capture/
│   ├── mod.rs
│   ├── wgc.rs
│   ├── capture_item.rs
│   └── d3d11_device.rs
│
├── encoder/
│   ├── mod.rs
│   ├── nvenc.rs
│   ├── nvenc_api.rs
│   └── nvenc_session.rs
│
├── audio/
│   ├── mod.rs
│   ├── device.rs
│   ├── microphone.rs
│   ├── loopback.rs
│   └── clock.rs
│
├── muxer/
│   ├── mod.rs
│   ├── libav.rs
│   ├── tracks.rs
│   └── timestamps.rs
│
└── ...
```

### Gate

Windows release build thành công mà không cần mock feature.

---

# 6. PHASE 2 — D3D11 Device Layer

Tạo một D3D11 device duy nhất cho cả capture và encoder.

```text
D3D11CreateDevice
      ↓
ID3D11Device
      ↓
ID3D11DeviceContext
      ↓
IDXGIDevice
```

Ưu tiên adapter NVIDIA.

Probe phải trả:

```text
adapter name
vendor
VRAM
D3D feature level
device creation status
```

Quan trọng: tránh để Windows chọn Intel iGPU nếu laptop hybrid graphics.

Nếu nhiều adapter:

```text
prefer NVIDIA
```

và verify captured texture + NVENC cùng GPU adapter.

### Gate

```text
D3D11_DEVICE_READY
NVIDIA_ADAPTER_SELECTED
```

---

# 7. PHASE 3 — Direct Windows Graphics Capture

Thay skeleton trong `capture/mod.rs`. Hiện backend thật đang luôn unavailable.

Implementation:

```text
GraphicsCaptureItem
        ↓
Direct3D11CaptureFramePool
        ↓
GraphicsCaptureSession
        ↓
FrameArrived
        ↓
ID3D11Texture2D
```

Support:

```text
Full display
Specific window
```

Không camera.

Cần xử lý:

```text
resolution change
window resize
display disconnect
HDR/SDR format
DPI
window close
capture item invalidation
```

Frame object phải trở thành handle/resource thay vì:

```rust
data_len: usize
```

Ví dụ abstraction:

```text
CapturedFrame
├── texture
├── width
├── height
├── format
├── qpc_timestamp
└── frame_number
```

### Bắt buộc

Không clone pixel buffer mỗi frame.

### Gate

Test capture:

```text
1080p60
5 min
60 FPS sustained
no RAM growth
no CPU framebuffer copy
```

---

# 8. PHASE 4 — Direct NVENC

Thay implementation giả trong `encoder/mod.rs`.

Flow:

```text
nvEncodeAPICreateInstance
        ↓
NvEncOpenEncodeSessionEx
        ↓
NvEncInitializeEncoder
        ↓
NvEncRegisterResource(D3D11 texture)
        ↓
NvEncMapInputResource
        ↓
NvEncEncodePicture
        ↓
NvEncLockBitstream
        ↓
encoded packet
```

Không copy texture về CPU trước encoder.

Probe phải xác minh:

```text
NVENC API
H264 support
HEVC support
max resolution
max sessions
B-frame support
lookahead
AQ
10-bit capability
```

### High Quality profile

Ưu tiên:

```text
P7
CQP
multipass full-resolution
lookahead
AQ
B-frames
```

Nếu GPU tải quá cao thì **không tự động hạ profile** trong take.

Chỉ cảnh báo:

```text
GPU_HEADROOM_LOW
```

User quyết định profile cho take tiếp theo.

### Gate

```text
WGC texture
   ↓
direct NVENC
   ↓
valid Annex-B stream
```

30 phút không encoder stall.

---

# 9. PHASE 5 — Native MKV / libavformat

`LibavMuxer` hiện chưa phải muxer thật.

Thực hiện real:

```text
avformat_alloc_output_context2
avformat_new_stream
avcodec_parameters
avio_open
avformat_write_header
av_interleaved_write_frame
av_write_trailer
```

Không dùng FFmpeg command-line để quay.

Libav được dùng cho:

```text
Muxing
Audio encoding/resampling nếu cần
Probe/validation
```

đều hợp lệ với requirement direct capture.

### Segmentation

Không cắt file ở frame bất kỳ.

```text
segment boundary requested
          ↓
force/request IDR
          ↓
finish current GOP
          ↓
close MKV
          ↓
fsync
          ↓
manifest update
          ↓
new MKV
```

Mỗi segment phải independently playable.

### Gate

Dùng `ffprobe` kiểm tra từng segment:

```text
valid container
H264/HEVC track exists
correct 60 FPS metadata
monotonic timestamps
no corrupt tail
```

---

# 10. PHASE 6 — WASAPI Microphone

Thay `WasapiCapture` placeholder hiện tại.

Sử dụng event-driven WASAPI.

```text
IMMDeviceEnumerator
        ↓
Mic endpoint
        ↓
IAudioClient
        ↓
IAudioCaptureClient
```

Không poll busy-loop.

Capture:

```text
native device format
 ↓
resample
 ↓
48 kHz
 ↓
audio encoder
```

Nếu microphone mono thì giữ track mono; không cần fake stereo nếu không có lý do.

---

# 11. PHASE 7 — WASAPI System Audio Loopback

Đây là một capture client riêng:

```text
Render endpoint
      ↓
AUDCLNT_STREAMFLAGS_LOOPBACK
      ↓
IAudioCaptureClient
```

Không trộn với mic.

Cuối cùng:

```text
Track 1 = Mic
Track 2 = System
```

Mute UI phải tác động recorder:

```text
mic mute
system mute
```

không chỉ tắt meter trên frontend.

---

# 12. PHASE 8 — Unified media clock & A/V sync

Đây là phase không nên bỏ qua.

Dùng:

```text
QueryPerformanceCounter
```

làm clock chung.

Mỗi frame:

```text
video_pts = frame_qpc - recording_start_qpc
```

Mỗi audio packet:

```text
audio_pts = packet_qpc - recording_start_qpc
```

Định kỳ tính:

```text
mic drift
system drift
video drift
```

Nếu audio clock lệch nhỏ:

```text
resampler compensation
```

Không được sửa bằng cách drop hàng loạt audio frame.

### Metric

```text
av_sync_error_ms
mic_drift_ppm
system_drift_ppm
```

### Gate

Sau soak test dài:

```text
audio/video sync không trôi có thể nhận thấy
```

---

# 13. PHASE 9 — GPU preview path

Recording path tuyệt đối không phụ thuộc Director.

Từ D3D11 texture:

```text
texture
 ↓
GPU downscale
 ↓
1280×720
 ↓
JPEG
 ↓
recorder://preview
```

Rate gate:

```text
max 2 FPS
```

Nếu system load tăng:

```text
2 → 1 → 0.5 FPS
```

nhưng:

```text
recording FPS NEVER changes
```

Gemini outage cũng không được làm recorder stop.

---

# 14. PHASE 10 — RecorderService hard cutover

Đây là thay đổi lớn nhất trong `service.rs`.

Hiện service trực tiếp dùng FFmpeg capture.

Sau cutover:

```text
RecorderService
├── WgcCapture
├── NvencEncoder
├── WasapiMic
├── WasapiLoopback
├── LibavMuxer
├── PreviewPipeline
├── SegmentManager
├── TimelineWriter
└── Telemetry
```

Xóa production code:

```rust
FfmpegSegmentCapture
FfmpegPreview
```

khỏi `RecorderService`.

Không cần nhất thiết xóa file `ffmpeg_capture.rs` ngay; có thể giữ làm development comparator, nhưng production service không import nó.

### Service state machine

Nâng thành:

```text
IDLE
 ↓
PROBING
 ↓
READY
 ↓
PREPARING
 ↓
RECORDING
 ↔
PAUSED
 ↓
FINALIZING
 ↓
COMPLETED

RECOVERING
ERROR
```

---

# 15. PHASE 11 — Crash-safe segmented writer

Mỗi segment:

```text
.tmp
 ↓
write
 ↓
finish MKV
 ↓
flush
 ↓
fsync
 ↓
validate
 ↓
rename atomic → .mkv
 ↓
manifest update
```

Manifest sử dụng atomic write:

```text
manifest.tmp
 ↓
fsync
 ↓
rename
```

Không để crash làm mất toàn take.

### Recovery

Khi desktop mở:

```text
scan recording directories
 ↓
find incomplete take
 ↓
validate all .mkv
 ↓
discard only invalid unfinished tail
 ↓
rebuild manifest
 ↓
RECOVERED
```

### Gate

Trong lúc record:

```text
taskkill recording-engine.exe /F
```

sau đó mở lại.

Kết quả yêu cầu:

```text
mọi completed segment vẫn playable
timeline còn nguyên
take recoverable
```

---

# 16. PHASE 12 — Tauri control plane

Tauri tiếp tục đúng vai trò hiện tại:

```text
React
 ↓ IPC
Tauri
 ↓ JSON/control
Recording sidecar
```

Không chuyển video raw qua Tauri.

Các command:

```text
recorder_probe
recorder_prepare
recorder_start
recorder_pause
recorder_resume
recorder_stop
recorder_create_marker
recorder_get_status
recorder_get_capabilities
recorder_recover
```

Events:

```text
recorder://state
recorder://status
recorder://preview
recorder://audio-meter
recorder://segment
recorder://timeline
recorder://warning
recorder://error
```

### Engine supervision

Tauri phải:

```text
spawn
health check
detect crash
collect exit code
restart only when safe
```

Không tự restart sidecar giữa một active take rồi giả vờ tiếp tục.

---

# 17. PHASE 13 — Frontend hard cutover

Tại UI hiện tại cần sửa vài quyết định thiết kế.

## Bỏ Camera

Panel:

```text
Nguồn Màn hình / Camera
```

đổi thành:

```text
Nguồn ghi hình
```

Options:

```text
Monitor 1
Monitor 2
Application Window
```

Không Sony camera, webcam, USB camera.

## Settings mới

```text
Video
├── Source
├── Resolution
├── FPS
├── Codec
├── Quality
└── Segment duration

Audio
├── Microphone
├── System Audio
├── Mic mute
└── System mute

Storage
├── Recording folder
└── Available storage
```

---

# 18. PHASE 14 — Loại bỏ mock authority

`useLiveRecord()` không được cung cấp production metrics nữa.

Tạo:

```text
useLiveRecordingController
```

làm application orchestration layer.

```text
LiveRecordPage
       ↓
useLiveRecordingController
       ├── useLiveRecorderSession
       ├── useLiveDirector
       ├── plan loader
       ├── preflight
       └── Take API
```

Controller chịu trách nhiệm:

```text
probe
prepare
start
pause
resume
stop
marker
recover
```

React component chỉ render.

---

# 19. PHASE 15 — Preflight thật

Trước Start:

```text
D3D11 adapter PASS
WGC PASS
NVENC PASS
capture source valid
mic PASS
system loopback PASS
output writable
disk PASS
FrozenPlan PASS
privacy scan PASS
sidecar healthy
```

Nếu một critical item fail:

```text
START disabled
```

Không dùng optimistic default.

---

# 20. PHASE 16 — Gemini Live lifecycle

Hạ tầng Gemini hiện có rồi; phần cần hoàn thiện chủ yếu là orchestration.

Start:

```text
Probe recorder
 ↓
Preflight
 ↓
Create Take
 ↓
Prepare native recorder
 ↓
Bootstrap Gemini Live
 ↓
Connect
 ↓
Director READY
 ↓
Start recorder
```

Nếu Gemini mất kết nối **sau khi đã quay**:

```text
Director DEGRADED
Recording CONTINUES
```

Điều này rất quan trọng.

Recording engine là critical path; AI Director không phải critical dependency sau Start.

---

# 21. PHASE 17 — Real telemetry

Hiện `service.rs` còn hard-code:

```text
frames_dropped = 0
dropped_pct = 0
```

và bitrate phần nào là estimate.

Phải thay bằng metric thật:

```text
Capture FPS
Encode FPS
Frames captured
Frames submitted
Frames encoded
Frames dropped
Capture queue depth
Encoder queue depth

NVENC latency p50/p95
GPU utilization
Video encode utilization
VRAM usage

CPU utilization
RAM

Disk write MB/s
Disk queue
Disk remaining

Mic RMS/Peak
System RMS/Peak
Audio underruns

A/V sync error

Preview FPS
Preview latency

Director latency
Director reconnects
```

---

# 22. PHASE 18 — Quality-first thermal/resource policy

Vì yêu cầu của bạn là **ưu tiên chất lượng và được phép sử dụng tối đa phần cứng**, không cần tối ưu để máy chạy "nhẹ".

Tuy nhiên phải tránh thermal collapse.

Recorder theo dõi:

```text
GPU temperature
GPU encode utilization
GPU clock
VRAM
CPU temperature nếu lấy được
disk temperature nếu có
```

Policy:

```text
normal
    ↓
use configured HQ profile

high GPU load
    ↓
degrade preview first

still high
    ↓
degrade Gemini observation rate

recording pipeline unchanged
```

Chỉ khi đạt mức nguy hiểm mới cảnh báo/dừng bảo vệ dữ liệu.

Không tự hạ:

```text
60 → 30 FPS
CQ 16 → 24
1080p → 720p
```

giữa một take.

---

# 23. PHASE 19 — Progressive soak benchmark

Vì chưa biết hệ thống chịu được bao lâu, không đặt con số tùy ý.

Test lần đầu theo staircase.

### Test A

```text
1080p60
5 phút
```

Verify media.

### Test B

```text
15 phút
```

### Test C

```text
30 phút
```

### Test D

```text
60 phút
```

### Test E

```text
120 phút
```

### Test F

Nếu vẫn ổn:

```text
240 phút
```

Mỗi stage chỉ chạy nếu stage trước PASS.

---

# 24. Thu thập dữ liệu trong stress test

Ghi mỗi 1–5 giây:

```text
timestamp
capture_fps
encode_fps
dropped_frames
GPU %
GPU encode %
GPU temperature
VRAM
CPU %
RAM
disk MB/s
disk free
A/V drift
preview latency
Gemini latency
```

Sau test tạo report:

```text
P50
P95
P99
max
```

và chart theo thời gian.

Từ đó mới quyết định:

```text
safe continuous recording duration
```

Thực tế nếu engine đúng và disk đủ, duration không nên bị giới hạn bởi architecture; mục tiêu phải là **resource-bound chứ không phải memory-leak-bound**.

---

# 25. Failure injection test

Không chỉ soak.

Phải chủ động phá hệ thống.

```text
Kill Gemini WebSocket
Kill API
Disable microphone
Change default audio device
Disconnect headset
Lock Windows
Resize window
Change display resolution
Unplug external display
NVENC initialization failure
Disk low
Disk full
Output permission removed
Kill recorder sidecar
Kill Tauri UI
Force sleep/wake
```

Và xác định expected behavior cho từng trường hợp.

Ví dụ:

```text
Gemini dies
→ continue recording

Mic dies
→ video + system audio continue
→ warning

System audio dies
→ video + mic continue
→ warning

Disk full
→ safely finalize current segment if possible
→ stop

WGC source disappears
→ finalize
→ stop with CAPTURE_SOURCE_LOST

NVENC dies
→ finalize if possible
→ hard stop
```

---

# 26. PHASE 20 — Packaging production

Installer phải chứa mọi runtime dependency.

Không dựa vào:

```text
user-installed ffmpeg
PATH
developer SDK
Visual Studio environment
```

Build pipeline phải package:

```text
WindAgent.exe
recording-engine.exe

required libav DLLs
required runtime DLLs
```

NVIDIA driver vẫn là system prerequisite.

Startup probe hiển thị rõ:

```text
Compatible NVIDIA GPU
Driver version
NVENC API version
WGC support
Audio support
```

---

# 27. Test hierarchy

Tôi đề xuất chia test rõ:

```text
tests/component/
    WGC abstractions
    NVENC state
    timestamp math
    segment state
    audio drift

tests/contract/
    TS ↔ Tauri ↔ sidecar IPC

tests/integration/
    WGC → NVENC
    NVENC → MKV
    WASAPI → MKV
    full A/V

tests/e2e/
    Tauri Live Record

tests/verification/
    5m
    15m
    30m
    60m+
    crash recovery
```

Không để test production recorder bị che bởi mock path.

---

# 28. Các file hiện tại sẽ chịu impact lớn nhất

### Native engine

```text
apps/desktop/native/recording-engine/Cargo.toml

src/lib.rs

src/capture/mod.rs
src/capture/ffmpeg_capture.rs

src/encoder/mod.rs

src/audio/mod.rs

src/muxer/mod.rs

src/preview/*
src/probe.rs
src/service.rs
src/telemetry/*
src/segment/*
src/ipc/*
```

`service.rs` là file cutover quan trọng nhất vì nó đang điều phối FFmpeg backend.

### Tauri

```text
apps/desktop/src-tauri/src/live_record/
├── commands.rs
├── engine_host.rs
├── state.rs
├── types.rs
├── playback.rs
└── tests.rs
```

### Frontend

```text
frontend/app/src/features/live-record/
├── contracts/
├── hooks/
├── pages/LiveRecordPage.tsx
├── components/DeviceSettingsPanel.tsx
├── components/AudioMonitoringPanel.tsx
├── components/RecordingStatusPanel.tsx
├── components/LiveMetricCards.tsx
├── components/LiveVideoPreview.tsx
├── components/DirectorPanel.tsx
└── __tests__/
```

---

# 29. Thứ tự thực hiện bắt buộc

Tôi sẽ thực hiện theo dependency graph này, không theo UI:

```text
P0  Contract V2
 │
 ▼
P1  Dependencies / Windows native foundation
 │
 ▼
P2  D3D11
 │
 ▼
P3  WGC
 │
 ▼
P4  NVENC
 │
 ▼
P5  LibAV/MKV
 │
 ├─────────────┐
 ▼             ▼
P6 Mic       P7 System Audio
 │             │
 └──────┬──────┘
        ▼
P8 A/V clock
        │
        ▼
P9 Preview
        │
        ▼
P10 RecorderService cutover
        │
        ▼
P11 Recovery
        │
        ▼
P12 Tauri
        │
        ▼
P13 Frontend
        │
        ▼
P14 Mock removal
        │
        ▼
P15 Preflight
        │
        ▼
P16 Gemini Director integration
        │
        ▼
P17 Telemetry
        │
        ▼
P18 Quality/thermal policy
        │
        ▼
P19 Soak + chaos
        │
        ▼
P20 Packaging
```

---

# 30. Definition of Done cuối cùng

Không được tuyên bố hoàn thành chỉ vì nút "Record" hoạt động.

`LIVE_RECORD_PRODUCTION_READY` chỉ PASS khi luồng sau chạy thật:

```text
Tauri Desktop
      ↓
Load Frozen Episode Plan
      ↓
Native capability probe
      ↓
NVIDIA D3D11 adapter
      ↓
WGC source selected
      ↓
NVENC probe PASS
      ↓
Mic WASAPI PASS
      ↓
System loopback PASS
      ↓
Preflight PASS
      ↓
Create Take
      ↓
Connect Gemini Live
      ↓
Start
      ↓
WGC → D3D11 → NVENC
      ↓
MKV segmented
      ↓
Video Track
Mic Track
System Track
      ↓
Gemini observes low-FPS preview
      ↓
Director executes frozen actions
      ↓
Pause / Resume
      ↓
Segment rollover
      ↓
Stop
      ↓
Flush encoder/audio
      ↓
Finalize MKV
      ↓
Manifest + Timeline
      ↓
Playback
      ↓
ffprobe validation PASS
```

Và phải chứng minh:

```text
No FFmpeg screen-capture backend in production path
No CPU/software encoder fallback
No fake recording metrics
No mock state in Tauri production
No camera dependency
No raw 1080p60 frames through Tauri IPC
No mixed mic/system master track
No corrupted completed segments after crash
No uncontrolled A/V drift
```

## Điểm quan trọng nhất

Tôi sẽ coi **Direct WGC → D3D11 → NVENC → MKV** là một hard architectural gate, không phải optimization sau này.

Hiện repo ghi kiến trúc này trong comment, nhưng implementation thực vẫn đang là FFmpeg capture cùng các WGC/NVENC/muxer skeleton.

Do đó lần triển khai tiếp theo nên là một **hard cutover khỏi FFmpeg capture**, chứ không tiếp tục mở rộng `FfmpegSegmentCapture`.

Với tiêu chí của bạn, tôi cũng sẽ không đặt deadline hay rút gọn scope để "xong nhanh": ưu tiên **đúng native architecture, zero-copy, chất lượng cao, multi-track audio, crash recovery và kiểm chứng bằng soak test thực tế**.
