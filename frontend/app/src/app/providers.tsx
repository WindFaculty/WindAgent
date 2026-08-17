/**
 * Providers — Canonical Provider Hierarchy for WindAgent Frontend App (P4.7).
 */

import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GlobalErrorBoundary } from './errors/GlobalErrorBoundary';
import { PlatformProvider } from '../platform/PlatformProvider';
import type { PlatformAdapter } from '../platform/platformAdapter';
import { WebPlatformAdapter } from '../platform/webAdapter';
import { ApiProvider } from '../api/ApiProvider';
import { QueryProvider } from '../query/QueryProvider';
import { createQueryClient, type QueryClient as AppQueryClient } from '../query/queryClient';
import { RealtimeProvider } from '../realtime/RealtimeProvider';
import { RouterProvider } from './router';

export interface AppProvidersProps {
  platform?: PlatformAdapter;
  queryClient?: AppQueryClient;
  children: React.ReactNode;
}

export const AppProviders: React.FC<AppProvidersProps> = ({
  platform = new WebPlatformAdapter(),
  queryClient = createQueryClient(),
  children,
}) => {
  const tanstackQueryClient = React.useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 10_000,
            refetchOnWindowFocus: false,
          },
        },
      }),
    []
  );

  return (
    <GlobalErrorBoundary>
      <PlatformProvider adapter={platform}>
        <ApiProvider>
          <QueryClientProvider client={tanstackQueryClient}>
            <QueryProvider client={queryClient}>
              <RealtimeProvider>
                <RouterProvider>{children}</RouterProvider>
              </RealtimeProvider>
            </QueryProvider>
          </QueryClientProvider>
        </ApiProvider>
      </PlatformProvider>
    </GlobalErrorBoundary>
  );
};
