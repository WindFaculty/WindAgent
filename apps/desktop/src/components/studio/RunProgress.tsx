/**
 * Run progress panel (Plan C4) — observes durable run status and events for
 * an episode's active run. Polling/event cursor authority lives in
 * StudioStore; this view only renders server-declared state and never
 * advances a stage locally.
 */

import { useEffect, useRef, useState } from 'react';
import type { StudioRunResource } from '@windagent/studio-contracts';
import type { RunEventsPage } from '@windagent/studio-client';
import type { StudioStore } from '@windagent/studio-state';

const STATUS_COLOR: Record<string, string> = {
  QUEUED: '#94a3b8',
  RUNNING: '#7dd3fc',
  WAITING_FOR_APPROVAL: '#fbbf24',
  RETRYING: '#fb923c',
  COMPLETED: '#4ade80',
  FAILED: '#fca5a5',
  CANCELLED: '#94a3b8',
};

const WAIT_LABEL: Record<string, string> = {
  APPROVAL_REQUIRED: 'Waiting for human approval at a checkpoint.',
  PROVIDER_UNAVAILABLE: 'Provider unavailable — run is fail-closed until service is restored.',
  DEPENDENCY_RETRY: 'Dependency retry in progress.',
  REVISION_REQUIRED: 'Revision required before the run can continue.',
};

const EVENT_LABEL: Record<string, string> = {
  'studio.series.created': 'Series created',
  'studio.episode.created': 'Episode created',
  'studio.revision.derived': 'Revision derived',
  'studio.artifact.created': 'Artifact created',
  'studio.idea.candidates_generated': 'Idea candidates generated',
  'studio.idea.selected': 'Idea selected',
  'studio.approval.requested': 'Approval requested',
  'studio.approval.recorded': 'Approval recorded',
  'studio.story.review_completed': 'Story review completed',
  'studio.story.revision_requested': 'Revision requested',
  'studio.screenplay.locked': 'Screenplay locked',
  'studio.episode.ready_for_production': 'Ready for production',
  'studio.run.failed': 'Run failed',
  'studio.run.cancelled': 'Run cancelled',
};

const MUTED = { color: '#94a3b8' } as const;

export function RunProgress({
  runId,
  store,
  onDurableChange,
  intervalMs = 2_000,
}: {
  runId: string;
  store: StudioStore;
  /** Called whenever new run events arrive or the run reaches a terminal status. */
  onDurableChange: () => void;
  /** Poll interval; tests may shrink it. */
  intervalMs?: number;
}) {
  const [run, setRun] = useState<StudioRunResource | null>(null);
  const [events, setEvents] = useState<Array<{ sequence: number; event_type: string }>>([]);
  const seenSequences = useRef<Set<number>>(new Set());
  const durableRef = useRef(onDurableChange);
  durableRef.current = onDurableChange;

  useEffect(() => {
    const stop = store.pollRun(runId, {
      intervalMs,
      onStatus: (next) => setRun(next),
      onEvent: (pageEvents: RunEventsPage['events']) => {
        const fresh = pageEvents.filter((e) => !seenSequences.current.has(e.sequence));
        for (const e of fresh) seenSequences.current.add(e.sequence);
        if (fresh.length > 0) {
          setEvents((prev) => [...prev, ...fresh].slice(-50));
          durableRef.current();
        }
      },
    });
    return stop;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, store]);

  useEffect(() => {
    if (run && ['COMPLETED', 'FAILED', 'CANCELLED'].includes(run.status)) {
      durableRef.current();
    }
  }, [run]);

  if (!run) {
    return (
      <section aria-label="Run progress" style={{ margin: '8px 0' }}>
        <span style={MUTED}>Run {runId.slice(0, 12)}… loading status…</span>
      </section>
    );
  }

  const wait = run.wait_reason ? WAIT_LABEL[run.wait_reason] : null;
  return (
    <section aria-label="Run progress" style={{ border: '1px solid #334155', borderRadius: 8, padding: 10, margin: '8px 0' }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ color: STATUS_COLOR[run.status] ?? '#e2e8f0', fontWeight: 600 }}>{run.status}</span>
        <span style={MUTED}>{run.command_type}</span>
        {run.wait_reason && <span style={{ color: '#fbbf24' }}>wait: {run.wait_reason}</span>}
      </div>
      {wait && <div style={{ ...MUTED, marginTop: 4 }}>{wait}</div>}
      {events.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: '8px 0 0', fontSize: 13 }}>
          {events.map((e) => (
            <li key={e.sequence} style={{ marginBottom: 2 }}>
              <span style={MUTED}>#{e.sequence}</span>{' '}
              {EVENT_LABEL[e.event_type] ?? e.event_type}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
