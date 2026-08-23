/**
 * Native Recording Engine Contract — Phase 0 Frozen
 * Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
 *
 * Two pipelines: Recording path (60 FPS -> NVENC -> MKV) vs AI observation (1-2 FPS downscale).
 * Raw frames NEVER cross Tauri IPC; only preview frames + metrics.
 */

export type CaptureBackend = 'WGC' | 'MOCK';
export type EncoderBackend = 'NVENC' | 'SOFTWARE_FALLBACK' | 'MOCK';
export type MuxerKind = 'MKV_SEGMENTED';

export interface RecordingEngineProfile {
  readonly capture: CaptureBackend;
  readonly encoder: EncoderBackend;
  readonly muxer: MuxerKind;
  readonly resolution: { readonly width: number; readonly height: number };
  readonly fps: 60 | 30;
  readonly codec: 'H264' | 'HEVC';
  readonly bitrate_mbps: number;
  readonly segment_minutes: 5 | 10;
  readonly audio_enabled: false; // P0 locked to false
}

export const DEFAULT_ENGINE_PROFILE: RecordingEngineProfile = {
  capture: 'WGC',
  encoder: 'NVENC',
  muxer: 'MKV_SEGMENTED',
  resolution: { width: 1920, height: 1080 },
  fps: 60,
  codec: 'H264',
  bitrate_mbps: 20,
  segment_minutes: 5,
  audio_enabled: false,
};

export interface SegmentManifest {
  readonly take_id: string;
  readonly execution_plan_id: string;
  readonly segments: readonly {
    readonly index: number;
    readonly file_token: string;
    readonly duration_sec: number;
    readonly is_playable: boolean;
  }[];
  readonly timeline_ref: string; // timeline.jsonl token
  readonly created_at: string;
}

export interface EngineTelemetry {
  readonly frames_captured: number;
  readonly frames_encoded: number;
  readonly frames_dropped: number;
  readonly dropped_pct: number;
  readonly encode_latency_ms_p50?: number;
  readonly disk_write_mbps: number;
  readonly nvenc_util_pct?: number;
  readonly preview_delay_ms?: number; // must be < 200ms
}

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

// Performance gates (Phase 11 baseline, frozen in P0 as acceptance reference)
export const RECORDING_PERFORMANCE_GATES = {
  dropped_frames_pct_max: 0.1,
  preview_delay_ms_max: 200,
  gemini_sample_fps_max: 2,
  nvenc_required: true,
  soak_minutes: 30,
} as const;

// Abstract port — implemented by Rust sidecar in later phases
export interface RecordingEnginePort {
  prepare(profile: RecordingEngineProfile, output_dir: string): Promise<{ ok: boolean; reason?: string }>;
  start(take_id: string): Promise<void>;
  pause(): Promise<void>;
  resume(): Promise<void>;
  stop(): Promise<SegmentManifest>;
  getTelemetry(): Promise<EngineTelemetry>;
  createMarker(marker_type: string): Promise<void>;
}
