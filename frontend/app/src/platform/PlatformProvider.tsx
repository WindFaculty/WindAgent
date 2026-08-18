/**
 * PlatformProvider & Platform Hooks (Phase 14 Web/Desktop Convergence).
 */

import React, { createContext, useContext, useEffect, useState } from 'react';
import type { PlatformAdapter, PlatformCapabilities } from './platformAdapter';
import { WebPlatformAdapter } from './webAdapter';

const defaultWebAdapter = new WebPlatformAdapter();
const PlatformContext = createContext<PlatformAdapter>(defaultWebAdapter);

export interface PlatformProviderProps {
  adapter?: PlatformAdapter;
  children: React.ReactNode;
}

export const PlatformProvider: React.FC<PlatformProviderProps> = ({ adapter = defaultWebAdapter, children }) => {
  return <PlatformContext.Provider value={adapter}>{children}</PlatformContext.Provider>;
};

export function usePlatform(): PlatformAdapter {
  return useContext(PlatformContext);
}

const DEFAULT_CAPABILITIES: PlatformCapabilities = {
  supportsNativeFilePicker: false,
  supportsNativeNotifications: false,
  supportsSystemMetrics: false,
  supportsLocalRuntime: false,
  supportsDeepLinks: true,
};

export function usePlatformCapabilities(): PlatformCapabilities {
  const adapter = usePlatform();
  const [capabilities, setCapabilities] = useState<PlatformCapabilities>(DEFAULT_CAPABILITIES);

  useEffect(() => {
    let mounted = true;
    adapter.getSystemCapabilities().then((caps) => {
      if (mounted) {
        setCapabilities(caps);
      }
    });
    return () => {
      mounted = false;
    };
  }, [adapter]);

  return capabilities;
}
