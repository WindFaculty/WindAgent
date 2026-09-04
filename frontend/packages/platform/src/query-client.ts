import { QueryClient } from "@tanstack/react-query";

/**
 * Server state lives in TanStack Query.  This factory is the single place
 * where cache defaults are configured; feature code must never construct its
 * own QueryClient or a custom polling client (old-project anti-pattern).
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}
