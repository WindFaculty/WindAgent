/**
 * Phase 13A — Browser Runtime Console Hooks.
 * Real /api/v3/browser sessions + @windagent/realtime stream. Zero mock data.
 */
import { useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import { useRealtimeClient } from '../../../realtime/RealtimeProvider';
import type { BrowserActionResponse, BrowserSessionResource } from '@windagent/api-contracts';

export const browserKeys = {
  all: ['v3', 'browser'] as const,
  sessions: () => [...browserKeys.all, 'sessions'] as const,
  session: (id: string) => [...browserKeys.all, 'session', id] as const,
};

export function useBrowserSessions() {
  const client = useApiClient();
  return useQuery<BrowserSessionResource[]>({
    queryKey: browserKeys.sessions(),
    queryFn: () => client.browser.listSessions(),
    refetchInterval: 10_000,
  });
}

export type BrowserActionKind =
  | 'create'
  | 'navigate'
  | 'click'
  | 'type'
  | 'scroll'
  | 'extract'
  | 'close';

export function useBrowserActions() {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: browserKeys.sessions() });
  };

  return useMutation({
    mutationFn: async (args: { kind: BrowserActionKind; sessionId?: string; [k: string]: unknown }) => {
      const { kind, sessionId, url, x, y, selector, text, direction, pixels } = args as {
        kind: BrowserActionKind;
        sessionId?: string;
        url?: string;
        x?: number;
        y?: number;
        selector?: string;
        text?: string;
        direction?: 'up' | 'down';
        pixels?: number;
      };
      switch (kind) {
        case 'create':
          return client.browser.createSession();
        case 'navigate':
          return client.browser.navigate(sessionId!, url!);
        case 'click':
          return client.browser.click(sessionId!, x!, y!);
        case 'type':
          return client.browser.typeText(sessionId!, selector!, text!);
        case 'scroll':
          return client.browser.scroll(sessionId!, direction, pixels);
        case 'extract':
          return client.browser.extract(sessionId!);
        case 'close':
          await client.browser.close(sessionId!);
          return null;
        default:
          throw new Error(`Unknown browser action: ${kind}`);
      }
    },
    onSuccess: invalidate,
  });
}

export function useBrowserRealtime(onEvent?: (event: string, payload: BrowserSessionResource | BrowserActionResponse) => void) {
  const queryClient = useQueryClient();
  const realtime = useRealtimeClient();
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    const unsubscribe = realtime.subscribe(
      { aggregateType: 'browser' },
      (envelope) => {
        queryClient.invalidateQueries({ queryKey: browserKeys.sessions() });
        const eventType = envelope.event_type || (envelope.payload as any)?.event || 'browser.updated';
        if (onEventRef.current) {
          onEventRef.current(String(eventType), (envelope.payload || envelope) as any);
        }
      }
    );

    return () => {
      unsubscribe();
    };
  }, [realtime, queryClient]);
}