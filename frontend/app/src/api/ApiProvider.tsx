/**
 * ApiProvider & useApiClient hook.
 */

import React, { createContext, useContext, useMemo } from 'react';
import { createApiClient, WindAgentClient, type TransportOptions } from '@windagent/api-client';

const ApiContext = createContext<WindAgentClient | null>(null);

/**
 * Same resolution rule the provider uses for its transport — exported so
 * non-React modules (live-director executor, samplers) target the same API.
 */
export function defaultApiBaseUrl(): string {
  return typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8765';
}

export interface ApiProviderProps {
  client?: WindAgentClient;
  options?: Partial<TransportOptions>;
  children: React.ReactNode;
}

export const ApiProvider: React.FC<ApiProviderProps> = ({ client, options, children }) => {
  const apiClient = useMemo(() => {
    if (client) return client;
    const baseUrl = options?.baseUrl || defaultApiBaseUrl();
    return createApiClient({
      baseUrl,
      ...options,
    });
  }, [client, options]);

  return <ApiContext.Provider value={apiClient}>{children}</ApiContext.Provider>;
};

export function useApiClient(): WindAgentClient {
  const client = useContext(ApiContext);
  if (!client) {
    throw new Error('useApiClient must be used within an ApiProvider');
  }
  return client;
}
