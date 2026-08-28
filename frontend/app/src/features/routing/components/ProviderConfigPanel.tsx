import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Eye,
  EyeOff,
  Info,
  Loader2,
  RefreshCw,
  Save,
  Zap,
} from 'lucide-react';
import type { ProviderItem } from './ProviderRegistryTable';

interface ProviderConfigPanelProps {
  provider: ProviderItem | null;
  onSave: (updated: ProviderItem) => Promise<void>;
  onTestConnection: (providerId: string) => Promise<void>;
  onSyncModels: (providerId: string) => Promise<void>;
  onLoadModelsByPricing: (pricing: 'FREE' | 'PAID') => Promise<number>;
  onUseSelectedModel: (providerId: string, modelId: string) => void;
  isTesting?: boolean;
  isSyncing?: boolean;
  isLoadingPricedModels?: boolean;
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  backgroundColor: 'rgba(17, 24, 39, 0.85)',
  border: '1px solid rgba(51, 65, 85, 0.6)',
  borderRadius: '8px',
  padding: '9px 12px',
  color: '#f8fafc',
  fontSize: '0.8rem',
  outline: 'none',
};

export const ProviderConfigPanel: React.FC<ProviderConfigPanelProps> = ({
  provider,
  onSave,
  onTestConnection,
  onSyncModels,
  onLoadModelsByPricing,
  onUseSelectedModel,
  isTesting = false,
  isSyncing = false,
  isLoadingPricedModels = false,
}) => {
  const [formData, setFormData] = useState<ProviderItem | null>(provider);
  const [newCredential, setNewCredential] = useState('');
  const [showCredential, setShowCredential] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [selectedModels, setSelectedModels] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setFormData(provider);
    setNewCredential('');
    setShowCredential(false);
    setMessage('');
    setError('');
    setSelectedModels(new Set());
  }, [provider]);

  if (!formData) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '300px',
          height: '100%',
          padding: '24px',
          boxSizing: 'border-box',
          backgroundColor: 'rgba(11, 19, 38, 0.85)',
          borderRadius: '14px',
          border: '1px solid rgba(51, 65, 85, 0.45)',
          color: '#64748b',
          fontSize: '0.85rem',
          textAlign: 'center',
        }}
      >
        Add or select a durable provider to configure its database-backed endpoint.
      </div>
    );
  }

  const clearFeedback = () => {
    setMessage('');
    setError('');
  };

  const handleSave = async () => {
    clearFeedback();
    setIsSaving(true);
    const payload = { ...formData } as ProviderItem & { __rawApiKey?: string };
    if (newCredential.trim()) payload.__rawApiKey = newCredential.trim();
    try {
      await onSave(payload);
      setNewCredential('');
      setMessage('Provider configuration saved to database.');
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setIsSaving(false);
    }
  };

  const handleTest = async () => {
    clearFeedback();
    try {
      await onTestConnection(formData.id);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  };

  const handleSync = async () => {
    clearFeedback();
    try {
      await onSyncModels(formData.id);
      setMessage('Models synchronized from the provider and saved to database.');
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  };

  const handleLoadModelsByPricing = async (pricing: 'FREE' | 'PAID') => {
    clearFeedback();
    try {
      const count = await onLoadModelsByPricing(pricing);
      setMessage(`${count} ${pricing.toLowerCase()} model(s) loaded from the synchronized catalog.`);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  };

  const testSucceeded = formData.lastTestStatus === 'success';
  const busy = isSaving || isTesting || isSyncing || isLoadingPricedModels;
  const modelGroups = Object.entries(
    formData.models.reduce<Record<string, string[]>>((groups, modelId) => {
      const group = modelId.includes('/') ? modelId.split('/')[0] : 'Other';
      (groups[group] ??= []).push(modelId);
      return groups;
    }, {}),
  )
    .map(([group, models]) => [group, [...models].sort((a, b) => a.localeCompare(b))] as const)
    .sort(([a], [b]) => a.localeCompare(b));

  return (
    <section
      style={{
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'rgba(11, 19, 38, 0.85)',
        borderRadius: '14px',
        border: '1px solid rgba(51, 65, 85, 0.45)',
        backdropFilter: 'blur(16px)',
        overflow: 'hidden',
        height: '100%',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px 18px',
          borderBottom: '1px solid rgba(51, 65, 85, 0.35)',
        }}
      >
        <div>
          <h2 style={{ margin: 0, color: '#f8fafc', fontSize: '0.98rem' }}>Provider Configuration</h2>
          <span style={{ color: '#64748b', fontSize: '0.72rem', fontFamily: 'var(--font-mono, monospace)' }}>
            {formData.id}
          </span>
        </div>
        <span
          style={{
            padding: '3px 9px',
            borderRadius: '999px',
            color: formData.status === 'connected' ? '#34d399' : formData.status === 'offline' ? '#f87171' : '#fbbf24',
            backgroundColor: formData.status === 'connected' ? 'rgba(16,185,129,.12)' : formData.status === 'offline' ? 'rgba(239,68,68,.12)' : 'rgba(245,158,11,.12)',
            border: '1px solid currentColor',
            fontSize: '0.7rem',
            fontWeight: 700,
          }}
        >
          {formData.status}
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '18px', padding: '18px', overflowY: 'auto' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: '12px' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', color: '#94a3b8', fontSize: '0.74rem' }}>
            Provider name
            <input
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              style={inputStyle}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', color: '#94a3b8', fontSize: '0.74rem' }}>
            Base URL / endpoint
            <input
              value={formData.endpoint}
              onChange={(e) => setFormData({ ...formData, endpoint: e.target.value })}
              style={{ ...inputStyle, fontFamily: 'var(--font-mono, monospace)' }}
            />
          </label>
        </div>

        <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', color: '#94a3b8', fontSize: '0.74rem' }}>
          Replace API key
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <input
              type={showCredential ? 'text' : 'password'}
              value={newCredential}
              onChange={(e) => setNewCredential(e.target.value)}
              placeholder="Leave blank to keep the encrypted credential"
              autoComplete="new-password"
              style={{ ...inputStyle, fontFamily: 'var(--font-mono, monospace)' }}
            />
            <button
              type="button"
              aria-label={showCredential ? 'Hide credential' : 'Show credential'}
              onClick={() => setShowCredential((value) => !value)}
              style={{ padding: '9px', borderRadius: '8px', border: '1px solid rgba(51,65,85,.6)', background: 'rgba(17,24,39,.85)', color: '#94a3b8', cursor: 'pointer' }}
            >
              {showCredential ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          <span style={{ color: '#64748b', fontSize: '0.68rem' }}>
            Credential state: {formData.credentialsStatus}. Raw secrets are encrypted by the backend and are never returned.
          </span>
        </label>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
            <div>
              <div style={{ color: '#e2e8f0', fontSize: '0.78rem', fontWeight: 700 }}>Discovered model catalog</div>
              <div style={{ color: '#64748b', fontSize: '0.68rem' }}>Read-only database view. Use Sync Models to refresh it from the provider API.</div>
            </div>
            <span style={{ color: '#60a5fa', fontSize: '0.72rem', fontWeight: 700 }}>{formData.models.length} models</span>
          </div>
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '7px',
              minHeight: '44px',
              padding: '9px',
              borderRadius: '8px',
              border: '1px solid rgba(51,65,85,.6)',
              backgroundColor: 'rgba(17,24,39,.75)',
              alignItems: 'center',
            }}
          >
            {formData.models.length === 0 ? (
              <span style={{ color: '#64748b', fontSize: '0.73rem' }}>No models have been synchronized.</span>
            ) : modelGroups.map(([group, models]) => (
              <div key={group} style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '7px', color: '#93c5fd', fontSize: '0.69rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  <span>{group}</span>
                  <span style={{ color: '#64748b', fontSize: '0.65rem', fontWeight: 700 }}>{models.length}</span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '7px' }}>
                  {models.map((model) => {
                    const isSelected = selectedModels.has(model);
                    return (
                      <button
                        key={model}
                        type="button"
                        aria-pressed={isSelected}
                        onClick={() => {
                          setSelectedModels((current) => {
                            const next = new Set(current);
                            if (next.has(model)) next.delete(model);
                            else next.add(model);
                            return next;
                          });
                        }}
                        style={{
                          padding: '4px 8px', borderRadius: '6px', cursor: 'pointer',
                          background: isSelected ? 'rgba(37,99,235,.28)' : 'rgba(255,255,255,.06)',
                          border: isSelected ? '1px solid #60a5fa' : '1px solid rgba(255,255,255,.1)',
                          color: isSelected ? '#dbeafe' : '#cbd5e1', fontSize: '0.7rem', fontFamily: 'var(--font-mono, monospace)',
                        }}
                      >
                        {model}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          {selectedModels.size > 0 && (
            <div role="status" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', padding: '9px 10px', borderRadius: '8px', background: 'rgba(37,99,235,.1)', border: '1px solid rgba(96,165,250,.35)', color: '#bfdbfe', fontSize: '0.72rem' }}>
              <span>
                {selectedModels.size === 1 ? (
                  <>Selected: <strong style={{ fontFamily: 'var(--font-mono, monospace)' }}>{[...selectedModels][0]}</strong></>
                ) : (
                  <>{selectedModels.size} models selected. Choose one model to create a routing rule.</>
                )}
              </span>
              <div style={{ display: 'flex', gap: '7px' }}>
                {selectedModels.size === 1 && (
                  <button type="button" onClick={() => onUseSelectedModel(formData.id, [...selectedModels][0])} style={{ border: 'none', borderRadius: '6px', background: '#2563eb', color: '#fff', padding: '6px 9px', fontWeight: 700, fontSize: '0.7rem', cursor: 'pointer' }}>
                    Use in model rule
                  </button>
                )}
                <button type="button" onClick={() => setSelectedModels(new Set())} style={{ border: '1px solid rgba(191,219,254,.35)', borderRadius: '6px', background: 'transparent', color: '#bfdbfe', padding: '6px 9px', fontWeight: 700, fontSize: '0.7rem', cursor: 'pointer' }}>
                  Clear
                </button>
              </div>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
          <button type="button" disabled={busy} onClick={handleSave} style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '9px 16px', borderRadius: '8px', border: '1px solid rgba(147,197,253,.35)', background: '#2563eb', color: '#fff', fontWeight: 700, cursor: busy ? 'wait' : 'pointer' }}>
            {isSaving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            {isSaving ? 'Saving...' : 'Save to Database'}
          </button>
          <button type="button" disabled={busy} onClick={handleTest} style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '9px 16px', borderRadius: '8px', border: '1px solid rgba(99,102,241,.35)', background: 'rgba(99,102,241,.12)', color: '#c7d2fe', fontWeight: 700, cursor: busy ? 'wait' : 'pointer' }}>
            {isTesting ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
            {isTesting ? 'Testing...' : 'Test Connection'}
          </button>
          <button type="button" disabled={busy} onClick={handleSync} style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '9px 16px', borderRadius: '8px', border: '1px solid rgba(16,185,129,.35)', background: 'rgba(16,185,129,.12)', color: '#6ee7b7', fontWeight: 700, cursor: busy ? 'wait' : 'pointer' }}>
            {isSyncing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {isSyncing ? 'Syncing...' : 'Sync Models'}
          </button>
          <button type="button" disabled={busy} onClick={() => handleLoadModelsByPricing('FREE')} style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '9px 16px', borderRadius: '8px', border: '1px solid rgba(34,197,94,.35)', background: 'rgba(34,197,94,.1)', color: '#86efac', fontWeight: 700, cursor: busy ? 'wait' : 'pointer' }}>
            {isLoadingPricedModels ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Load Free Models
          </button>
          <button type="button" disabled={busy} onClick={() => handleLoadModelsByPricing('PAID')} style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '9px 16px', borderRadius: '8px', border: '1px solid rgba(245,158,11,.35)', background: 'rgba(245,158,11,.1)', color: '#fcd34d', fontWeight: 700, cursor: busy ? 'wait' : 'pointer' }}>
            {isLoadingPricedModels ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Load Paid Models
          </button>
        </div>

        {error && (
          <div role="alert" style={{ display: 'flex', gap: '8px', padding: '10px 12px', borderRadius: '8px', background: 'rgba(239,68,68,.12)', border: '1px solid rgba(239,68,68,.35)', color: '#fca5a5', fontSize: '0.74rem' }}>
            <AlertCircle size={15} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}
        {message && !error && (
          <div role="status" style={{ display: 'flex', gap: '8px', padding: '10px 12px', borderRadius: '8px', background: 'rgba(16,185,129,.08)', border: '1px solid rgba(16,185,129,.3)', color: '#6ee7b7', fontSize: '0.74rem' }}>
            <CheckCircle2 size={15} style={{ flexShrink: 0 }} />
            <span>{message}</span>
          </div>
        )}

        {formData.lastTestStatus ? (
          <div
            role={testSucceeded ? 'status' : 'alert'}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '9px',
              padding: '12px 14px',
              borderRadius: '9px',
              background: testSucceeded ? 'rgba(16,185,129,.06)' : 'rgba(239,68,68,.08)',
              border: `1px solid ${testSucceeded ? 'rgba(16,185,129,.3)' : 'rgba(239,68,68,.35)'}`,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '7px', color: testSucceeded ? '#34d399' : '#f87171', fontWeight: 700, fontSize: '0.8rem' }}>
                {testSucceeded ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                {testSucceeded ? 'Connection successful' : 'Connection failed'}
              </span>
              <span style={{ color: '#64748b', fontSize: '0.68rem' }}>{formData.lastTestTime}</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', color: '#94a3b8', fontSize: '0.68rem' }}>
              <span>Latency<br /><strong style={{ color: '#e2e8f0' }}>{formData.lastTestLatency ?? 0} ms</strong></span>
              <span>Authentication<br /><strong style={{ color: formData.lastTestAuthValid ? '#34d399' : '#f87171' }}>{formData.lastTestAuthValid ? 'Valid' : 'Failed'}</strong></span>
              <span>Endpoint<br /><strong style={{ color: testSucceeded ? '#34d399' : '#f87171' }}>{testSucceeded ? 'Reachable' : 'Unavailable'}</strong></span>
            </div>
            <div style={{ color: testSucceeded ? '#94a3b8' : '#fca5a5', fontSize: '0.7rem' }}>{formData.lastTestMessage}</div>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 12px', borderRadius: '8px', background: 'rgba(255,255,255,.03)', border: '1px solid rgba(51,65,85,.4)', color: '#94a3b8', fontSize: '0.73rem' }}>
            <Info size={14} color="#60a5fa" />
            No real connection test has been run for this provider.
          </div>
        )}
      </div>
    </section>
  );
};
