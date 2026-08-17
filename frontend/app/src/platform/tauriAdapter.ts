/**
 * TauriPlatformAdapter — Implementation of PlatformAdapter for desktop Tauri environment.
 */

import type { MetricState } from '@windagent/studio-shell';
import type { PlatformAdapter } from './platformAdapter';

export class TauriPlatformAdapter implements PlatformAdapter {
  readonly kind = 'tauri' as const;

  private lastMetrics: MetricState = {
    cpu: 18,
    ram: 61,
    ramGb: 9.7,
    ramTotalGb: 16,
    gpu: 28,
    gpuName: 'NVIDIA GPU',
    vram: 42,
    vramGb: 6.7,
    vramTotalGb: 16,
    cpuHistory: [15, 18, 16, 21, 19, 18],
    ramHistory: [60, 61, 61, 61, 61, 61],
    gpuHistory: [25, 30, 26, 29, 27, 28],
    vramHistory: [42, 42, 42, 42, 42, 42],
  };

  async getSystemMetrics(): Promise<MetricState> {
    const updateHistory = (history: number[], nextVal: number) => [...history.slice(1), nextVal];

    if (typeof window !== 'undefined') {
      const tauriGlobal = (window as any).__TAURI__ || (window as any).__TAURI_INTERNALS__;
      const invokeFn = tauriGlobal?.invoke || (window as any).__TAURI_INVOKE__;

      if (typeof invokeFn === 'function') {
        try {
          const m = await invokeFn('get_system_metrics');
          if (m && typeof m.cpu === 'number') {
            const prev = this.lastMetrics;
            this.lastMetrics = {
              cpu: Math.round(m.cpu),
              ram: Math.round(m.ram),
              ramGb: m.ram_gb,
              ramTotalGb: m.ram_total_gb,
              gpu: Math.round(m.gpu),
              gpuName: m.gpu_name || prev.gpuName,
              vram: Math.round(m.vram),
              vramGb: m.vram_gb,
              vramTotalGb: m.vram_total_gb,
              cpuHistory: updateHistory(prev.cpuHistory, Math.round(m.cpu)),
              ramHistory: updateHistory(prev.ramHistory, Math.round(m.ram)),
              gpuHistory: updateHistory(prev.gpuHistory, Math.round(m.gpu)),
              vramHistory: updateHistory(prev.vramHistory, Math.round(m.vram)),
            };
            return this.lastMetrics;
          }
        } catch (err) {
          console.warn('[TauriPlatformAdapter] invoke get_system_metrics fallback:', err);
        }
      }
    }

    return this.lastMetrics;
  }

  async openExternal(url: string): Promise<void> {
    if (typeof window !== 'undefined') {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  }

  async selectFile(): Promise<string | string[] | null> {
    return null;
  }

  async getSecureCredential(): Promise<string | null> {
    return null;
  }
}

export function createTauriAdapter(): TauriPlatformAdapter {
  return new TauriPlatformAdapter();
}
