/**
 * FrameSampler — Phase 6 (ban_ke_hoach_v1.md Section 12, Principle E)
 *
 * Two pipelines: Recording @60FPS (WGC→NVENC→MKV) vs AI observation @1-2 FPS
 * downscaled 1280×720 JPEG/WebP. Raw 1080p60 frames NEVER cross Tauri IPC
 * and NEVER reach Gemini — only down-sampled preview frames at low FPS.
 *
 * Mode "event-driven" sends a frame only when cue/state/tool_result changes
 * (plus at most 1 FPS periodic heartbeat while recording).
 */

import type { FrameSamplerConfig } from './types';
import { DEFAULT_FRAME_SAMPLER } from './types';
import type { RecorderPreviewFrame } from '../contracts/ipc';

export interface PreviewFrame {
  readonly dataUrl: string; // JPEG/WebP base64 data URL, 1280×720
  readonly ts: number; // monotonic ms since take start
  readonly width: 1280;
  readonly height: 720;
}

export class FrameSampler {
  private config: FrameSamplerConfig;
  private lastEmitMs = 0;
  private pending: PreviewFrame | null = null;

  constructor(config: Partial<FrameSamplerConfig> = {}) {
    this.config = { ...DEFAULT_FRAME_SAMPLER, ...config } as FrameSamplerConfig;
  }

  /** Minimum interval for periodic mode (1 FPS = 1000ms, 2 FPS = 500ms) */
  private get minIntervalMs(): number {
    return this.config.fps === 2 ? 500 : 1000;
  }

  /** Downscale dimensions are frozen per contract — caller must resize before calling. */
  get downscale() { return this.config.downscale; }
  get format() { return this.config.format; }

  /** Whether we should emit now (rate-limit + event-driven gate). */
  shouldEmit(nowMs: number, opts: { force?: boolean } = {}): boolean {
    if (opts.force) return true;
    if (this.config.mode === 'event-driven' && this.pending) return true;
    return nowMs - this.lastEmitMs >= this.minIntervalMs;
  }

  /** Stage a freshly captured preview frame (already downscaled). */
  stage(frame: PreviewFrame): void {
    this.pending = frame;
  }

  /**
   * Feed a `recorder://preview` event payload straight into the sampler.
   * The sidecar has already downscaled + JPEG-encoded the frame (Principle E);
   * this only maps the IPC shape and applies the rate gate. Heartbeat frames
   * without a jpeg payload are ignored.
   */
  stageFromRecorderEvent(payload: RecorderPreviewFrame, nowMs = Date.now()): boolean {
    const b64 = payload.jpeg_base64;
    if (!b64) return false;
    this.stage({
      dataUrl: `data:image/jpeg;base64,${b64}`,
      ts: typeof payload.ts === 'number' ? payload.ts : nowMs,
      // Frozen observation resolution — sidecar guarantees ≤1280×720.
      width: 1280,
      height: 720,
    });
    return true;
  }

  /** Consume the staged frame if rate gate allows — otherwise null (drop). */
  consume(nowMs = Date.now()): PreviewFrame | null {
    if (!this.pending) return null;
    if (!this.shouldEmit(nowMs)) return null;
    const out = this.pending;
    this.pending = null;
    this.lastEmitMs = nowMs;
    return out;
  }

  reset(): void {
    this.pending = null;
    this.lastEmitMs = 0;
  }
}
