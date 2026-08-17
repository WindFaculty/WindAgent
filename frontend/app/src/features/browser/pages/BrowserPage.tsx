/**
 * Phase 13A — Browser Runtime Console Page.
 * Lists real browser runtime sessions; screenshot is a server artifact.
 */
import React, { useState } from 'react';
import { useBrowserSessions, useBrowserActions, useBrowserRealtime } from '../hooks/useBrowser';
import { useApiClient } from '../../../shared/hooks/useApiClient';

export const BrowserPage: React.FC = () => {
  const { data: sessions = [], isLoading, error } = useBrowserSessions();
  const actions = useBrowserActions();
  const client = useApiClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [address, setAddress] = useState('about:blank');
  const [events, setEvents] = useState<string[]>([]);

  const selected = sessions.find((s) => s.id === selectedId) ?? sessions[0] ?? null;

  useBrowserRealtime((event, payload) => {
    setEvents((prev) => [`${event} ${(payload as { url?: string })?.url ?? ''}`.trim(), ...prev].slice(0, 50));
  });

  const run = (kind: Parameters<typeof actions.mutate>[0]['kind'], extra?: Record<string, unknown>) => {
    if (!selected && kind !== 'create') return;
    actions.mutate({ kind, sessionId: selected?.id, ...extra } as never);
  };

  const screenshotRef = selected ? client.browser.screenshotUrl(selected.id) : null;

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '1600px', margin: '0 auto', fontFamily: 'var(--font-sans, sans-serif)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>Browser Runtime Console</h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>
            Live agent browser sessions. Screenshots and actions come from the real browser runtime.
          </p>
        </div>
        <button
          onClick={() => run('create')}
          disabled={actions.isPending}
          style={buttonStyle('#3b82f6', '#fff')}
        >
          {actions.isPending ? 'Working…' : 'New Session'}
        </button>
      </div>

      {isLoading && <div style={{ color: 'var(--text-muted, #9ca3af)' }}>Loading sessions…</div>}
      {error && <div style={{ color: '#f87171', fontSize: '0.85rem' }}>{(error as Error).message}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '16px', alignItems: 'start' }}>
        {/* Session list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {sessions.length === 0 && !isLoading && (
            <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--bg-panel, #111827)', border: '1px solid var(--border-color, #1f2937)', fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>
              No live sessions. Start one to launch the browser runtime.
            </div>
          )}
          {sessions.map((s) => (
            <div
              key={s.id}
              onClick={() => {
                setSelectedId(s.id);
                setAddress(s.url);
              }}
              style={{
                padding: '10px 12px',
                borderRadius: '8px',
                cursor: 'pointer',
                backgroundColor: selected?.id === s.id ? 'var(--bg-panel-light, #171f33)' : 'var(--bg-panel, #111827)',
                border: `1px solid ${selected?.id === s.id ? '#3b82f6' : 'var(--border-color, #1f2937)'}`,
              }}
            >
              <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.title}</div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted, #9ca3af)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.url}</div>
              <div style={{ fontSize: '0.7rem', color: s.error ? '#f87171' : s.loading ? '#fbbf24' : '#4ade80' }}>
                {s.error ? 'error' : s.loading ? 'loading' : 'idle'} · {s.screenshot_url ? '📸' : ''} {s.extracted_chars} chars
              </div>
            </div>
          ))}
        </div>

        {/* Viewport + controls */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && run('navigate', { url: address })}
              placeholder="Enter URL…"
              style={inputStyle()}
            />
            <button onClick={() => run('navigate', { url: address })} disabled={!selected || actions.isPending} style={buttonStyle('#3b82f6', '#fff')}>
              Go
            </button>
            <button onClick={() => run('extract')} disabled={!selected || actions.isPending} style={buttonStyle('#374151', '#e5e7eb')}>
              Extract
            </button>
            <button onClick={() => run('close')} disabled={!selected || actions.isPending} style={buttonStyle('#b91c1c', '#fff')}>
              Close
            </button>
          </div>

          {/* Screenshot viewport */}
          <div
            style={{
              border: '1px solid var(--border-color, #1f2937)',
              borderRadius: '10px',
              overflow: 'hidden',
              backgroundColor: '#0b1220',
              minHeight: '360px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {screenshotRef ? (
              <img
                src={screenshotRef}
                alt={`Browser screenshot — ${selected?.url ?? ''}`}
                style={{ width: '100%', maxHeight: '460px', objectFit: 'contain' }}
              />
            ) : (
              <span style={{ color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
                {selected ? 'No screenshot artifact yet — navigate to capture one.' : 'Select or create a session.'}
              </span>
            )}
          </div>

          {/* Action timeline */}
          <div
            style={{
              borderRadius: '8px',
              backgroundColor: 'var(--bg-panel, #111827)',
              border: '1px solid var(--border-color, #1f2937)',
              padding: '12px',
              maxHeight: '180px',
              overflowY: 'auto',
              fontFamily: 'monospace',
              fontSize: '0.75rem',
              color: 'var(--text-muted, #9ca3af)',
            }}
          >
            {events.length === 0 && <div>No runtime browser events yet.</div>}
            {events.map((e, i) => (
              <div key={i}>{e}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

function buttonStyle(bg: string, fg: string): React.CSSProperties {
  return {
    backgroundColor: bg,
    color: fg,
    border: 'none',
    borderRadius: '6px',
    padding: '7px 14px',
    fontSize: '0.8rem',
    fontWeight: 600,
    cursor: 'pointer',
  };
}

function inputStyle(): React.CSSProperties {
  return {
    flex: 1,
    padding: '8px 10px',
    borderRadius: '6px',
    border: '1px solid var(--border-color, #1f2937)',
    backgroundColor: 'var(--bg-panel, #111827)',
    color: 'var(--text-primary, #f9fafb)',
    fontSize: '0.8rem',
  };
}