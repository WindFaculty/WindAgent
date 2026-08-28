/**
 * Tauri IPC Contract — Live Record Control Plane — V2 Frozen
 * Gate: LIVE_RECORD_V2_CONTRACT_FROZEN
 *
 * Frontend NEVER touches NVENC/libav directly. The recording engine is a
 * sidecar data plane; Tauri is control plane only. The nested profile mirrors
 * `RecordingEngineProfile` from ./recordingEngine and is forwarded verbatim —
 * the engine's validator is the single source of truth for encoder settings.
 *
 * Raw frames never cross this surface; only preview JPEGs (≤2 FPS), audio
 * meters and measured telemetry.
 */

import type {
  RecordingEngineProfile,
  SegmentManifest,
} from './recordingEngine';

export type RecorderCommand =
  | 'recorder_prepare'
  | 'recorder_start'
  | 'recorder_pause'
  | 'recorder_resume'
  | 'recorder_stop'
  | 'recorder_get_status'
  | 'recorder_create_marker'
  // V2 (§11): recorder-level mute — the toggle reaches the MKV tracks.
  | 'recorder_mute'
  // V2 (§15): crash-safe recovery of an interrupted take.
  | 'recorder_recover'
  // V2 (§17): real monitor/window enumeration for the source picker.
  | 'recorder_get_sources'
  | 'recorder_get_capabilities';

export interface RecorderPrepareRequest {
  readonly execution_plan_id: string;
  readonly execution_plan_hash: string;
  readonly episode_id: string;
  readonly output_dir: string; // validated server-side, no raw path echo to UI beyond token
  readonly profile: RecordingEngineProfile;
}

export interface RecorderStartRequest {
  readonly execution_plan_id: string;
  readonly take_id?: string;
}

/** V2 (§11) — muting meters only is forbidden; this silences the tracks. */
export interface MuteRequest {
  readonly mic_muted: boolean;
  readonly system_muted: boolean;
}

/** V2 (§15) — scan an interrupted take, keep completed segments, drop the tail. */
export interface RecoverRequest {
  readonly output_dir: string;
}

export interface MarkerRequest {
  readonly marker_type: string;
  readonly cue_id?: string;
  readonly action_id?: string;
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

  /** §17 real telemetry — present once the native engine reports them. */
  readonly capture_fps?: number;
  readonly encode_fps?: number;
  readonly av_sync_error_ms?: number;
  readonly mic_drift_ppm?: number;
  readonly system_drift_ppm?: number;
  /** §18 resource stage: normal | preview_degraded | director_degraded | danger */
  readonly resource_stage?: string;

  readonly current_segment_index?: number;
  readonly current_segment_path?: string;
  readonly disk_write_mbps?: number;
  readonly nvenc_status: 'IDLE' | 'ENCODING' | 'ERROR' | 'UNAVAILABLE';
  readonly bitrate_mbps: number;
  readonly preview_available: boolean;
  readonly blockers?: readonly string[];
}

// ─── Source picker (§17 — real enumeration from the engine) ─────────────────

/** One enumerable display target — feeds `capture_source: {kind:'DISPLAY', id}`. */
export interface MonitorSource {
  readonly kind: 'DISPLAY';
  /** Device path fed back verbatim as `capture_source.id`. */
  readonly id: string;
  readonly label: string;
  readonly width: number;
  readonly height: number;
  readonly is_primary: boolean;
}

/** One enumerable window target — feeds `capture_source: {kind:'WINDOW', id}`. */
export interface WindowSource {
  readonly kind: 'WINDOW';
  /** HWND token fed back verbatim as `capture_source.id`. */
  readonly id: string;
  readonly label: string;
  readonly process: string;
}

export interface CaptureSources {
  readonly monitors: readonly MonitorSource[];
  readonly windows: readonly WindowSource[];
}

// ─── Capability probe (V2 — one real round-trip against the engine) ──────────

export interface NativeCapabilities {
  /** True only when D3D11 + WGC + NVENC (+ requested audio paths) all pass. */
  readonly engine_available: boolean;
  /** "wgc-nvenc-mkv" in production; "mock" under explicit dev simulation. */
  readonly backend: string;
  readonly contract_version: number;

  // D3D11 device layer (§6)
  readonly d3d11_ready: boolean;
  readonly gpu_adapter_name: string;
  readonly gpu_vendor_id: number;
  readonly gpu_vram_mb: number;
  readonly d3d_feature_level: number;
  readonly nvidia_adapter_selected: boolean;

  // WGC (§7)
  readonly wgc_available: boolean;
  readonly wgc_os_supported: boolean;

  // NVENC (§8)
  readonly nvenc_available: boolean;
  readonly nvenc_api_version: number;
  readonly nvenc_h264_supported: boolean;
  readonly nvenc_hevc_supported: boolean;
  readonly nvenc_max_width: number;
  readonly nvenc_max_height: number;
  readonly nvenc_bframes_supported: boolean;
  readonly nvenc_lookahead_supported: boolean;
  readonly nvenc_aq_supported: boolean;

  // Audio (§10/§11)
  readonly wasapi_available: boolean;
  readonly mic_available: boolean;
  readonly system_loopback_available: boolean;
  readonly aac_encoder_available: boolean;

  // Host
  readonly disk_free_gb: number;
  readonly output_writable: boolean;
  readonly libav_runtime_found: boolean;

  readonly blockers: readonly string[];
}

// ─── Events ──────────────────────────────────────────────────────────────────

export type RecorderEventName =
  | 'recorder://status'
  | 'recorder://segment'
  | 'recorder://preview'
  | 'recorder://warning'
  | 'recorder://error'
  | 'recorder://timeline'
  // V2 (§10): per-track loudness meters (mic/system kept separate — never mixed).
  | 'recorder://audio-meter';

export interface RecorderSegmentEvent {
  readonly take_id: string;
  readonly segment_index: number;
  readonly file_token: string; // tokenized delivery, never raw FS path
  readonly byte_len: number;
  readonly duration_sec: number;
  readonly is_playable: boolean;
}

/** V2 (§10) — per-track loudness for UI meters, post-recorder-tap. */
export interface AudioMeterEvent {
  readonly track: 'mic' | 'system';
  readonly rms_dbfs: number;
  readonly peak_dbfs: number;
  readonly muted: boolean;
}

export interface RecorderPreviewFrame {
  readonly take_id: string;
  readonly width: number;
  readonly height: number;
  /** Encoded byte count of the JPEG payload. */
  readonly data_len: number;
  /** Take-relative monotonic ms (engine stamps it from the media clock). */
  readonly timestamp_ms: number;
  /**
   * Down-scaled JPEG (≤1280×720, ≤2 FPS) — the ONLY frame payload allowed to
   * cross IPC (Principle E). Raw 1080p60 frames never leave the engine.
   */
  readonly jpeg_base64: string;
}

/** Stop response — manifest summary of everything written for the take. */
export type RecorderStopResult = SegmentManifest;

// IPC payload shape validation helpers
export function isRecorderStatus(v: unknown): v is RecorderStatus {
  if (!v || typeof v !== 'object') return false;
  const o = v as Record<string, unknown>;
  return typeof o.state === 'string' && typeof o.elapsed_sec === 'number' && typeof o.bitrate_mbps === 'number';
}
