/**
 * WebPlatformAdapter — Implementation of PlatformAdapter for standard browser environment.
 * Phase 14 Web/Desktop Convergence.
 */

import type { MetricState } from '@windagent/studio-shell';
import type {
  PlatformAdapter,
  PlatformCapabilities,
  FilePickerOptions,
  PlatformNotificationOptions,
} from './platformAdapter';

export class WebPlatformAdapter implements PlatformAdapter {
  readonly kind = 'web' as const;
  readonly platform = 'web' as const;

  private lastMetrics: MetricState = {
    cpu: 0,
    ram: 0,
    ramGb: 0,
    ramTotalGb: 16,
    gpu: 0,
    gpuName: 'Web GPU (Host Telemetry Unavailable)',
    vram: 0,
    vramGb: 0,
    vramTotalGb: 16,
    cpuHistory: [0, 0, 0, 0, 0, 0],
    ramHistory: [0, 0, 0, 0, 0, 0],
    gpuHistory: [0, 0, 0, 0, 0, 0],
    vramHistory: [0, 0, 0, 0, 0, 0],
  };

  async getSystemCapabilities(): Promise<PlatformCapabilities> {
    const hasNotifications = typeof window !== 'undefined' && 'Notification' in window;
    return {
      supportsNativeFilePicker: false,
      supportsNativeNotifications: hasNotifications,
      supportsSystemMetrics: false,
      supportsLocalRuntime: false,
      supportsDeepLinks: true,
    };
  }

  async getSystemMetrics(): Promise<MetricState> {
    // In web environment with supportsSystemMetrics=false, return truthful baseline without fake jitter
    return this.lastMetrics;
  }

  async openExternal(url: string): Promise<void> {
    if (typeof window !== 'undefined') {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  }

  async selectFile(_options?: FilePickerOptions): Promise<string | string[] | null> {
    // In web environment without native OS file picker access, returns null
    return null;
  }

  async showNotification(title: string, options?: PlatformNotificationOptions): Promise<void> {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      if (Notification.permission === 'granted') {
        new Notification(title, { body: options?.body, icon: options?.icon });
      } else if (Notification.permission !== 'denied') {
        const permission = await Notification.requestPermission();
        if (permission === 'granted') {
          new Notification(title, { body: options?.body, icon: options?.icon });
        }
      }
    }
  }

  async getSecureCredential(_key: string): Promise<string | null> {
    return null;
  }
}

export function createWebAdapter(): WebPlatformAdapter {
  return new WebPlatformAdapter();
}
