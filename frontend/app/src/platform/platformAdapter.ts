/**
 * PlatformAdapter — Abstraction layer for desktop (Tauri) and web environments.
 */

import type { MetricState } from '@windagent/studio-shell';

export interface PlatformCapabilities {
  readonly supportsNativeFilePicker: boolean;
  readonly supportsNativeNotifications: boolean;
  readonly supportsSystemMetrics: boolean;
  readonly supportsLocalRuntime: boolean;
  readonly supportsDeepLinks: boolean;
}

export interface FilePickerOptions {
  filter?: string;
  multiple?: boolean;
  directory?: boolean;
}

export interface PlatformNotificationOptions {
  body?: string;
  icon?: string;
}

export interface PlatformAdapter {
  readonly kind: 'web' | 'tauri';
  readonly platform: 'web' | 'desktop';
  getSystemCapabilities(): Promise<PlatformCapabilities>;
  getSystemMetrics(): Promise<MetricState>;
  getNativeSystemMetrics?(): Promise<MetricState>;
  openExternal(url: string): Promise<void>;
  selectFile?(options?: FilePickerOptions): Promise<string | string[] | null>;
  showNotification?(title: string, options?: PlatformNotificationOptions): Promise<void>;
  getSecureCredential?(key: string): Promise<string | null>;
}

