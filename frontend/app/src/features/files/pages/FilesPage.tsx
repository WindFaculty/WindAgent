/**
 * Phase 13B — Workspace Files Page.
 * Server-side sandbox enforced; frontend only sends workspace-relative paths.
 */
import React, { useState } from 'react';
import { useFiles, useCreateFile, useDeleteFile } from '../hooks/useFiles';
import { useApiClient } from '../../../shared/hooks/useApiClient';

export const FilesPage: React.FC = () => {
  const { data: files = [], isLoading, error } = useFiles();
  const create = useCreateFile();
  const remove = useDeleteFile();
  const client = useApiClient();

  const [path, setPath] = useState('notes/idea.md');
  const [content, setContent] = useState('');

  const handleCreate = () => {
    if (!path.trim()) return;
    create.mutate({ path: path.trim(), name: path.trim().split('/').pop() ?? path.trim(), content });
    setContent('');
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '1400px', margin: '0 auto', fontFamily: 'var(--font-sans, sans-serif)' }}>
      <div>
        <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>Workspace Files</h2>
        <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>
          Workspace-scoped file abstraction. Absolute host paths rejected server-side.
        </p>
      </div>

      {/* Create form */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'stretch' }}>
        <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="workspace-relative path (e.g. notes/idea.md)" style={inputStyle()} />
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="file content"
          rows={1}
          style={{ ...inputStyle(), resize: 'vertical', minWidth: '280px' }}
        />
        <button onClick={handleCreate} disabled={create.isPending || !path.trim()} style={buttonStyle('#3b82f6', '#fff')}>
          {create.isPending ? 'Creating…' : 'Create'}
        </button>
      </div>
      {create.isError && <div style={{ color: '#f87171', fontSize: '0.8rem' }}>{(create.error as Error).message}</div>}

      {/* File table */}
      <div style={{ borderRadius: '10px', border: '1px solid var(--border-color, #1f2937)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-panel, #111827)', color: 'var(--text-muted, #9ca3af)', textAlign: 'left' }}>
              <th style={thStyle}>Name</th>
              <th style={thStyle}>Path</th>
              <th style={thStyle}>Type</th>
              <th style={thStyle}>Size</th>
              <th style={thStyle}>Modified</th>
              <th style={thStyle}></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} style={{ padding: '16px', color: 'var(--text-muted, #9ca3af)' }}>Loading workspace files…</td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={6} style={{ padding: '16px', color: '#f87171' }}>{(error as Error).message}</td>
              </tr>
            )}
            {!isLoading && !error && files.length === 0 && (
              <tr>
                <td colSpan={6} style={{ padding: '16px', color: 'var(--text-muted, #9ca3af)' }}>No workspace files yet.</td>
              </tr>
            )}
            {files.map((f) => (
              <tr key={f.id} style={{ borderTop: '1px solid var(--border-color, #1f2937)' }}>
                <td style={tdStyle}><strong style={{ color: 'var(--text-primary, #f9fafb)' }}>{f.name}</strong></td>
                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: '0.75rem' }}>{f.path}</td>
                <td style={tdStyle}>{f.media_type}</td>
                <td style={tdStyle}>{formatSize(f.size)}</td>
                <td style={tdStyle}>{new Date(Number(f.modified_at) * 1000).toLocaleString()}</td>
                <td style={{ ...tdStyle, textAlign: 'right' }}>
                  <a href={client.files.downloadUrl(f.id)} download={f.name} style={{ color: '#60a5fa', marginRight: '12px', fontSize: '0.75rem' }}>
                    download
                  </a>
                  <button onClick={() => remove.mutate(f.id)} disabled={remove.isPending} style={{ background: 'none', border: 'none', color: '#f87171', fontSize: '0.75rem', cursor: 'pointer' }}>
                    delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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

const thStyle: React.CSSProperties = { padding: '10px 12px', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.04em' };
const tdStyle: React.CSSProperties = { padding: '10px 12px', color: 'var(--text-secondary, #c2c6d6)' };