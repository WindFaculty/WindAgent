/**
 * Realtime subscription hook for an episode workspace via @windagent/realtime.
 */

import { useEffect, useState } from 'react';
import { useQueryClient } from '../../../query';
import { useRealtimeClient } from '../../../realtime/RealtimeProvider';
import { EPISODE_DETAIL_QUERY_KEY } from './useEpisode';
import { EPISODE_ARTIFACTS_QUERY_KEY, EPISODE_RUNS_QUERY_KEY } from './useEpisodeArtifacts';
import type { EpisodeResource } from '@windagent/api-contracts';

export function useEpisodeRealtime(episodeId?: string) {
  const queryClient = useQueryClient();
  const realtime = useRealtimeClient();
  const [isConnected, setIsConnected] = useState(realtime.getState() === 'CONNECTED');
  const [lastEvent, setLastEvent] = useState<{ event: string; timestamp: string } | null>(null);

  useEffect(() => {
    const unsubState = realtime.onStateChange((state) => {
      setIsConnected(state === 'CONNECTED');
    });

    if (!episodeId) {
      return unsubState;
    }

    const unsubEvents = realtime.subscribe(
      { aggregateType: 'episode', aggregateId: episodeId },
      (envelope) => {
        const eventType = envelope.event_type || (envelope.payload as any)?.event;
        const timestamp = String(envelope.occurred_at || new Date().toISOString());
        setLastEvent({ event: eventType, timestamp });

        if (eventType === 'episode.updated' && envelope.payload) {
          queryClient.setQueryData<EpisodeResource>(
            EPISODE_DETAIL_QUERY_KEY(episodeId),
            envelope.payload as unknown as EpisodeResource
          );
        } else if (eventType === 'run.progress' || eventType === 'checkpoint.awaiting_approval') {
          queryClient.invalidateQueries({ queryKey: EPISODE_DETAIL_QUERY_KEY(episodeId) });
          queryClient.invalidateQueries({ queryKey: EPISODE_ARTIFACTS_QUERY_KEY(episodeId) });
          queryClient.invalidateQueries({ queryKey: EPISODE_RUNS_QUERY_KEY(episodeId) });
        }
      }
    );

    return () => {
      unsubState();
      unsubEvents();
    };
  }, [episodeId, realtime, queryClient]);

  return {
    isConnected,
    lastEvent,
  };
}
