/**
 * Realtime WebSocket connection hook for an episode workspace.
 */

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '../../../query';
import { EPISODE_DETAIL_QUERY_KEY } from './useEpisode';
import { EPISODE_ARTIFACTS_QUERY_KEY, EPISODE_RUNS_QUERY_KEY } from './useEpisodeArtifacts';
import type { EpisodeResource } from '@windagent/api-contracts';

export function useEpisodeRealtime(episodeId?: string) {
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<{ event: string; timestamp: string } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!episodeId) return;

    let unmounted = false;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || '127.0.0.1:8000';
    const url = `${protocol}//${host}/ws/v3/episodes/${encodeURIComponent(episodeId)}`;

    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!unmounted) setIsConnected(true);
      };

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (!unmounted) {
            setLastEvent({ event: data.event, timestamp: data.timestamp });

            if (data.event === 'episode.updated' && data.payload) {
              queryClient.setQueryData<EpisodeResource>(
                EPISODE_DETAIL_QUERY_KEY(episodeId),
                data.payload
              );
            } else if (data.event === 'run.progress' || data.event === 'checkpoint.awaiting_approval') {
              queryClient.invalidateQueries({ queryKey: EPISODE_DETAIL_QUERY_KEY(episodeId) });
              queryClient.invalidateQueries({ queryKey: EPISODE_ARTIFACTS_QUERY_KEY(episodeId) });
              queryClient.invalidateQueries({ queryKey: EPISODE_RUNS_QUERY_KEY(episodeId) });
            }
          }
        } catch {
          // ignore malformed ws messages
        }
      };

      ws.onclose = () => {
        if (!unmounted) setIsConnected(false);
      };

      ws.onerror = () => {
        if (!unmounted) setIsConnected(false);
      };
    } catch {
      setIsConnected(false);
    }

    return () => {
      unmounted = true;
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [episodeId, queryClient]);

  return {
    isConnected,
    lastEvent,
  };
}
