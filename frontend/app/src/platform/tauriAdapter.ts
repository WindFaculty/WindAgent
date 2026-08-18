/**
 * TauriPlatformAdapter — Implementation of PlatformAdapter for desktop Tauri environment.
 * Phase 14 Web/Desktop Convergence.
 */

import type { MetricState } from '@windagent/studio-shell';
import type {
  PlatformAdapter,
  PlatformCapabilities,
  FilePickerOptions,
  PlatformNotificationOptions,
} from './platformAdapter';

export class TauriPlatformAdapter implements PlatformAdapter {
  readonly kind = 'tauri' as const;
  readonly platform = 'desktop' as const;

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

  async getSystemCapabilities(): Promise<PlatformCapabilities> {
    return {
      supportsNativeFilePicker: true,
      supportsNativeNotifications: true,
      supportsSystemMetrics: true,
      supportsLocalRuntime: true,
      supportsDeepLinks: true,
    };
  }

  async getSystemMetrics(): Promise<MetricState> {
    return this.getNativeSystemMetrics();
  }

  async getNativeSystemMetrics(): Promise<MetricState> {
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
      const tauriGlobal = (window as any).__TAURI__;
      const shellOpen = tauriGlobal?.shell?.open || tauriGlobal?.opener?.openUrl;
      if (typeof shellOpen === 'function') {
        try {
          await shellOpen(url);
          return;
        } catch {
          // fallback to window.open
        }
      }
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  }

  async selectFile(options?: FilePickerOptions): Promise<string | string[] | null> {
    if (typeof window !== 'undefined') {
      const tauriDialog = (window as any).__TAURI__?.dialog;
      if (tauriDialog && typeof tauriDialog.open === 'function') {
        try {
          return await tauriDialog.open({
            multiple: options?.multiple ?? false,
            directory: options?.directory ?? false,
          });
        } catch (err) {
          console.warn('[TauriPlatformAdapter] dialog.open error:', err);
        }
      }
    }
    return null;
  }

  async showNotification(title: string, options?: PlatformNotificationOptions): Promise<void> {
    if (typeof window !== 'undefined') {
      const tauriNotification = (window as any).__TAURI__?.notification;
      if (tauriNotification && typeof tauriNotification.sendNotification === 'function') {
        try {
          await tauriNotification.sendNotification({
            title,
            body: options?.body,
          });
          return;
        } catch {
          // fallback to web notification
        }
      }
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, { body: options?.body, icon: options?.icon });
      }
    }
  }

  async getSecureCredential(key: string): Promise<string | null> {
    if (typeof window !== 'undefined') {
      const tauriGlobal = (window as any).__TAURI__ || (window as any).__TAURI_INTERNALS__;
      const invokeFn = tauriGlobal?.invoke || (window as any).__TAURI_INVOKE__;
      if (typeof invokeFn === 'function') {
        try {
          return await invokeFn('get_secure_credential', { key });
        } catch {
          return null;
        }
      }
    }
    return null;
  }
}

export function createTauriAdapter(): TauriPlatformAdapter {
  return new TauriPlatformAdapter();
}
