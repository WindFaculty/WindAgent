/**
 * PlatformProvider & usePlatform hook.
 */

import React, { createContext, useContext } from 'react';
import type { PlatformAdapter } from './platformAdapter';
import { WebPlatformAdapter } from './webAdapter';

const PlatformContext = createContext<PlatformAdapter>(new WebPlatformAdapter());

export interface PlatformProviderProps {
  adapter: PlatformAdapter;
  children: React.ReactNode;
}

export const PlatformProvider: React.FC<PlatformProviderProps> = ({ adapter, children }) => {
  return <PlatformContext.Provider value={adapter}>{children}</PlatformContext.Provider>;
};

export function usePlatform(): PlatformAdapter {
  return useContext(PlatformContext);
}
