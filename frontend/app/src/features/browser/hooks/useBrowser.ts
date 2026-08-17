/**
 * Phase 13A — Browser Runtime Console Hooks.
 * Real /api/v3/browser sessions + /ws/v3/browser realtime. Zero mock data.
 */
import { useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import type { BrowserActionResponse, BrowserSessionResource } from '@windagent/api-contracts';

export const browserKeys = {
  all: ['v3', 'browser'] as const,
  sessions: () => [...browserKeys.all, 'sessions'] as const,
  session: (id: string) => [...browserKeys.all, 'session', id] as const,
};

function wsOrigin(): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8765';
  return origin.replace(/^http/, 'ws');
}

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
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    const ws = new WebSocket(wsOrigin() + '/ws/v3/browser');

    ws.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data);
        queryClient.invalidateQueries({ queryKey: browserKeys.sessions() });
        if (evt?.event && onEventRef.current) {
          onEventRef.current(String(evt.event), evt);
        }
      } catch {
        // ignore malformed ws frames
      }
    };

    return () => ws.close();
  }, [queryClient]);
}