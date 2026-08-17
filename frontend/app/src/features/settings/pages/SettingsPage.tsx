/**
 * Phase 13E — Settings Page.
 * Renders the server-owned settings schema. Secrets show configured-status only.
 */
import React, { useState } from 'react';
import { useSettings, usePatchSettings, groupSettings, isSecretConfigured } from '../hooks/useSettings';
import type { SettingSchemaItem } from '@windagent/api-contracts';

export const SettingsPage: React.FC = () => {
  const { data, isLoading, error } = useSettings();
  const patch = usePatchSettings();
  const [secretValues, setSecretValues] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState('');

  const groups = data ? groupSettings(data.settings) : {};

  const update = (item: SettingSchemaItem, value: unknown) => {
    setSaved('');
    patch.mutate({ [item.key]: value });
  };

  const updateSecret = (item: SettingSchemaItem) => {
    const raw = secretValues[item.key] ?? '';
    setSaved('');
    patch.mutate({ [item.key]: raw.trim() || null });
    setSecretValues((prev) => ({ ...prev, [item.key]: '' }));
  };

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '1100px', margin: '0 auto', fontFamily: 'var(--font-sans, sans-serif)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>Settings</h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>
            Rendered from the server settings schema. Secrets never leave the backend.
          </p>
        </div>
        {patch.isPending && <span style={{ fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)' }}>Saving…</span>}
        {saved && <span style={{ fontSize: '0.8rem', color: '#4ade80' }}>{saved}</span>}
      </div>

      {isLoading && <div style={{ color: 'var(--text-muted, #9ca3af)' }}>Loading settings…</div>}
      {error && <div style={{ color: '#f87171', fontSize: '0.85rem' }}>{(error as Error).message}</div>}
      {patch.isError && <div style={{ color: '#f87171', fontSize: '0.85rem' }}>{(patch.error as Error).message}</div>}

      {Object.entries(groups).map(([group, items]) => (
        <section key={group} style={{ borderRadius: '10px', border: '1px solid var(--border-color, #1f2937)', backgroundColor: 'var(--bg-panel, #111827)', overflow: 'hidden' }}>
          <h3 style={{ margin: 0, padding: '12px 16px', fontSize: '0.8rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#60a5fa', backgroundColor: 'rgba(59,130,246,0.08)' }}>
            {group}
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {items.map((item) => (
              <div key={item.key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px', padding: '12px 16px', borderTop: '1px solid var(--border-color, #1f2937)' }}>
                <div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary, #f9fafb)', fontFamily: 'monospace' }}>{item.key}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)' }}>
                    {item.description}
                    {item.read_only && ' · read-only'}
                    {item.requires_restart && ' · requires restart'}
                  </div>
                </div>
                <div style={{ minWidth: '220px', display: 'flex', justifyContent: 'flex-end' }}>
                  {renderControl(item, secretValues, setSecretValues, update, updateSecret)}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
};

function renderControl(
  item: SettingSchemaItem,
  secretValues: Record<string, string>,
  setSecretValues: React.Dispatch<React.SetStateAction<Record<string, string>>>,
  update: (item: SettingSchemaItem, value: unknown) => void,
  updateSecret: (item: SettingSchemaItem) => void
) {
  if (item.secret) {
    const configured = isSecretConfigured(item);
    return (
      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
        <span style={{ fontSize: '0.75rem', color: configured ? '#4ade80' : '#f87171', fontWeight: 700 }}>
          {configured ? 'configured' : 'not configured'}
        </span>
        <input
          type="password"
          placeholder="new value"
          value={secretValues[item.key] ?? ''}
          onChange={(e) => setSecretValues((prev) => ({ ...prev, [item.key]: e.target.value }))}
          style={inputStyle()}
        />
        <button onClick={() => updateSecret(item)} disabled={!secretValues[item.key] && !configured} style={buttonStyle('#3b82f6', '#fff')}>
          {configured ? 'Rotate' : 'Set'}
        </button>
      </div>
    );
  }

  if (item.read_only) {
    return <span style={{ fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)' }}>{String(item.value ?? '')}</span>;
  }

  switch (item.type) {
    case 'boolean':
      return (
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
          <input type="checkbox" checked={Boolean(item.value)} onChange={(e) => update(item, e.target.checked)} />
          <span style={{ fontSize: '0.8rem', color: 'var(--text-primary, #f9fafb)' }}>{item.value ? 'on' : 'off'}</span>
        </label>
      );
    case 'enum': {
      const options = item.enum ?? [];
      if (options.length <= 3) {
        return (
          <div style={{ display: 'flex', gap: '6px' }}>
            {options.map((opt) => (
              <button key={opt} onClick={() => update(item, opt)} style={chipStyle(item.value === opt)}>{opt}</button>
            ))}
          </div>
        );
      }
      return (
        <select value={String(item.value ?? '')} onChange={(e) => update(item, e.target.value)} style={selectStyle()}>
          {options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      );
    }
    case 'number':
      return (
        <input
          type="number"
          value={Number(item.value ?? 0)}
          min={item.min ?? undefined}
          max={item.max ?? undefined}
          onChange={(e) => update(item, Number(e.target.value))}
          style={inputStyle()}
        />
      );
    default:
      return <input value={String(item.value ?? '')} onChange={(e) => update(item, e.target.value)} style={inputStyle()} />;
  }
}

function buttonStyle(bg: string, fg: string): React.CSSProperties {
  return { backgroundColor: bg, color: fg, border: 'none', borderRadius: '6px', padding: '7px 12px', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer' };
}

function inputStyle(): React.CSSProperties {
  return {
    padding: '7px 10px',
    width: '160px',
    borderRadius: '6px',
    border: '1px solid var(--border-color, #1f2937)',
    backgroundColor: '#0b1220',
    color: 'var(--text-primary, #f9fafb)',
    fontSize: '0.8rem',
  };
}

function selectStyle(): React.CSSProperties {
  return {
    padding: '7px 10px',
    borderRadius: '6px',
    border: '1px solid var(--border-color, #1f2937)',
    backgroundColor: '#0b1220',
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