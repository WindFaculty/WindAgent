/**
 * RealtimeProvider & useRealtimeClient hook.
 */

import React, { createContext, useContext, useEffect, useMemo } from 'react';
import { createRealtimeClient, RealtimeClient, type RealtimeOptions } from '@windagent/realtime';

const RealtimeContext = createContext<RealtimeClient | null>(null);

export interface RealtimeProviderProps {
  client?: RealtimeClient;
  options?: Partial<RealtimeOptions>;
  children: React.ReactNode;
}

export const RealtimeProvider: React.FC<RealtimeProviderProps> = ({ client, options, children }) => {
  const rtClient = useMemo(() => {
    if (client) return client;
    const defaultWsUrl =
      typeof window !== 'undefined'
        ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`
        : 'ws://127.0.0.1:8765/ws';

    return createRealtimeClient({
      url: options?.url || defaultWsUrl,
      ...options,
    });
  }, [client, options]);

  useEffect(() => {
    rtClient.connect();
    return () => {
      rtClient.disconnect();
    };
  }, [rtClient]);

  return <RealtimeContext.Provider value={rtClient}>{children}</RealtimeContext.Provider>;
};

export function useRealtimeClient(): RealtimeClient {
  const client = useContext(RealtimeContext);
  if (!client) {
    throw new Error('useRealtimeClient must be used within a RealtimeProvider');
  }
  return client;
}
