/**
 * Tauri IPC Contract — Live Record Control Plane — Phase 0 Frozen
 * Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
 *
 * Minimal command surface. Frontend NEVER touches NVENC/libav directly.
 * Recording engine is a sidecar data plane; Tauri is control plane only.
 */

export type RecorderCommand =
  | 'recorder_prepare'
  | 'recorder_start'
  | 'recorder_pause'
  | 'recorder_resume'
  | 'recorder_stop'
  | 'recorder_get_status'
  | 'recorder_create_marker'
  | 'recorder_get_capabilities';

export interface RecorderPrepareRequest {
  readonly execution_plan_id: string;
  readonly execution_plan_hash: string;
  readonly episode_id: string;
  readonly output_dir: string; // validated server-side, no raw path echo to UI beyond token
  readonly profile: {
    readonly resolution: string;
    readonly fps: number;
    readonly codec: string;
    readonly segment_minutes: number;
    readonly audio_enabled: false;
  };
}

export interface RecorderStartRequest {
  readonly execution_plan_id: string;
  readonly take_id?: string;
}

export interface RecorderStatus {
  readonly state: import('../domain/types').LiveRecordSessionStatus;
  readonly take_id?: string;
  readonly execution_plan_id?: string;
  readonly elapsed_sec: number;
  readonly frames_captured: number;
  readonly frames_encoded: number;
  readonly frames_dropped: number;
  readonly dropped_pct: number;
  readonly current_segment_index?: number;
  readonly current_segment_path?: string;
  readonly disk_write_mbps?: number;
  readonly nvenc_status: 'IDLE' | 'ENCODING' | 'ERROR' | 'UNAVAILABLE';
  readonly bitrate_mbps: number;
  readonly preview_available: boolean;
  readonly blockers?: readonly string[];
}

export interface MarkerRequest {
  readonly marker_type: string;
  readonly cue_id?: string;
  readonly action_id?: string;
}

export type RecorderEventName =
  | 'recorder://status'
  | 'recorder://segment'
  | 'recorder://preview'
  | 'recorder://warning'
  | 'recorder://error'
  | 'recorder://timeline';

export interface RecorderSegmentEvent {
  readonly take_id: string;
  readonly segment_index: number;
  readonly file_token: string; // tokenized delivery, never raw FS path
  readonly started_at: string;
  readonly ended_at?: string;
  readonly is_playable: boolean;
}

export interface RecorderPreviewFrame {
  readonly take_id: string;
  readonly frame_token: string;
  readonly width: number;
  readonly height: number;
  readonly ts: number; // monotonic ms
  /**
   * Down-scaled JPEG (≤1280×720, ≤2 FPS) — the ONLY frame payload allowed to
   * cross IPC (Principle E). Raw 1080p60 frames never leave the engine.
   */
  readonly jpeg_base64?: string;
}

// IPC payload shape validation helpers
export function isRecorderStatus(v: unknown): v is RecorderStatus {
  if (!v || typeof v !== 'object') return false;
  const o = v as Record<string, unknown>;
  return typeof o.state === 'string' && typeof o.elapsed_sec === 'number' && typeof o.bitrate_mbps === 'number';
}

// Capability contract for native side
export interface NativeCapabilities {
  readonly wgc_available: boolean;
  readonly nvenc_available: boolean;
  readonly wasapi_available: boolean; // P0: false engineering, but capability advertised
  readonly disk_free_gb: number;
  readonly output_writable: boolean;
  // Phase 8/9 real-probe extensions — present only when the engine sidecar
  // is available and has probed the host's ffmpeg pipeline.
  readonly engine_available?: boolean;
  readonly backend?: string; // "ffmpeg-ddagrab-nvenc" | "mock"
  readonly blockers?: readonly string[];
}
