/**
 * Phase 13C — Memory Page.
 * Scoped memory records; retrieval via backend (no client embedding faking).
 */
import React, { useState } from 'react';
import { useMemoryRecords, useMemorySearch, useCreateMemory, MEMORY_SCOPES } from '../hooks/useMemory';
import type { MemoryScope } from '@windagent/api-contracts';

export const MemoryPage: React.FC = () => {
  const [scope, setScope] = useState<MemoryScope | undefined>(undefined);
  const [query, setQuery] = useState('');
  const { data: records = [], isLoading, error } = useMemoryRecords(scope);
  const search = useMemorySearch(query);
  const create = useCreateMemory();

  const [content, setContent] = useState('');
  const [newScope, setNewScope] = useState<MemoryScope>('global');

  const visible = query.trim() ? search.data ?? [] : records;

  const handleCreate = () => {
    if (!content.trim()) return;
    create.mutate({ scope: newScope, content: content.trim() });
    setContent('');
  };

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '1200px', margin: '0 auto', fontFamily: 'var(--font-sans, sans-serif)' }}>
      <div>
        <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>Memory</h2>
        <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>
          Scoped knowledge records retrieved from the runtime — not the database browser.
        </p>
      </div>

      {/* Search + create */}
      <div style={{ display: 'flex', gap: '8px' }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search memory records…"
          style={inputStyle()}
        />
        <select value={newScope} onChange={(e) => setNewScope(e.target.value as MemoryScope)} style={selectStyle()}>
          {MEMORY_SCOPES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <input value={content} onChange={(e) => setContent(e.target.value)} placeholder="new memory content" style={inputStyle()} />
        <button onClick={handleCreate} disabled={create.isPending || !content.trim()} style={buttonStyle('#3b82f6', '#fff')}>
          Save
        </button>
      </div>

      {/* Scope filter */}
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
        <button onClick={() => setScope(undefined)} style={chipStyle(scope === undefined)}>all</button>
        {MEMORY_SCOPES.map((s) => (
          <button key={s} onClick={() => setScope(s)} style={chipStyle(scope === s)}>{s}</button>
        ))}
      </div>

      {isLoading && <div style={{ color: 'var(--text-muted, #9ca3af)' }}>Loading memory records…</div>}
      {error && <div style={{ color: '#f87171', fontSize: '0.85rem' }}>{(error as Error).message}</div>}

      {/* Records */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {!isLoading && !error && visible.length === 0 && (
          <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--bg-panel, #111827)', border: '1px solid var(--border-color, #1f2937)', fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>
            No memory records in this scope.
          </div>
        )}
        {visible.map((rec) => (
          <div key={rec.id} style={{ padding: '12px 14px', borderRadius: '8px', backgroundColor: 'var(--bg-panel, #111827)', border: '1px solid var(--border-color, #1f2937)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
              <span style={{ fontSize: '0.7rem', fontWeight: 700, color: '#60a5fa', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                {rec.scope} · {rec.type}
              </span>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted, #9ca3af)' }}>
                {rec.embedding_state === 'INDEXED' ? 'indexed' : 'not embedded'}
              </span>
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-primary, #f9fafb)' }}>{rec.content}</div>
            {rec.owner && <div style={{ fontSize: '0.7rem', color: 'var(--text-muted, #9ca3af)', marginTop: '4px' }}>owner: {rec.owner}</div>}
          </div>
        ))}
      </div>
    </div>
  );
};

function buttonStyle(bg: string, fg: string): React.CSSProperties {
  return { backgroundColor: bg, color: fg, border: 'none', borderRadius: '6px', padding: '8px 14px', fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer' };
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

function selectStyle(): React.CSSProperties {
  return {
    padding: '8px 10px',
    borderRadius: '6px',
    border: '1px solid var(--border-color, #1f2937)',
    backgroundColor: 'var(--bg-panel, #111827)',
    color: 'var(--text-primary, #f9fafb)',
    fontSize: '0.8rem',
  };
}

function chipStyle(active: boolean): React.CSSProperties {
  return {
    padding: '5px 12px',
    borderRadius: '999px',
    border: `1px solid ${active ? '#3b82f6' : 'var(--border-color, #1f2937)'}`,
    backgroundColor: active ? 'rgba(59,130,246,0.15)' : 'transparent',
    color: active ? '#93c5fd' : 'var(--text-muted, #9ca3af)',
    fontSize: '0.75rem',
    cursor: 'pointer',
  };
}