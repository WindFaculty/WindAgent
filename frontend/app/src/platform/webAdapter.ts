/**
 * WebPlatformAdapter — Implementation of PlatformAdapter for standard browser environment.
 */

import type { MetricState } from '@windagent/studio-shell';
import type { PlatformAdapter } from './platformAdapter';

export class WebPlatformAdapter implements PlatformAdapter {
  readonly kind = 'web' as const;

  private lastMetrics: MetricState = {
    cpu: 18,
    ram: 61,
    ramGb: 9.7,
    ramTotalGb: 16,
    gpu: 28,
    gpuName: 'Web GPU (Simulated)',
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
    const prev = this.lastMetrics;

    const nextCpu = Math.max(10, Math.min(90, Math.round(prev.cpu + (Math.random() * 6 - 3))));
    const nextRam = Math.max(50, Math.min(85, Math.round(prev.ram + (Math.random() * 2 - 1))));
    const nextRamGb = parseFloat(((nextRam / 100) * 16).toFixed(1));
    const nextGpu = Math.max(15, Math.min(95, Math.round(prev.gpu + (Math.random() * 8 - 4))));
    const nextVram = Math.max(35, Math.min(75, Math.round(prev.vram + (Math.random() * 2 - 1))));
    const nextVramGb = parseFloat(((nextVram / 100) * 16).toFixed(1));

    this.lastMetrics = {
      cpu: nextCpu,
      ram: nextRam,
      ramGb: nextRamGb,
      ramTotalGb: prev.ramTotalGb,
      gpu: nextGpu,
      gpuName: prev.gpuName,
      vram: nextVram,
      vramGb: nextVramGb,
      vramTotalGb: prev.vramTotalGb,
      cpuHistory: updateHistory(prev.cpuHistory, nextCpu),
      ramHistory: updateHistory(prev.ramHistory, nextRam),
      gpuHistory: updateHistory(prev.gpuHistory, nextGpu),
      vramHistory: updateHistory(prev.vramHistory, nextVram),
    };

    return this.lastMetrics;
  }

  async openExternal(url: string): Promise<void> {
    if (typeof window !== 'undefined') {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  }

  async selectFile(): Promise<string | null> {
    // In web, file selector can return synthetic path or fallback
    return null;
  }

  async getSecureCredential(): Promise<string | null> {
    return null;
  }
}

export function createWebAdapter(): WebPlatformAdapter {
  return new WebPlatformAdapter();
}
