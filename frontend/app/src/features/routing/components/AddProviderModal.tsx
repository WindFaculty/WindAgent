import React, { useEffect, useState } from 'react';
import { Plus, Server, X } from 'lucide-react';
import type { ProviderItem } from './ProviderRegistryTable';

interface AddProviderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (newProvider: ProviderItem, rawApiKey?: string) => void;
  existingIds?: string[];
}

const PRESETS: Record<string, { label: string; name: string; endpoint: string }> = {
  openrouter: { label: 'OpenRouter', name: 'OpenRouter', endpoint: 'https://openrouter.ai/api/v1' },
  gemini: { label: 'Google Gemini', name: 'Google AI Studio', endpoint: 'https://generativelanguage.googleapis.com' },
  anthropic: { label: 'Anthropic', name: 'Anthropic', endpoint: 'https://api.anthropic.com' },
  openai: { label: 'OpenAI', name: 'OpenAI', endpoint: 'https://api.openai.com/v1' },
  groq: { label: 'Groq', name: 'Groq', endpoint: 'https://api.groq.com/openai/v1' },
  ollama: { label: 'Ollama', name: 'Ollama Local', endpoint: 'http://localhost:11434' },
  custom: { label: 'Custom', name: '', endpoint: '' },
};

const fieldStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '9px 11px',
  borderRadius: '7px',
  backgroundColor: 'rgba(0, 0, 0, 0.4)',
  border: '1px solid rgba(66, 71, 84, 0.6)',
  color: '#f8fafc',
  fontSize: '0.8rem',
  outline: 'none',
};

export const AddProviderModal: React.FC<AddProviderModalProps> = ({
  isOpen,
  onClose,
  onAdd,
  existingIds = [],
}) => {
  const [providerType, setProviderType] = useState('custom');
  const [name, setName] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [formError, setFormError] = useState('');

  useEffect(() => {
    if (!isOpen) {
      setProviderType('custom');
      setName('');
      setEndpoint('');
      setApiKey('');
    }
    setFormError('');
  }, [isOpen]);

  if (!isOpen) return null;

  const selectPreset = (presetId: string) => {
    const preset = PRESETS[presetId];
    setProviderType(presetId);
    setName(preset.name);
    setEndpoint(preset.endpoint);
    setFormError('');
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    const trimmedEndpoint = endpoint.trim().replace(/\/+$/, '');
    if (!trimmedName || !trimmedEndpoint) {
      setFormError('Provider name and Base URL are required.');
      return;
    }
    try {
      const parsed = new URL(trimmedEndpoint);
      if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error('invalid protocol');
    } catch {
      setFormError('Base URL must be a valid http(s) URL.');
      return;
    }

    const id = trimmedName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || `provider-${Date.now()}`;
    if (existingIds.some((existing) => existing.toLowerCase() === id)) {
      setFormError(`Provider id "${id}" already exists. Choose a different name.`);
      return;
    }

    const provider: ProviderItem = {
      id,
      name: trimmedName,
      subName: providerType === 'custom' ? 'Custom Endpoint' : trimmedName,
      endpoint: trimmedEndpoint,
      credentialsStatus: apiKey.trim() ? 'warning' : 'offline',
      modelsCount: 0,
      ruleSet: '',
      status: 'warning',
      apiKeyMasked: '',
      timeoutSec: 0,
      maxRetries: 0,
      models: [],
      perModelRules: [],
      fallbackProvider: '',
      maxTokens: 0,
      streaming: false,
      enableCache: false,
    };

    onAdd(provider, apiKey.trim() || undefined);
  };

  return (
    <div
      role="presentation"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(8px)',
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-provider-title"
        onClick={(event) => event.stopPropagation()}
        style={{ width: '100%', maxWidth: '560px', backgroundColor: '#0f172a', borderRadius: '14px', border: '1px solid rgba(66, 71, 84, 0.6)', boxShadow: '0 20px 40px rgba(0,0,0,.6)', overflow: 'hidden' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid rgba(66,71,84,.4)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Server size={18} color="#60a5fa" />
            <h3 id="add-provider-title" style={{ margin: 0, color: '#f8fafc', fontSize: '1rem' }}>Add durable provider endpoint</h3>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} style={{ background: 'transparent', border: 0, color: '#94a3b8', cursor: 'pointer', padding: '4px' }}>
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '15px', padding: '20px' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '7px', color: '#94a3b8', fontSize: '0.74rem', fontWeight: 600 }}>Endpoint presets</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {Object.entries(PRESETS).map(([id, preset]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => selectPreset(id)}
                  style={{ padding: '5px 10px', borderRadius: '6px', fontSize: '0.73rem', fontWeight: 600, cursor: 'pointer', color: providerType === id ? '#60a5fa' : '#cbd5e1', backgroundColor: providerType === id ? 'rgba(59,130,246,.25)' : 'rgba(255,255,255,.05)', border: providerType === id ? '1px solid #3b82f6' : '1px solid rgba(66,71,84,.4)' }}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.35fr', gap: '12px' }}>
            <label style={{ color: '#94a3b8', fontSize: '0.74rem' }}>
              Provider name
              <input required value={name} onChange={(event) => setName(event.target.value)} style={{ ...fieldStyle, marginTop: '5px' }} />
            </label>
            <label style={{ color: '#94a3b8', fontSize: '0.74rem' }}>
              Base URL / endpoint
              <input required value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="https://..." style={{ ...fieldStyle, marginTop: '5px', fontFamily: 'var(--font-mono, monospace)' }} />
            </label>
          </div>

          <label style={{ color: '#94a3b8', fontSize: '0.74rem' }}>
            API key (optional for local endpoints)
            <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} autoComplete="new-password" placeholder="Stored encrypted; never returned" style={{ ...fieldStyle, marginTop: '5px', fontFamily: 'var(--font-mono, monospace)' }} />
          </label>

          <div style={{ padding: '9px 11px', borderRadius: '7px', border: '1px solid rgba(59,130,246,.25)', background: 'rgba(59,130,246,.08)', color: '#93c5fd', fontSize: '0.72rem' }}>
            Models are not prefilled. Save the provider, run Test Connection, then Sync Models to persist its real catalog.
          </div>

          {formError && <div role="alert" style={{ padding: '9px 11px', borderRadius: '7px', background: 'rgba(239,68,68,.12)', border: '1px solid rgba(239,68,68,.35)', color: '#fca5a5', fontSize: '0.75rem' }}>{formError}</div>}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', paddingTop: '12px', borderTop: '1px solid rgba(66,71,84,.3)' }}>
            <button type="button" onClick={onClose} style={{ padding: '8px 16px', borderRadius: '7px', border: '1px solid rgba(66,71,84,.5)', background: 'transparent', color: '#cbd5e1', cursor: 'pointer' }}>Cancel</button>
            <button type="submit" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '8px 16px', borderRadius: '7px', border: 0, background: '#2563eb', color: '#fff', fontWeight: 700, cursor: 'pointer' }}>
              <Plus size={14} /> Save Provider
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
