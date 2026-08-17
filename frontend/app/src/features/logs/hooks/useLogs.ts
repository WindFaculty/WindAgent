/**
 * Phase 13D — Logs Hooks.
 * REST list + /ws/v3/logs live stream. Records are real runtime log entries.
 */
import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import type { LogQueryParams, LogRecord } from '@windagent/api-contracts';

export const logsKeys = {
  all: ['v3', 'logs'] as const,
  list: (filters: LogQueryParams) => [...logsKeys.all, 'list', filters] as const,
  sources: () => [...logsKeys.all, 'sources'] as const,
};

export const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const;

function wsOrigin(): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8765';
  return origin.replace(/^http/, 'ws');
}

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
  const onRecordRef = useRef(onRecord);
  onRecordRef.current = onRecord;

  useEffect(() => {
    const ws = new WebSocket(wsOrigin() + '/ws/v3/logs');

    ws.onmessage = (msg) => {
      try {
        const record = JSON.parse(msg.data) as LogRecord;
        onRecordRef.current(record);
        queryClient.invalidateQueries({ queryKey: logsKeys.all });
      } catch {
        // ignore malformed ws frames
      }
    };

    return () => ws.close();
  }, [queryClient]);
}