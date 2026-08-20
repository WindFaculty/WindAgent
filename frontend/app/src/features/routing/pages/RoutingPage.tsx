import React, { useMemo, useState } from 'react';
import { Activity, Plus, RefreshCw, ShieldCheck } from 'lucide-react';
import type {
  AddProviderRequest,
  AssignProviderModelRuleRequest,
  ProviderConnectionTestResult,
} from '@windagent/api-contracts';
import {
  useAssignProviderModelRule,
  useCreateProvider,
  useProviderModelRules,
  useProviders,
  useProvidersHealth,
  useTestProviderConnection,
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

const emptyProvider: AddProviderRequest = {
  id: '',
  name: '',
  type: 'cloud',
  base_url: '',
  protocol_mode: 'openai',
};

const emptyRule: AssignProviderModelRuleRequest = {
  role: '',
  name: '',
  primary_canonical_model_id: '',
  enabled: true,
  priority: 1,
};

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export const RoutingPage: React.FC = () => {
  const providersQuery = useProviders();
  const healthQuery = useProvidersHealth();
  const rulesQuery = useProviderModelRules();
  const createProvider = useCreateProvider();
  const testConnection = useTestProviderConnection();
  const assignRule = useAssignProviderModelRule();
  const [providerForm, setProviderForm] = useState<AddProviderRequest>(emptyProvider);
  const [ruleForm, setRuleForm] = useState<AssignProviderModelRuleRequest>(emptyRule);
  const [lastReceipt, setLastReceipt] = useState<ProviderConnectionTestResult | null>(null);

  const providers = providersQuery.data ?? [];
  const health = healthQuery.data ?? {};
  const rules = rulesQuery.data ?? [];
  const endpoints = useMemo(
    () => providers.flatMap((provider) => provider.endpoints),
    [providers],
  );

  const submitProvider = async (event: React.FormEvent) => {
    event.preventDefault();
    await createProvider.mutateAsync(providerForm);
    setProviderForm(emptyProvider);
  };

  const submitRule = async (event: React.FormEvent) => {
    event.preventDefault();
    await assignRule.mutateAsync(ruleForm);
    setRuleForm(emptyRule);
  };

  const probe = async (providerId: string, endpointId: string) => {
    const receipt = await testConnection.mutateAsync({ providerId, endpointId });
    setLastReceipt(receipt);
  };

  return (
    <main style={{ color: 'var(--text-main, #e5e7eb)', margin: '0 auto', maxWidth: 1500, padding: '24px 30px' }}>
      <header style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0 }}>Provider &amp; model routing</h1>
          <p style={{ color: 'var(--text-muted, #94a3b8)', margin: '6px 0 0' }}>
            Connection state, discovery, and routing rules are read from the server authority.
          </p>
        </div>
        <button
          onClick={() => void Promise.all([providersQuery.refetch(), healthQuery.refetch(), rulesQuery.refetch()])}
          style={button}
          type="button"
        >
          <RefreshCw size={16} /> Refresh
        </button>
      </header>

      {(providersQuery.error || healthQuery.error || rulesQuery.error) && (
        <div role="alert" style={{ ...panel, borderColor: '#ef4444', color: '#fca5a5', marginBottom: 18 }}>
          {errorText(providersQuery.error || healthQuery.error || rulesQuery.error)}
        </div>
      )}

      <section style={{ display: 'grid', gap: 14, gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', marginBottom: 18 }}>
        <div style={panel}><strong>{providers.length}</strong><div>Configured providers</div></div>
        <div style={panel}><strong>{endpoints.filter((endpoint) => endpoint.status === 'healthy').length}</strong><div>Healthy endpoints</div></div>
        <div style={panel}><strong>{providers.reduce((total, provider) => total + provider.models_count, 0)}</strong><div>Discovered models</div></div>
        <div style={panel}><strong>{rules.length}</strong><div>Enabled model rules</div></div>
      </section>

      <section style={{ ...panel, marginBottom: 18 }}>
        <h2 style={{ marginTop: 0 }}>Providers</h2>
        {providersQuery.isLoading ? <p>Loading provider authority…</p> : providers.map((provider) => (
          <article key={provider.id} style={{ borderTop: '1px solid #263244', padding: '14px 0' }}>
            <div style={{ alignItems: 'center', display: 'flex', gap: 10 }}>
              <ShieldCheck size={17} />
              <strong>{provider.display_name}</strong>
              <span>{health[provider.id]?.status ?? provider.status}</span>
              <span style={{ color: '#94a3b8' }}>{provider.models_count} models</span>
            </div>
            {provider.endpoints.map((endpoint) => (
              <div key={endpoint.id} style={{ alignItems: 'center', display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 10 }}>
                <code>{endpoint.base_url}</code>
                <span>{endpoint.status}</span>
                <span>{endpoint.latency_ms.toFixed(1)} ms</span>
                <span>{endpoint.is_configured ? endpoint.credential_reference || 'credential configured' : 'no credential'}</span>
                <button
                  disabled={testConnection.isPending}
                  onClick={() => void probe(provider.id, endpoint.id)}
                  style={button}
                  type="button"
                >
                  <Activity size={15} /> Test connection
                </button>
              </div>
            ))}
          </article>
        ))}
      </section>

      {lastReceipt && (
        <section aria-live="polite" style={{ ...panel, marginBottom: 18 }}>
          <strong>{lastReceipt.reachable ? 'Connection succeeded' : 'Connection failed'}</strong>
          <div>{lastReceipt.message}</div>
          <div>{lastReceipt.latency_ms.toFixed(1)} ms · {lastReceipt.model_discovery.length} models discovered</div>
          {lastReceipt.error_code && <code>{lastReceipt.error_code}</code>}
        </section>
      )}

      <div style={{ display: 'grid', gap: 18, gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))' }}>
        <form onSubmit={(event) => void submitProvider(event)} style={panel}>
          <h2 style={{ marginTop: 0 }}>Add provider</h2>
          <div style={{ display: 'grid', gap: 10 }}>
            <input required placeholder="Provider id" style={field} value={providerForm.id} onChange={(event) => setProviderForm({ ...providerForm, id: event.target.value })} />
            <input required placeholder="Display name" style={field} value={providerForm.name} onChange={(event) => setProviderForm({ ...providerForm, name: event.target.value })} />
            <input required placeholder="Base URL" style={field} value={providerForm.base_url} onChange={(event) => setProviderForm({ ...providerForm, base_url: event.target.value })} />
            <select style={field} value={providerForm.protocol_mode} onChange={(event) => setProviderForm({ ...providerForm, protocol_mode: event.target.value as AddProviderRequest['protocol_mode'] })}>
              <option value="openai">OpenAI compatible</option><option value="anthropic">Anthropic</option><option value="gemini">Gemini</option><option value="ollama">Ollama</option>
            </select>
            <input autoComplete="new-password" placeholder="API key (encrypted by server)" style={field} type="password" value={providerForm.api_key ?? ''} onChange={(event) => setProviderForm({ ...providerForm, api_key: event.target.value || undefined })} />
            <button disabled={createProvider.isPending} style={button} type="submit"><Plus size={16} /> Save provider</button>
            {createProvider.error && <span role="alert">{errorText(createProvider.error)}</span>}
          </div>
        </form>

        <form onSubmit={(event) => void submitRule(event)} style={panel}>
          <h2 style={{ marginTop: 0 }}>Assign model rule</h2>
          <div style={{ display: 'grid', gap: 10 }}>
            <input required placeholder="Role/capability (coding, planning, review)" style={field} value={ruleForm.role} onChange={(event) => setRuleForm({ ...ruleForm, role: event.target.value })} />
            <input required placeholder="Rule name" style={field} value={ruleForm.name} onChange={(event) => setRuleForm({ ...ruleForm, name: event.target.value })} />
            <input required placeholder="Discovered canonical model id" style={field} value={ruleForm.primary_canonical_model_id} onChange={(event) => setRuleForm({ ...ruleForm, primary_canonical_model_id: event.target.value })} />
            <button disabled={assignRule.isPending} style={button} type="submit">Assign rule</button>
            {assignRule.error && <span role="alert">{errorText(assignRule.error)}</span>}
          </div>
          <ul>
            {rules.map((rule) => <li key={rule.role}><strong>{rule.role}</strong> → <code>{rule.primary_canonical_model_id}</code></li>)}
          </ul>
        </form>
      </div>
    </main>
  );
};

export default RoutingPage;
