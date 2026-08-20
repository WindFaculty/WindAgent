/**
 * Phase 13D — Logs Hooks.
 * REST list + @windagent/realtime stream. Records are real runtime log entries.
 */
import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import { useRealtimeClient } from '../../../realtime/RealtimeProvider';
import type { LogQueryParams, LogRecord } from '@windagent/api-contracts';

export const logsKeys = {
  all: ['v3', 'logs'] as const,
  list: (filters: LogQueryParams) => [...logsKeys.all, 'list', filters] as const,
  sources: () => [...logsKeys.all, 'sources'] as const,
};

export const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const;

export function useLogs(filters: LogQueryParams = {}) {
  const client = useApiClient();
  return useQuery<LogRecord[]>({
    queryKey: logsKeys.list(filters),
    queryFn: () => client.logs.list(filters),
    refetchInterval: 10_000,
  });
}

export function useLogSources() {
  const client = useApiClient();
  return useQuery<string[]>({
    queryKey: logsKeys.sources(),
    queryFn: () => client.logs.sources(),
  });
}

export function useLogStream(onRecord: (record: LogRecord) => void) {
  const queryClient = useQueryClient();
  const realtime = useRealtimeClient();
  const onRecordRef = useRef(onRecord);
  onRecordRef.current = onRecord;

  useEffect(() => {
    const unsubscribe = realtime.subscribe<LogRecord>(
      { aggregateType: 'log' },
      (envelope) => {
        if (envelope?.payload) {
          onRecordRef.current(envelope.payload as LogRecord);
          queryClient.invalidateQueries({ queryKey: logsKeys.all });
        }
      }
    );

    return () => {
      unsubscribe();
    };
  }, [realtime, queryClient]);
}