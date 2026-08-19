/**
 * Phase 13D — Logs Page.
 * Filterable runtime log stream; live entries arrive over /ws/v3/logs.
 */
import React, { useState } from 'react';
import { useLogs, useLogStream, useLogSources, LOG_LEVELS } from '../hooks/useLogs';
import type { LogRecord } from '@windagent/api-contracts';

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: '#6b7280',
  INFO: '#4ade80',
  WARNING: '#fbbf24',
  ERROR: '#f87171',
  CRITICAL: '#f43f5e',
};

export const LogsPage: React.FC = () => {
  const [level, setLevel] = useState('');
  const [source, setSource] = useState('');
  const [live, setLive] = useState<LogRecord[]>([]);
  const { data: logs = [], isLoading, error } = useLogs(level ? { level, source: source || undefined } : { source: source || undefined });
  const { data: sources = [] } = useLogSources();

  useLogStream((record) => {
    setLive((prev) => [record, ...prev].slice(0, 200));
  });

  const merged = [...live];
  const seen = new Set(merged.map((r) => `${r.timestamp}|${r.message}`));
  for (const r of logs) {
    const key = `${r.timestamp}|${r.message}`;
    if (!seen.has(key)) {
      merged.push(r);
      seen.add(key);
    }
  }

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '1600px', margin: '0 auto', fontFamily: 'var(--font-sans, sans-serif)' }}>
      <div>
        <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>Runtime Logs</h2>
        <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>
          Structured runtime records with correlation / trace ids. Live stream over WebSocket.
        </p>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        <select value={level} onChange={(e) => setLevel(e.target.value)} style={selectStyle()}>
          <option value="">all levels</option>
          {LOG_LEVELS.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
        <select value={source} onChange={(e) => setSource(e.target.value)} style={selectStyle()}>
          <option value="">all sources</option>
          {sources.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)' }}>
          {merged.length} records{live.length > 0 ? ` · ${live.length} live` : ''}
        </span>
      </div>

      {isLoading && <div style={{ color: 'var(--text-muted, #9ca3af)' }}>Loading logs…</div>}
      {error && <div style={{ color: '#f87171', fontSize: '0.85rem' }}>{(error as Error).message}</div>}

      {/* Log stream */}
      <div
        style={{
          borderRadius: '10px',
          border: '1px solid var(--border-color, #1f2937)',
          backgroundColor: '#0b1220',
          padding: '12px',
          maxHeight: '600px',
          overflowY: 'auto',
          fontFamily: 'monospace',
          fontSize: '0.74rem',
        }}
      >
        {merged.length === 0 && !isLoading && (
          <div style={{ color: 'var(--text-muted, #9ca3af)' }}>No log records yet — runtime activity will appear here.</div>
        )}
        {merged.map((r, i) => {
          const timeStr = r.timestamp ? String(r.timestamp).slice(11, 23) : '--:--:--';
          return (
            <div key={i} style={{ display: 'flex', gap: '10px', padding: '3px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
              <span style={{ color: '#4b5563', whiteSpace: 'nowrap' }}>{timeStr}</span>
              <span style={{ color: LEVEL_COLORS[r.level] ?? '#6b7280', width: '70px', fontWeight: 700 }}>{r.level || 'INFO'}</span>
              <span style={{ color: '#93c5fd', width: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.source || 'system'}</span>
              <span style={{ color: '#e5e7eb', flex: 1 }}>{r.message || ''}</span>
              {r.correlation_id && <span style={{ color: '#8b5cf6', whiteSpace: 'nowrap' }}>{r.correlation_id}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
};

function selectStyle(): React.CSSProperties {
  return {
    padding: '7px 10px',
    borderRadius: '6px',
    border: '1px solid var(--border-color, #1f2937)',
    backgroundColor: 'var(--bg-panel, #111827)',
    color: 'var(--text-primary, #f9fafb)',
    fontSize: '0.8rem',
  };
}