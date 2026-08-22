/**
 * P0.1 — Providers page: full durable provider lifecycle surface.
 *
 * Server authority only: list/create/edit/enable-disable/delete/credentials/
 * connection test all round-trip to /api/v3/providers. No demo data, no local
 * inference, no fabricated receipts.
 */
import React, { useMemo, useState } from 'react';
import {
  Activity,
  DownloadCloud,
  KeyRound,
  Pencil,
  Plus,
  Power,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { HttpError } from '@windagent/api-client';
import type {
  AddProviderRequest,
  DeleteProviderConflict,
  ProviderConnectionTestResult,
  ProviderResource,
  RotateCredentialRequest,
  SyncModelsResult,
  UpdateProviderRequest,
} from '@windagent/api-contracts';
import {
  useCreateProvider,
  useDeleteProvider,
  useProviders,
  useProvidersHealth,
  useRemoveProviderCredential,
  useRotateProviderCredential,
  useSyncProviderModels,
  useTestProviderConnection,
  useUpdateProvider,
} from '../../providers/hooks/useProviders';

const panel: React.CSSProperties = {
  background: 'var(--surface-raised, #111827)',
  border: '1px solid var(--border-subtle, #263244)',
  borderRadius: 12,
  padding: 18,
};

const field: React.CSSProperties = {
  background: 'var(--surface, #0b1220)',
  border: '1px solid var(--border-subtle, #334155)',
  borderRadius: 8,
  color: 'inherit',
  padding: '9px 10px',
  width: '100%',
};

const button: React.CSSProperties = {
  alignItems: 'center',
  background: '#2563eb',
  border: 0,
  borderRadius: 8,
  color: '#fff',
  cursor: 'pointer',
  display: 'inline-flex',
  fontWeight: 700,
  gap: 7,
  justifyContent: 'center',
  padding: '9px 12px',
};

const buttonGhost: React.CSSProperties = {
  ...button,
  background: 'transparent',
  border: '1px solid var(--border-subtle, #334155)',
  color: 'var(--text-main, #e5e7eb)',
};

const buttonDanger: React.CSSProperties = {
  ...button,
  background: '#dc2626',
};

const chip = (color: string): React.CSSProperties => ({
  alignItems: 'center',
  backgroundColor: `${color}22`,
  borderRadius: 999,
  color,
  display: 'inline-flex',
  fontSize: 12,
  fontWeight: 700,
  gap: 6,
  lineHeight: '20px',
  padding: '2px 10px',
});

const STATUS_COLORS: Record<string, string> = {
  healthy: '#22c55e',
  degraded: '#f59e0b',
  offline: '#ef4444',
  unconfigured: '#94a3b8',
};

const emptyAddForm: AddProviderRequest = {
  id: '',
  name: '',
  type: 'cloud',
  base_url: '',
  protocol_mode: 'openai',
};

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Extract the structured 409 dependency payload from a failed delete. */
function parseDeleteConflict(error: unknown): DeleteProviderConflict | null {
  if (!(error instanceof HttpError) || error.status !== 409) return null;
  try {
    const parsed = JSON.parse(error.responseBody ?? '') as { detail?: DeleteProviderConflict };
    if (parsed?.detail?.blocking_rules) return parsed.detail;
  } catch {
    /* fall through */
  }
  return null;
}

const AddProviderForm: React.FC<{
  pending: boolean;
  error: string | null;
  onSubmit: (form: AddProviderRequest) => void;
}> = ({ pending, error, onSubmit }) => {
  const [form, setForm] = useState<AddProviderRequest>(emptyAddForm);
  const set = (patch: Partial<AddProviderRequest>) =>
    setForm((prev) => ({ ...prev, ...patch }));

  return (
    <section style={{ ...panel, marginBottom: 18 }}>
      <h2 style={{ margin: '0 0 12px' }}>Add provider</h2>
      <form
        style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(form);
          setForm(emptyAddForm);
        }}
      >
        <label style={{ display: 'grid', gap: 4 }}>
          <span>Provider ID</span>
          <input required style={field} value={form.id} onChange={(e) => set({ id: e.target.value })} placeholder="openrouter" />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span>Display name</span>
          <input required style={field} value={form.name} onChange={(e) => set({ name: e.target.value })} placeholder="OpenRouter" />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span>Type</span>
          <select style={field} value={form.type} onChange={(e) => set({ type: e.target.value as AddProviderRequest['type'] })}>
            <option value="cloud">cloud</option>
            <option value="local">local</option>
            <option value="custom">custom</option>
          </select>
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span>Base URL</span>
          <input required style={field} value={form.base_url} onChange={(e) => set({ base_url: e.target.value })} placeholder="https://openrouter.ai/api/v1" />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span>Protocol mode</span>
          <select style={field} value={form.protocol_mode} onChange={(e) => set({ protocol_mode: e.target.value as AddProviderRequest['protocol_mode'] })}>
            <option value="openai">OpenAI-compatible (OpenRouter / Groq / custom)</option>
            <option value="anthropic">Anthropic</option>
            <option value="gemini">Gemini</option>
            <option value="ollama">Ollama</option>
          </select>
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span>API key (encrypted at rest)</span>
          <input type="password" style={field} value={form.api_key ?? ''} onChange={(e) => set({ api_key: e.target.value || undefined })} placeholder="sk-…" autoComplete="new-password" />
        </label>
      </form>
      {error && (
        <div role="alert" style={{ color: '#fca5a5', marginTop: 10 }}>{error}</div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
        <button disabled={pending} style={button} type="submit">
          <Plus size={15} /> Register provider
        </button>
      </div>
    </section>
  );
};

const EditProviderForm: React.FC<{
  provider: ProviderResource;
  pending: boolean;
  onSave: (providerId: string, request: UpdateProviderRequest) => Promise<void>;
  onClose: () => void;
}> = ({ provider, pending, onSave, onClose }) => {
  const endpoint = provider.endpoints[0];
  const [name, setName] = useState(provider.display_name);
  const [baseUrl, setBaseUrl] = useState(endpoint?.base_url ?? '');
  const [protocolMode, setProtocolMode] = useState<UpdateProviderRequest['protocol_mode']>(
    'openai',
  );

  return (
    <div style={{ borderTop: '1px solid var(--border-subtle, #263244)', marginTop: 12, paddingTop: 12 }}>
      <form
        style={{ alignItems: 'end', display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}
        onSubmit={(event) => {
          event.preventDefault();
          void onSave(provider.id, {
            name,
            base_url: baseUrl || undefined,
            protocol_mode: protocolMode ?? undefined,
          }).then(onClose);
        }}
      >
        <label style={{ display: 'grid', gap: 4 }}>
          <span>Display name</span>
          <input required style={field} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span>Base URL</span>
          <input style={field} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span>Protocol mode</span>
          <select style={field} value={protocolMode} onChange={(e) => setProtocolMode(e.target.value as UpdateProviderRequest['protocol_mode'])}>
            <option value="openai">OpenAI-compatible</option>
            <option value="anthropic">Anthropic</option>
            <option value="gemini">Gemini</option>
            <option value="ollama">Ollama</option>
          </select>
        </label>
        <div style={{ display: 'flex', gap: 8 }}>
          <button disabled={pending} style={button} type="submit">Save</button>
          <button onClick={onClose} style={buttonGhost} type="button">Cancel</button>
        </div>
      </form>
      <p style={{ color: 'var(--text-muted, #94a3b8)', marginBottom: 0 }}>
        Protocol mode is applied on save; rotate the API key from the credential panel.
      </p>
    </div>
  );
};

const CredentialPanel: React.FC<{
  provider: ProviderResource;
  rotatePending: boolean;
  removePending: boolean;
  message: string | null;
  onRotate: (providerId: string, request: RotateCredentialRequest) => void;
  onRemove: (providerId: string) => void;
}> = ({ provider, rotatePending, removePending, message, onRotate, onRemove }) => {
  const [apiKey, setApiKey] = useState('');
  const [label, setLabel] = useState('');

  return (
    <div style={{ borderTop: '1px solid var(--border-subtle, #263244)', marginTop: 12, paddingTop: 12 }}>
      <form
        style={{ alignItems: 'end', display: 'grid', gap: 10, gridTemplateColumns: 'minmax(200px, 2fr) minmax(140px, 1fr) auto auto' }}
        onSubmit={(event) => {
          event.preventDefault();
          if (!apiKey) return;
          onRotate(provider.id, { api_key: apiKey, label: label || undefined });
          setApiKey('');
          setLabel('');
        }}
      >
        <label style={{ display: 'grid', gap: 4 }}>
          <span>{provider.has_credentials ? 'Replace API key' : 'API key'}</span>
          <input
            required
            type="password"
            style={field}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-…"
            autoComplete="new-password"
          />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span>Label (optional)</span>
          <input style={field} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="primary" />
        </label>
        <button disabled={rotatePending || !apiKey} style={button} type="submit">
          <KeyRound size={15} /> {provider.has_credentials ? 'Rotate key' : 'Save key'}
        </button>
        <button
          disabled={removePending || !provider.has_credentials}
          onClick={() => onRemove(provider.id)}
          style={buttonGhost}
          type="button"
        >
          Remove credential
        </button>
      </form>
      {message && <p style={{ color: '#86efac', marginBottom: 0 }}>{message}</p>}
    </div>
  );
};

const DeleteConflictPanel: React.FC<{
  conflict: DeleteProviderConflict;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}> = ({ conflict, pending, onConfirm, onCancel }) => {
  const [allowDisable, setAllowDisable] = useState(false);
  return (
    <div role="alert" style={{ borderColor: '#ef4444', borderStyle: 'solid', borderWidth: 1, borderRadius: 8, marginTop: 12, padding: 12 }}>
      <strong style={{ color: '#fca5a5' }}>Cannot delete: routing rules still depend on this provider</strong>
      <ul style={{ margin: '8px 0' }}>
        {conflict.blocking_rules.map((rule) => (
          <li key={rule.role}>
            <code>{rule.role}</code> → <code>{rule.primary_canonical_model_id}</code>
          </li>
        ))}
      </ul>
      <p style={{ color: 'var(--text-muted, #94a3b8)' }}>{conflict.resolution}</p>
      <label style={{ alignItems: 'center', display: 'flex', gap: 8 }}>
        <input checked={allowDisable} onChange={(e) => setAllowDisable(e.target.checked)} type="checkbox" />
        Disable the conflicting rules explicitly, then delete the provider
      </label>
      <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
        <button disabled={pending || !allowDisable} onClick={onConfirm} style={buttonDanger} type="button">
          Disable rules & delete
        </button>
        <button onClick={onCancel} style={buttonGhost} type="button">Cancel</button>
      </div>
    </div>
  );
};

const ProviderCard: React.FC<{
  provider: ProviderResource;
  healthStatus?: string;
  receipt: ProviderConnectionTestResult | null;
  syncResult: SyncModelsResult | null;
  testPending: boolean;
  syncPending: boolean;
  updatePending: boolean;
  deletePending: boolean;
  rotatePending: boolean;
  removePending: boolean;
  conflict: DeleteProviderConflict | null;
  actionError: string | null;
  credMessage: string | null;
  onTestConnection: (providerId: string, endpointId: string) => void;
  onSyncModels: (providerId: string, endpointId?: string) => void;
  onUpdate: (providerId: string, request: UpdateProviderRequest) => Promise<void>;
  onDelete: (providerId: string) => void;
  onConfirmDelete: (providerId: string) => void;
  onCancelDelete: () => void;
  onToggleEnabled: (providerId: string, enabled: boolean) => void;
  onRotateCredential: (providerId: string, request: RotateCredentialRequest) => void;
  onRemoveCredential: (providerId: string) => void;
}> = ({
  provider,
  healthStatus,
  receipt,
  syncResult,
  testPending,
  syncPending,
  updatePending,
  deletePending,
  rotatePending,
  removePending,
  conflict,
  actionError,
  credMessage,
  onTestConnection,
  onSyncModels,
  onUpdate,
  onDelete,
  onConfirmDelete,
  onCancelDelete,
  onToggleEnabled,
  onRotateCredential,
  onRemoveCredential,
}) => {
  const [editing, setEditing] = useState(false);
  const [credOpen, setCredOpen] = useState(false);
  const statusColor = STATUS_COLORS[healthStatus ?? provider.status] ?? '#94a3b8';

  return (
    <article style={{ ...panel, marginBottom: 16 }}>
      <header style={{ alignItems: 'center', display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <ShieldCheck size={18} />
        <strong style={{ fontSize: 16 }}>{provider.display_name}</strong>
        <code style={{ color: 'var(--text-muted, #94a3b8)' }}>{provider.id}</code>
        <span style={chip(statusColor)}>
          ● {healthStatus ?? provider.status}
        </span>
        {!provider.enabled && <span style={chip('#ef4444')}>disabled</span>}
        <span style={chip('#38bdf8')}>{provider.models_count} models</span>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginLeft: 'auto' }}>
          <button
            onClick={() => onToggleEnabled(provider.id, provider.enabled === false)}
            style={buttonGhost}
            type="button"
          >
            <Power size={14} /> {provider.enabled === false ? 'Enable' : 'Disable'}
          </button>
          <button onClick={() => { setEditing((v) => !v); setCredOpen(false); }} style={buttonGhost} type="button">
            <Pencil size={14} /> Edit
          </button>
          <button onClick={() => { setCredOpen((v) => !v); setEditing(false); }} style={buttonGhost} type="button">
            <KeyRound size={14} /> API key
          </button>
          <button disabled={deletePending} onClick={() => onDelete(provider.id)} style={buttonDanger} type="button">
            <Trash2 size={14} /> Delete
          </button>
        </div>
      </header>

      {provider.endpoints.map((endpoint) => (
        <div key={endpoint.id} style={{ alignItems: 'center', display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 12 }}>
          <code>{endpoint.base_url}</code>
          <span style={chip(STATUS_COLORS[endpoint.status] ?? '#94a3b8')}>{endpoint.status}</span>
          {endpoint.latency_ms > 0 && <span>{endpoint.latency_ms.toFixed(1)} ms</span>}
          <span style={{ color: 'var(--text-muted, #94a3b8)' }}>
            {endpoint.is_configured
              ? `credential configured${endpoint.credential_label ? ` (${endpoint.credential_label})` : ''}`
              : 'no credential'}
          </span>
          <button
            disabled={testPending}
            onClick={() => onTestConnection(provider.id, endpoint.id)}
            style={button}
            type="button"
          >
            <Activity size={14} /> Test connection
          </button>
          <button
            disabled={syncPending}
            onClick={() => onSyncModels(provider.id, endpoint.id)}
            style={buttonGhost}
            type="button"
          >
            <DownloadCloud size={14} /> Sync Models
          </button>
        </div>
      ))}

      {syncResult && (
        <div
          role="status"
          style={{
            background: 'var(--surface, #0b1220)',
            borderRadius: 8,
            marginTop: 12,
            padding: 12,
          }}
        >
          <strong>
            {syncResult.ok ? 'Sync completed' : 'Sync failed'} ·{' '}
            {syncResult.discovered_count} discovered · {syncResult.added.length} added ·{' '}
            {syncResult.updated.length} updated · {syncResult.unchanged.length} unchanged ·{' '}
            {syncResult.unavailable.length} unavailable
          </strong>
          <div style={{ color: 'var(--text-muted, #94a3b8)', marginTop: 4 }}>
            {syncResult.message}
            {syncResult.error_code ? ` (error_code: ${syncResult.error_code})` : ''}
          </div>
        </div>
      )}

      {receipt && (
        <div style={{ background: 'var(--surface, #0b1220)', borderRadius: 8, marginTop: 12, padding: 12 }}>
          <strong>
            {receipt.reachable ? '● Reachable' : '● Unreachable'} · auth{' '}
            {receipt.auth_valid ? 'valid' : 'invalid'} · {receipt.latency_ms.toFixed(1)} ms ·{' '}
            {receipt.model_discovery.length} models discovered
          </strong>
          <div style={{ color: 'var(--text-muted, #94a3b8)', marginTop: 4 }}>{receipt.message}</div>
          {receipt.error_code && <div style={{ color: '#fca5a5' }}>error_code: {receipt.error_code}</div>}
        </div>
      )}

      {actionError && (
        <div role="alert" style={{ color: '#fca5a5', marginTop: 10 }}>{actionError}</div>
      )}

      {editing && (
        <EditProviderForm provider={provider} pending={updatePending} onSave={onUpdate} onClose={() => setEditing(false)} />
      )}
      {credOpen && (
        <CredentialPanel
          provider={provider}
          rotatePending={rotatePending}
          removePending={removePending}
          message={credMessage}
          onRotate={onRotateCredential}
          onRemove={onRemoveCredential}
        />
      )}
      {conflict && (
        <DeleteConflictPanel
          conflict={conflict}
          pending={deletePending}
          onConfirm={() => onConfirmDelete(provider.id)}
          onCancel={onCancelDelete}
        />
      )}
    </article>
  );
};

export const ProvidersPage: React.FC = () => {
  const providersQuery = useProviders();
  const healthQuery = useProvidersHealth();
  const createProvider = useCreateProvider();
  const testConnection = useTestProviderConnection();
  const updateProvider = useUpdateProvider();
  const deleteProvider = useDeleteProvider();
  const rotateCredential = useRotateProviderCredential();
  const removeCredential = useRemoveProviderCredential();
  const syncModels = useSyncProviderModels();

  const [showAdd, setShowAdd] = useState(false);
  const [receipts, setReceipts] = useState<Record<string, ProviderConnectionTestResult>>({});
  const [syncResults, setSyncResults] = useState<Record<string, SyncModelsResult>>({});
  const [conflicts, setConflicts] = useState<Record<string, DeleteProviderConflict>>({});
  const [actionErrors, setActionErrors] = useState<Record<string, string>>({});
  const [credMessages, setCredMessages] = useState<Record<string, string>>({});

  const providers = providersQuery.data ?? [];
  const health = healthQuery.data ?? {};
  const totalModels = useMemo(
    () => providers.reduce((total, provider) => total + provider.models_count, 0),
    [providers],
  );

  const handleTestConnection = (providerId: string, endpointId: string) => {
    void testConnection.mutateAsync({ providerId, endpointId }).then((receipt) => {
      setReceipts((prev) => ({ ...prev, [providerId]: receipt }));
    });
  };

  const handleSyncModels = (providerId: string, endpointId?: string) => {
    void syncModels.mutateAsync({ providerId, endpointId }).then((result) => {
      setSyncResults((prev) => ({ ...prev, [providerId]: result }));
    });
  };

  const handleSyncAll = async () => {
    for (const provider of providers) {
      const endpointId = provider.endpoints[0]?.id;
      if (!endpointId || provider.enabled === false) continue;
      try {
        const result = await syncModels.mutateAsync({ providerId: provider.id, endpointId });
        setSyncResults((prev) => ({ ...prev, [provider.id]: result }));
      } catch {
        // keep syncing remaining providers; per-card error surfaces via receipt state
      }
    }
  };

  const handleUpdate = async (providerId: string, request: UpdateProviderRequest) => {
    await updateProvider.mutateAsync({ providerId, request });
    setActionErrors((prev) => ({ ...prev, [providerId]: '' }));
  };

  const handleDelete = (providerId: string) => {
    setConflicts((prev) => ({ ...prev, [providerId]: undefined as never }));
    deleteProvider.mutate(
      { providerId },
      {
        onError: (error) => {
          const conflict = parseDeleteConflict(error);
          if (conflict) {
            setConflicts((prev) => ({ ...prev, [providerId]: conflict }));
          }
        },
      },
    );
  };

  const handleConfirmDelete = (providerId: string) => {
    void deleteProvider.mutateAsync({ providerId, allowDisablingRules: true }).then(() => {
      setConflicts((prev) => ({ ...prev, [providerId]: undefined as never }));
    });
  };

  const handleToggleEnabled = (providerId: string, enabled: boolean) => {
    void handleUpdate(providerId, { enabled });
  };

  const handleRotateCredential = (providerId: string, request: RotateCredentialRequest) => {
    void rotateCredential
      .mutateAsync({ providerId, request })
      .then((status) => {
        setCredMessages((prev) => ({
          ...prev,
          [providerId]: `Credential saved (v${status.secret_version}); encrypted at rest.`,
        }));
      })
      .catch((error) => {
        setCredMessages((prev) => ({ ...prev, [providerId]: errorText(error) }));
      });
  };

  const handleRemoveCredential = (providerId: string) => {
    void removeCredential.mutateAsync(providerId).then(() => {
      setCredMessages((prev) => ({ ...prev, [providerId]: 'Credential removed.' }));
    });
  };

  const listError = providersQuery.error ?? healthQuery.error;

  return (
    <main style={{ color: 'var(--text-main, #e5e7eb)', margin: '0 auto', maxWidth: 1200, padding: '24px 30px' }}>
      <header style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0 }}>Providers</h1>
          <p style={{ color: 'var(--text-muted, #94a3b8)', margin: '6px 0 0' }}>
            Durable provider registry — connection tests run real network probes; API keys are encrypted at rest and never returned.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => setShowAdd((v) => !v)} style={button} type="button">
            <Plus size={16} /> Add Provider
          </button>
          <button disabled={syncModels.isPending || providers.length === 0} onClick={() => void handleSyncAll()} style={buttonGhost} type="button">
            <DownloadCloud size={15} /> Sync All
          </button>
          <button
            onClick={() => void Promise.all([providersQuery.refetch(), healthQuery.refetch()])}
            style={buttonGhost}
            type="button"
          >
            <RefreshCw size={15} /> Refresh
          </button>
        </div>
      </header>

      {listError && (
        <div role="alert" style={{ ...panel, borderColor: '#ef4444', color: '#fca5a5', marginBottom: 18 }}>
          {errorText(listError)}
        </div>
      )}

      <section style={{ display: 'grid', gap: 14, gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', marginBottom: 18 }}>
        <div style={panel}><strong>{providers.length}</strong><div>Registered providers</div></div>
        <div style={panel}>
          <strong>{providers.filter((provider) => (health[provider.id]?.status ?? provider.status) === 'healthy').length}</strong>
          <div>Connected</div>
        </div>
        <div style={panel}><strong>{totalModels}</strong><div>Discovered models</div></div>
        <div style={panel}>
          <strong>{providers.filter((provider) => provider.has_credentials).length}</strong>
          <div>Credentials configured</div>
        </div>
      </section>

      {showAdd && (
        <AddProviderForm
          pending={createProvider.isPending}
          error={createProvider.error ? errorText(createProvider.error) : null}
          onSubmit={(form) => {
            void createProvider.mutateAsync(form).then(() => setShowAdd(false));
          }}
        />
      )}

      {providersQuery.isLoading && <p>Loading provider authority…</p>}

      {!providersQuery.isLoading && providers.length === 0 && !listError && (
        <div style={panel}>
          <strong>No providers registered yet.</strong>
          <p style={{ color: 'var(--text-muted, #94a3b8)' }}>
            Use “Add Provider” to register OpenRouter, Google AI Studio, Groq, Ollama, or any custom OpenAI-compatible endpoint.
          </p>
        </div>
      )}

      {providers.map((provider) => (
        <ProviderCard
          key={provider.id}
          provider={provider}
          healthStatus={health[provider.id]?.status}
          receipt={receipts[provider.id] ?? null}
          syncResult={syncResults[provider.id] ?? null}
          testPending={testConnection.isPending}
          syncPending={syncModels.isPending}
          updatePending={updateProvider.isPending}
          deletePending={deleteProvider.isPending}
          rotatePending={rotateCredential.isPending}
          removePending={removeCredential.isPending}
          conflict={conflicts[provider.id] ?? null}
          actionError={actionErrors[provider.id] || null}
          credMessage={credMessages[provider.id] || null}
          onTestConnection={handleTestConnection}
          onSyncModels={handleSyncModels}
          onUpdate={handleUpdate}
          onDelete={handleDelete}
          onConfirmDelete={handleConfirmDelete}
          onCancelDelete={() => setConflicts((prev) => ({ ...prev, [provider.id]: undefined as never }))}
          onToggleEnabled={handleToggleEnabled}
          onRotateCredential={handleRotateCredential}
          onRemoveCredential={handleRemoveCredential}
        />
      ))}
    </main>
  );
};

export default ProvidersPage;
