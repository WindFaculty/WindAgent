/**
 * PlatformAdapter — Abstraction layer for desktop (Tauri) and web environments.
 */

import type { MetricState } from '@windagent/studio-shell';

export interface PlatformAdapter {
  readonly kind: 'web' | 'tauri';
  getSystemMetrics(): Promise<MetricState>;
  openExternal(url: string): Promise<void>;
  selectFile?(options?: { filter?: string; multiple?: boolean }): Promise<string | string[] | null>;
  getSecureCredential?(key: string): Promise<string | null>;
}
