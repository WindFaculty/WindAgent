/**
 * Frontend Bootstrap Engine (P4.2).
 */

import type { PlatformAdapter } from '../platform/platformAdapter';

export interface BootstrapConfig {
  platform: PlatformAdapter;
}

export function bootstrapFrontend(config: BootstrapConfig): void {
  // Global unhandled promise rejection handler
  if (typeof window !== 'undefined') {
    window.addEventListener('unhandledrejection', (event) => {
      console.error('[WindAgent Frontend] Unhandled Promise Rejection:', event.reason);
    });
  }

  console.info(`[WindAgent Frontend] Initialized platform: ${config.platform.kind}`);
}
