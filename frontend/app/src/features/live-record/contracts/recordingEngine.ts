/**
 * Native Recording Engine Contract — V2 Frozen
 * Gate: LIVE_RECORD_V2_CONTRACT_FROZEN
 *
 * Locked architecture (ban_ke_hoach_v1.md §1, §3):
 *   Windows Graphics Capture → D3D11 texture → direct NVENC → libavformat MKV.
 *   Zero-copy GPU hot path; FFmpeg CLI and software encoders are NOT production
 *   backends (fail-closed BLOCK RECORDING). Multi-track audio: mic + system as
 *   separate MKV tracks, never mixed pre-record. QPC is the single clock authority.
 * Raw frames NEVER cross Tauri IPC; only preview JPEGs (≤2 FPS) + metrics.
 */

// ─── Capture source ──────────────────────────────────────────────────────────

export type CaptureSourceKind = 'DISPLAY' | 'WINDOW';

export interface CaptureSource {
  readonly kind: CaptureSourceKind;
  /** Monitor device path (DISPLAY) or HWND token (WINDOW); empty = primary display */
  readonly id: string;
}

// ─── Video ───────────────────────────────────────────────────────────────────

export type VideoRateControl = 'CQP';
export type NvencPreset = 'P5' | 'P6' | 'P7';
export type NvencMultipass = 'DISABLED' | 'HALF_RES' | 'FULL_RES';

export interface VideoConfig {
  readonly width: number;
  readonly height: number;
  readonly fps: 60 | 30;

  /** Direct NVENC is mandatory — no software fallback exists in production. */
  readonly encoder: 'NVENC';
  readonly codec: 'H264' | 'HEVC';

  /** Quality-first: CQP over fixed bitrate for screen content. */
  readonly rate_control: VideoRateControl;
  /** 14 = extreme quality · 16 = high-quality default · 18 = balanced · 20 = light */
  readonly cq: number;

  readonly preset: NvencPreset;
  readonly multipass: NvencMultipass;
  /** Lookahead depth in frames (0 disables; max 32). */
  readonly lookahead: number;
  readonly spatial_aq: boolean;
  readonly temporal_aq: boolean;
  readonly b_frames: number;
  readonly gop_frames: number;
}

// ─── Audio (multi-track — each source becomes its own MKV track) ─────────────

export interface AudioTrackConfig {
  readonly enabled: boolean;
  /** WASAPI endpoint id; empty = default device. */
  readonly device_id: string;
}

export interface AudioConfig {
  readonly microphone: AudioTrackConfig;
  readonly system: AudioTrackConfig;
  readonly sample_rate: 48000;
  readonly codec: 'AAC';
}

// ─── Container ───────────────────────────────────────────────────────────────

export interface ContainerConfig {
  /** MKV is the master recording container; MP4 is export-only, post-production. */
  readonly format: 'MKV';
  readonly segment_minutes: 5 | 10;
}

// ─── Profile ─────────────────────────────────────────────────────────────────

export interface RecordingEngineProfile {
  readonly capture_source: CaptureSource;
  readonly video: VideoConfig;
  readonly audio: AudioConfig;
  readonly container: ContainerConfig;
}

/** Default quality-first profile (ban_ke_hoach_v1.md §4). */
export const DEFAULT_ENGINE_PROFILE: RecordingEngineProfile = {
  capture_source: { kind: 'DISPLAY', id: '' },
  video: {
    width: 1920,
    height: 1080,
    fps: 60,
    encoder: 'NVENC',
    codec: 'H264',
    rate_control: 'CQP',
    cq: 16,
    preset: 'P7',
    multipass: 'FULL_RES',
    // Lookahead off (mirrors the engine default): no B-frames means it only
    // delays packets — a crash-loss window against §15 crash-safe segments.
    lookahead: 0,
    spatial_aq: true,
    temporal_aq: true,
    // B-frames off: the engine's sync-mode NVENC session (single output
    // bitstream buffer) completes B-chain pictures in presentation order,
    // which Matroska's decode-order requirement forbids.
    b_frames: 0,
    gop_frames: 120,
  },
  audio: {
    microphone: { enabled: true, device_id: '' },
    system: { enabled: true, device_id: '' },
    sample_rate: 48000,
    codec: 'AAC',
  },
  container: { format: 'MKV', segment_minutes: 5 },
};

/** Wire-contract version bumped on every breaking profile change. */
export const ENGINE_CONTRACT_VERSION = 2;

// ─── Manifests / telemetry ───────────────────────────────────────────────────

export interface SegmentManifest {
  readonly take_id: string;
  readonly execution_plan_id: string;
  readonly segments: readonly {
    readonly index: number;
    readonly file_token: string;
    readonly duration_sec: number;
    readonly byte_len: number;
    readonly is_playable: boolean;
  }[];
  readonly timeline_ref: string; // timeline.jsonl token
  readonly created_at: string;
}

export interface EngineTelemetry {
  // Capture
  readonly capture_fps: number;
  readonly frames_captured: number;
  readonly frames_submitted: number;
  // Encode
  readonly encode_fps: number;
  readonly frames_encoded: number;
  readonly frames_dropped: number;
  readonly dropped_pct: number;
  // Queues
  readonly capture_queue_depth: number;
  readonly encoder_queue_depth: number;
  // NVENC
  readonly nvenc_latency_ms_p50?: number;
  readonly nvenc_latency_ms_p95?: number;
  readonly nvenc_util_pct?: number;
  // Host resources
  readonly gpu_util_pct?: number;
  readonly vram_used_mb?: number;
  readonly cpu_util_pct?: number;
  readonly ram_used_mb?: number;
  // Disk
  readonly disk_write_mbps: number;
  readonly disk_free_gb: number;
  // Audio
  readonly av_sync_error_ms?: number;
  readonly mic_drift_ppm?: number;
  readonly system_drift_ppm?: number;
  // Preview / director
  readonly preview_delay_ms?: number; // must be < 200ms
  readonly director_latency_ms?: number;
  readonly bitrate_mbps: number;
}

// ─── Playback payload contract (unchanged from V1) ───────────────────────────

export interface PlaybackEngineContract {
  /** TYPE: 15-40 chars/s | PASTE: bulk insert */
  readonly mode: 'TYPE' | 'PASTE';
  readonly before_hash?: string;
  readonly after_hash?: string;
  readonly payload_ref: string;
  readonly typing_profile?: {
    readonly chars_per_second: number;
    readonly pause_after_line_ms?: number;
    readonly pause_after_block_ms?: number;
  };
}

// Performance gates (frozen acceptance reference — ban_ke_hoach_v1.md §27)
export const RECORDING_PERFORMANCE_GATES = {
  dropped_frames_pct_max: 0.1,
  preview_delay_ms_max: 200,
  gemini_sample_fps_max: 2,
  nvenc_required: true,
  soak_minutes: 30,
} as const;

// Abstract port — implemented by the Rust recording-engine sidecar
export interface RecordingEnginePort {
  prepare(profile: RecordingEngineProfile, output_dir: string): Promise<{ ok: boolean; reason?: string }>;
  start(take_id: string): Promise<void>;
  pause(): Promise<void>;
  resume(): Promise<void>;
  stop(): Promise<SegmentManifest>;
  getTelemetry(): Promise<EngineTelemetry>;
  createMarker(marker_type: string): Promise<void>;
}
