/**
 * QueryProvider & useQuery / useMutation hooks.
 */

import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { QueryClient, type QueryObserverOptions, type QueryState } from './queryClient';

const QueryContext = createContext<QueryClient | null>(null);

export interface QueryProviderProps {
  client: QueryClient;
  children: React.ReactNode;
}

export const QueryProvider: React.FC<QueryProviderProps> = ({ client, children }) => {
  return <QueryContext.Provider value={client}>{children}</QueryContext.Provider>;
};

export function useQueryClient(): QueryClient {
  const client = useContext(QueryContext);
  if (!client) {
    throw new Error('useQueryClient must be used within a QueryProvider');
  }
  return client;
}

export function useQuery<TData = unknown, TError = Error>(
  options: QueryObserverOptions<TData>
): QueryState<TData, TError> & { refetch: () => Promise<TData> } {
  const client = useQueryClient();
  const enabled = options.enabled ?? true;

  const [state, setState] = useState<QueryState<TData, TError>>(() => {
    const existing = client.getQueryState<TData>(options.queryKey);
    if (existing) return existing as QueryState<TData, TError>;
    return {
      data: undefined,
      error: null,
      isLoading: enabled,
      isFetching: enabled,
      isSuccess: false,
      isError: false,
      updatedAt: 0,
    };
  });

  const refetch = useCallback(() => {
    return client.fetchQuery<TData>({ ...options, staleTimeMs: 0 });
  }, [client, options]);

  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
    const unsubscribe = client.subscribe(options.queryKey, (nextState) => {
      setState(nextState as QueryState<TData, TError>);
    });

    if (enabled) {
      client.fetchQuery<TData>(optionsRef.current).catch(() => {});
    }

    return () => {
      unsubscribe();
    };
  }, [client, JSON.stringify(options.queryKey), enabled]);

  return { ...state, refetch };
}

export interface UseMutationOptions<TData = unknown, TVariables = void, TError = Error> {
  mutationFn: (variables: TVariables) => Promise<TData>;
  onSuccess?: (data: TData, variables: TVariables) => void | Promise<void>;
  onError?: (error: TError, variables: TVariables) => void | Promise<void>;
}

export function useMutation<TData = unknown, TVariables = void, TError = Error>(
  options: UseMutationOptions<TData, TVariables, TError>
) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<TError | null>(null);
  const [data, setData] = useState<TData | undefined>(undefined);

  const mutateAsync = useCallback(
    async (variables: TVariables): Promise<TData> => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await options.mutationFn(variables);
        setData(result);
        setIsLoading(false);
        if (options.onSuccess) {
          await options.onSuccess(result, variables);
        }
        return result;
      } catch (err) {
        setIsLoading(false);
        setError(err as TError);
        if (options.onError) {
          await options.onError(err as TError, variables);
        }
        throw err;
      }
    },
    [options]
  );

  return {
    mutateAsync,
    isLoading,
    error,
    data,
  };
}
