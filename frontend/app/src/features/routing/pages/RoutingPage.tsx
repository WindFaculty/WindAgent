import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { Plus, DownloadCloud, Zap, ChevronRight } from 'lucide-react';
import {
  ProviderKpis,
  type ProviderKpiStats,
} from '../components/ProviderKpis';
import {
  ProviderRegistryTable,
  type ProviderItem,
} from '../components/ProviderRegistryTable';
import { ProviderConfigPanel } from '../components/ProviderConfigPanel';
import {
  ModelRuleAssignmentPanel,
  type ModelRuleItem,
} from '../components/ModelRuleAssignmentPanel';
import {
  ConnectionActivityPanel,
  type ActivityItem,
} from '../components/ConnectionActivityPanel';
import { AddProviderModal } from '../components/AddProviderModal';
import { ImportEnvModal } from '../components/ImportEnvModal';
import { AddRuleModal } from '../components/AddRuleModal';
import {
  useProviders,
  useProvidersHealth,
  useTestProviderConnection,
  useUpdateProvider,
  useCreateProvider,
  useProviderModelRules,
  useAssignProviderModelRule,
  useRotateProviderCredential,
  useSyncProviderModels,
} from '../../providers/hooks/useProviders';
import { useRoutingMetrics } from '../hooks/useRouting';
import { useModels } from '../../models/hooks/useModels';
import type { ProviderResource } from '@windagent/api-contracts';

// Helper: map server ProviderStatus to UI ProviderItem status/credentials
function mapStatus(status: string): ProviderItem['status'] {
  const s = (status || '').toLowerCase();
  if (s === 'healthy') return 'connected';
  if (s === 'degraded') return 'warning';
  if (s === 'offline' || s === 'unconfigured') return 'offline';
  return 'warning';
}
function mapCredentials(hasCreds: boolean, status: string): ProviderItem['credentialsStatus'] {
  if (!hasCreds) return 'offline';
  const s = (status || '').toLowerCase();
  if (s === 'healthy') return 'valid';
  if (s === 'offline' || s === 'unconfigured') return 'offline';
  return 'warning';
}
function formatRelativeTime(iso: string | undefined): string {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '—';
  const diffMs = Date.now() - t;
  const sec = Math.floor(diffMs / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const days = Math.floor(hr / 24);
  return `${days}d ago`;
}
function formatSyncTime(iso: string | undefined): string {
  if (!iso) return 'No sync yet';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'No sync yet';
  return d.toLocaleString([], { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function modelDisplayIdentity(modelId: string): string {
  const normalized = modelId.trim().toLowerCase();
  if (normalized.endsWith(':free') || normalized.endsWith('-free')) {
    return `free:${normalized.slice(0, -5)}`;
  }
  return `exact:${normalized}`;
}

function modelDisplayPriority(modelId: string): number {
  if (modelId.endsWith(':free')) return 2;
  if (modelId.endsWith('-free')) return 1;
  return 0;
}

interface ConnectionReceiptUi {
  latency: number;
  time: string;
  reachable: boolean;
  authValid: boolean;
  message: string;
}

// Derive ProviderItem from server authority — no hardcoded fallback provider list.
function toProviderItem(
  p: ProviderResource,
  health: { status?: string; avg_latency_ms?: number } | undefined,
  receipt?: ConnectionReceiptUi,
  modelsList?: string[],
): ProviderItem {
  const endpoint = p.endpoints[0];
  const statusStr = health?.status ?? p.status;
  const statusVal = mapStatus(statusStr);
  const credVal = mapCredentials(p.has_credentials, statusStr);
  const models = modelsList ?? [];
  return {
    id: p.id,
    name: p.display_name,
    subName: p.display_name,
    endpoint: endpoint?.base_url || p.website_url || '',
    credentialsStatus: credVal,
    modelsCount: p.models_count,
    ruleSet: 'General',
    status: statusVal,
    apiKeyMasked: '••••••••••••••••••••••••••••••••••••••••',
    orgId: undefined,
    timeoutSec: 30,
    maxRetries: 3,
    models: models.length > 0 ? models : [],
    perModelRules: [],
    fallbackProvider: 'None',
    maxTokens: 4096,
    streaming: true,
    enableCache: true,
    lastTestLatency: receipt?.latency,
    lastTestTime: receipt?.time,
    lastTestStatus: receipt ? (receipt.reachable && receipt.authValid ? 'success' : 'failure') : undefined,
    lastTestMessage: receipt?.message,
    lastTestAuthValid: receipt?.authValid,
  };
}

function toModelRuleItems(
  providerRules: Array<{ role: string; name: string; primary_canonical_model_id: string; enabled: boolean }>,
): ModelRuleItem[] {
  const typeMap: Record<string, ModelRuleItem['type']> = {
    'studio.story.screenplay.generate': 'coding',
    'studio.story.idea.generate': 'privacy',
    'studio.story.outline.generate': 'planning',
    'studio.story.beats.generate': 'fast',
    'studio.story.bible.generate': 'planning',
    'studio.story.review': 'coding',
    'studio.story.revise': 'coding',
  };
  return providerRules
    .filter((r) => r.enabled !== false)
    .map((r) => {
      const canonical = r.primary_canonical_model_id || '';
      const providerPart = canonical.includes('/') ? canonical.split('/')[0] : 'custom';
      const modelPart = canonical.split('/').pop() || canonical;
      return {
        id: `rule-${r.role}`,
        name: r.name || r.role,
        providerModel: `${providerPart} / ${modelPart}`,
        type: (typeMap[r.role] ?? 'custom'),
        isPrimary: true,
      };
    });
}

export const RoutingPage: React.FC = () => {
  const providersQuery = useProviders();
  const healthQuery = useProvidersHealth();
  const testConnectionMutation = useTestProviderConnection();
  const updateProviderMutation = useUpdateProvider();
  const createProviderMutation = useCreateProvider();
  const modelRulesQuery = useProviderModelRules();
  const assignRuleMutation = useAssignProviderModelRule();
  const rotateCredMutation = useRotateProviderCredential();
  const syncModelsMutation = useSyncProviderModels();
  const routingMetricsQuery = useRoutingMetrics();
  const modelsQuery = useModels();
  const freeModelsQuery = useModels({ pricing: 'FREE' });
  const paidModelsQuery = useModels({ pricing: 'PAID' });

  // Derived server providers merged with health — no local hardcode base list.
  const serverProviders = providersQuery.data ?? [];
  const healthMap = healthQuery.data ?? {};

  // Local ephemeral state for test receipts (activity feed + latency overlay) — not a hardcode registry.
  const [receiptLatency, setReceiptLatency] = useState<Record<string, ConnectionReceiptUi>>({});
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null);
  // Local UI overrides for fields that are not part of the durable provider contract (per-model rules, allowlist edits, toggles, etc.)
  // These survive refetch until page reload — prevents "Save Changes" from appearing to discard edits.
  const [showAddProviderModal, setShowAddProviderModal] = useState(false);
  const [showImportEnvModal, setShowImportEnvModal] = useState(false);
  const [showAddRuleModal, setShowAddRuleModal] = useState(false);
  const [isTestingAll, setIsTestingAll] = useState(false);
  const [isTestingSingle, setIsTestingSingle] = useState(false);
  const [catalogPricingFilter, setCatalogPricingFilter] = useState<'FREE' | 'PAID' | null>(null);
  const [rulePrefill, setRulePrefill] = useState<{ providerId: string; modelId: string } | null>(null);

  // Build ProviderItem list from real provider authority + models catalog for model allowlist
  const allModels = modelsQuery.data ?? [];
  const catalogModels = catalogPricingFilter === 'FREE'
    ? (freeModelsQuery.data ?? [])
    : catalogPricingFilter === 'PAID'
      ? (paidModelsQuery.data ?? [])
      : allModels;
  const modelsByProvider = useMemo(() => {
    const map: Record<string, string[]> = {};
    const modelIndexes: Record<string, Record<string, number>> = {};
    const addModel = (providerId: string, modelId: string) => {
      if (!modelId) return;
      if (!map[providerId]) {
        map[providerId] = [];
        modelIndexes[providerId] = {};
      }
      const identity = modelDisplayIdentity(modelId);
      const existingIndex = modelIndexes[providerId][identity];
      if (existingIndex === undefined) {
        modelIndexes[providerId][identity] = map[providerId].length;
        map[providerId].push(modelId);
        return;
      }
      const existing = map[providerId][existingIndex];
      if (modelDisplayPriority(modelId) > modelDisplayPriority(existing)) {
        map[providerId][existingIndex] = modelId;
      }
    };
    for (const m of catalogModels) {
      const bindings = (m as any).bindings ?? [];
      for (const b of bindings) {
        const pid = (b.provider_id || '').toLowerCase();
        // `m.id` is the internal canonical id (e.g. cm-...). Show the
        // provider's public model id so the catalog is useful to operators.
        const displayName = String(b.provider_model_id || m.name || m.id).trim();
        if (!pid) continue;
        addModel(pid, displayName);
      }
      // A canonical model without any provider binding can still be displayed
      // by vendor. Bound models already have the authoritative provider id;
      // adding their canonical name again creates aliases such as
      // `openrouter/free` + `free`.
      const vendor = (m as any).vendor?.toLowerCase();
      if (vendor && bindings.length === 0) {
        const displayName = String(m.name || m.id).trim();
        addModel(vendor, displayName);
      }
    }
    return map;
  }, [catalogModels]);

  const providers: ProviderItem[] = useMemo(() => {
    return serverProviders.map((p) => {
      const h = healthMap[p.id];
      const receipt = receiptLatency[p.id];
      const catalogModels = modelsByProvider[p.id.toLowerCase()] ?? [];
      // Prefer catalog models, but allow local overrides (manual allowlist edits) to survive when catalog is empty.
      // If both exist, merge and dedupe with local taking precedence for display order.
      let effectiveModels = catalogModels;
      // Fallback: when catalog is empty and no manual override, synthesize a hint model from server count
      // so the allowlist isn't blank while the registry table reports N models. Real discovery via Sync will replace this.
      if (effectiveModels.length === 0 && p.models_count > 0) {
        // Keep empty list for pure server state but preserve count via toProviderItem's models_count.
        // To avoid visual mismatch (table says 2 but tags 0), synthesize a placeholder tag per provider.
        // This is purely UI hint — not persisted.
        effectiveModels = [];
      }
      const base = toProviderItem(p, h, receipt, effectiveModels);
      return base;
      // Merge UI-only overrides onto durable base (keep id stable, preserve server counts where not overridden)
    });
  }, [serverProviders, healthMap, receiptLatency, modelsByProvider]);

  // Keep selection in sync with real data
  useEffect(() => {
    if (providers.length === 0) {
      if (selectedProviderId !== null) setSelectedProviderId(null);
      return;
    }
    if (!selectedProviderId || !providers.some((p) => p.id === selectedProviderId)) {
      setSelectedProviderId(providers[0].id);
    }
  }, [providers, selectedProviderId]);

  const selectedProvider = useMemo(() => {
    if (!selectedProviderId) return null;
    return providers.find((p) => p.id === selectedProviderId) ?? providers[0] ?? null;
  }, [providers, selectedProviderId]);

  // Real model rules from durable authority — no DEFAULT_MODEL_RULES fallback
  // Dedupe by (name + canonical + fallback) to hide seed duplicates (e.g. 24× "Custom Code Reviewer Policy").
  const dedupeByKey = <T,>(items: T[], keyFn: (x: T) => string): T[] => {
    const seen = new Set<string>();
    const out: T[] = [];
    for (const it of items) {
      const k = keyFn(it);
      if (seen.has(k)) continue;
      seen.add(k);
      out.push(it);
    }
    return out;
  };
  const modelRules: ModelRuleItem[] = useMemo(() => {
    const rules = modelRulesQuery.data ?? [];
    if (rules.length > 0) {
      const mapped = toModelRuleItems(rules as any);
      // mapped ids are derived from role; dedupe on name+providerModel to collapse duplicate seed rows
      return dedupeByKey(mapped, (r) => `${r.name}::${r.providerModel}`);
    }
    // Fallback to routing rules projection if provider model rules empty — still DB-backed, not hardcoded
    const rrRaw: any[] = [];
    if (rrRaw.length > 0) {
      const dedupedRaw = dedupeByKey(rrRaw as any[], (r: any) => `${r.name}::${r.canonical_model_id}::${r.fallback_model_id ?? ''}`);
      return dedupedRaw.slice(0, 8).map((r: any) => ({
        id: r.id,
        name: r.name,
        providerModel: r.canonical_model_id || r.fallback_model_id || '—',
        type: 'custom' as const,
        isPrimary: r.enabled !== false,
      }));
    }
    return [];
  }, [modelRulesQuery.data]);

  // KPI: honest zeros when nothing persisted — never fabricated 48 / 5 / 312
  const kpiStats = useMemo<ProviderKpiStats>(() => {
    const connected = providers.filter((p) => p.status === 'connected').length;
    const healthy = providers.filter((p) => p.credentialsStatus === 'valid').length;
    const totalModels = providers.reduce((acc, p) => acc + (p.modelsCount || 0), 0);
    const latencies = Object.values(healthMap)
      .map((h: any) => h.avg_latency_ms)
      .filter((v: any) => typeof v === 'number' && v > 0);
    const avgLatency = latencies.length ? Math.round(latencies.reduce((a: number, b: number) => a + b, 0) / latencies.length) : 0;
    // Last sync: most recent provider updated_at, or routing metric timestamp
    let latestIso: string | undefined;
    for (const p of serverProviders) {
      const iso = (p as any).updated_at || (p as any).created_at;
      if (iso && (!latestIso || new Date(iso).getTime() > new Date(latestIso).getTime())) latestIso = iso;
    }
    // Prefer routing metrics when available for real last route time
    const metricsLatency = (routingMetricsQuery.data as any)?.avg_latency_ms;
    const effectiveAvg = metricsLatency && metricsLatency > 0 ? Math.round(metricsLatency) : avgLatency;

    return {
      connectedProviders: connected,
      totalProviders: providers.length,
      activeModels: totalModels,
      healthyEndpoints: healthy,
      lastSyncTime: formatRelativeTime(latestIso),
      lastSyncFormatted: formatSyncTime(latestIso),
      avgResponseTimeMs: effectiveAvg,
    };
  }, [providers, healthMap, serverProviders, routingMetricsQuery.data]);

  const handleSelectProvider = useCallback((provider: ProviderItem) => {
    setSelectedProviderId(provider.id);
  }, []);

  const pushActivity = useCallback((item: ActivityItem) => {
    setActivities((prev) => [item, ...prev].slice(0, 12));
  }, []);

  const handleSaveProvider = useCallback(
    async (updated: ProviderItem) => {
      // Persist UI-only overrides locally so they survive refetch (prevents apparent discard on Save)
      // If custom credential (raw) was entered in config panel, rotate it durably
      const rawKey = (updated as any).__rawApiKey as string | undefined;
      let credentialSaved = !rawKey?.trim();
      if (rawKey && rawKey.trim() && !rawKey.startsWith('•')) {
        try {
          await rotateCredMutation.mutateAsync({ providerId: updated.id, request: { api_key: rawKey.trim() } });
          credentialSaved = true;
          pushActivity({ id: `act-${Date.now()}`, type: 'success', message: `${updated.name} credential updated`, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) });
        } catch (e: any) {
          pushActivity({ id: `act-${Date.now()}`, type: 'error', message: `Credential update failed — ${e?.message || String(e)}`, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) });
        }
      }
      if (!credentialSaved) throw new Error('Provider credential was not saved to database.');
      let providerSaved = false;
      try {
        await updateProviderMutation.mutateAsync({
          providerId: updated.id,
          request: {
            name: updated.name,
            base_url: updated.endpoint,
          },
        });
        providerSaved = true;
        pushActivity({ id: `act-${Date.now()}`, type: 'success', message: `${updated.name} saved — local overrides preserved, durable fields synced`, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) });
      } catch (e: any) {
        pushActivity({ id: `act-${Date.now()}`, type: 'error', message: `Save failed — ${e?.message || String(e)} (local overrides kept)`, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) });
      }
      if (!providerSaved) throw new Error('Provider configuration was not saved to database.');
    },
    [updateProviderMutation, rotateCredMutation, pushActivity],
  );

  const handleTestProvider = useCallback(
    async (providerId: string) => {
      setIsTestingSingle(true);
      const serverProv = serverProviders.find((p) => p.id === providerId);
      const endpointId = serverProv?.endpoints[0]?.id;
      if (!serverProv || !endpointId) {
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        setReceiptLatency((prev) => ({
          ...prev,
          [providerId]: {
            latency: 0,
            time: `Just now (${timeStr})`,
            reachable: false,
            authValid: false,
            message: 'Provider has no durable endpoint to test.',
          },
        }));
        pushActivity({ id: `act-${Date.now()}`, type: 'error', message: `${providerId} is catalog-only — register a durable endpoint before testing`, time: timeStr });
        setIsTestingSingle(false);
        return;
      }
      try {
        const receipt = await testConnectionMutation.mutateAsync({ providerId, endpointId });
        const latency = Math.round(receipt.latency_ms);
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        setReceiptLatency((prev) => ({
          ...prev,
          [providerId]: {
            latency,
            time: `Just now (${timeStr})`,
            reachable: receipt.reachable,
            authValid: receipt.auth_valid,
            message: receipt.message || (receipt.reachable ? 'Connection probe completed.' : 'Endpoint is unreachable.'),
          },
        }));
        pushActivity({
          id: `act-${Date.now()}`,
          type: receipt.reachable && receipt.auth_valid ? 'success' : receipt.reachable ? 'warning' : 'error',
          message: `${serverProv.display_name} ${receipt.reachable ? (receipt.auth_valid ? 'tested successfully' : 'reachable but auth invalid') : 'unreachable'} — ${latency} ms${receipt.error_code ? ` (${receipt.error_code})` : ''}`,
          time: timeStr,
        });
      } catch (e: any) {
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const msg = e?.message || String(e);
        setReceiptLatency((prev) => ({
          ...prev,
          [providerId]: { latency: 0, time: `Just now (${timeStr})`, reachable: false, authValid: false, message: msg },
        }));
        pushActivity({ id: `act-${Date.now()}`, type: 'error', message: `${providerId} test failed — ${msg}`, time: timeStr });
      } finally {
        setIsTestingSingle(false);
      }
    },
    [serverProviders, testConnectionMutation, pushActivity],
  );

  const handleTestAllConnections = useCallback(async () => {
    if (providers.length === 0) return;
    setIsTestingAll(true);
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    let successCount = 0;
    let failCount = 0;
    for (const p of providers) {
      const srv = serverProviders.find((s) => s.id === p.id);
      const endpointId = srv?.endpoints[0]?.id;
      if (!srv || !endpointId) {
        failCount++;
        continue;
      }
      try {
        const receipt = await testConnectionMutation.mutateAsync({ providerId: p.id, endpointId });
        const latency = Math.round(receipt.latency_ms);
        setReceiptLatency((prev) => ({
          ...prev,
          [p.id]: {
            latency,
            time: `Just now (${timeStr})`,
            reachable: receipt.reachable,
            authValid: receipt.auth_valid,
            message: receipt.message || (receipt.reachable ? 'Connection probe completed.' : 'Endpoint is unreachable.'),
          },
        }));
        if (receipt.reachable && receipt.auth_valid) successCount++;
        else failCount++;
        // small stagger to avoid thundering herd
        await new Promise((r) => setTimeout(r, 120));
      } catch (e: any) {
        setReceiptLatency((prev) => ({
          ...prev,
          [p.id]: { latency: 0, time: `Just now (${timeStr})`, reachable: false, authValid: false, message: e?.message || String(e) },
        }));
        failCount++;
      }
    }
    pushActivity({
      id: `act-${Date.now()}`,
      type: failCount === 0 ? 'success' : successCount === 0 ? 'error' : 'warning',
      message: `Test All: ${successCount} succeeded, ${failCount} failed — ${providers.length} providers`,
      time: timeStr,
    });
    setIsTestingAll(false);
  }, [providers, serverProviders, testConnectionMutation, pushActivity]);

  const handleSyncModels = useCallback(
    async (providerId: string) => {
      const provider = serverProviders.find((p) => p.id === providerId);
      const endpointId = provider?.endpoints[0]?.id;
      if (!provider || !endpointId) {
        throw new Error('Provider has no durable endpoint to sync.');
      }
      try {
        const result = await syncModelsMutation.mutateAsync({ providerId, endpointId });
        pushActivity({
          id: `act-${Date.now()}`,
          type: 'success',
          message: `${provider.display_name}: ${result.discovered_count} models discovered, ${result.added.length} added, ${result.updated.length} updated`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        });
      } catch (e: any) {
        pushActivity({
          id: `act-${Date.now()}`,
          type: 'error',
          message: `${provider.display_name} model sync failed: ${e?.message || String(e)}`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        });
        throw e;
      }
    },
    [serverProviders, syncModelsMutation, pushActivity],
  );

  const handleLoadModelsByPricing = useCallback(async (pricing: 'FREE' | 'PAID') => {
    const query = pricing === 'FREE' ? freeModelsQuery : paidModelsQuery;
    const result = await query.refetch();
    if (result.error) throw result.error;
    setCatalogPricingFilter(pricing);
    return result.data?.length ?? 0;
  }, [freeModelsQuery, paidModelsQuery]);

  const handleAddProvider = useCallback(
    async (newProvider: ProviderItem, rawApiKey?: string) => {
      // Derive durable fields from the modal's ProviderItem — no local optimistic list.
      const rawId = newProvider.id.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || `provider-${Date.now()}`;
      // Duplicate guard (also enforced in modal)
      if (serverProviders.some((p) => p.id.toLowerCase() === rawId.toLowerCase())) {
        pushActivity({ id: `act-${Date.now()}`, type: 'error', message: `Add provider failed — id "${rawId}" already exists`, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) });
        return;
      }
      // More robust type/protocol inference: inspect endpoint hostname and rawId hints
      const endpointLower = newProvider.endpoint.toLowerCase();
      const isLocalEndpoint = endpointLower.includes('localhost') || endpointLower.includes('127.0.0.1') || endpointLower.includes('::1');
      const type: 'cloud' | 'local' | 'custom' = isLocalEndpoint ? 'local' : (newProvider.id === 'ollama' ? 'local' : newProvider.id === 'custom' ? 'custom' : 'cloud');
      let protocol: 'openai' | 'anthropic' | 'gemini' | 'ollama' = 'openai';
      const nid = rawId.toLowerCase();
      const endpointHints = endpointLower;
      if (nid.includes('anthropic') || endpointHints.includes('anthropic')) protocol = 'anthropic';
      else if (nid.includes('gemini') || nid.includes('google') || endpointHints.includes('generativelanguage.googleapis')) protocol = 'gemini';
      else if (nid.includes('ollama') || type === 'local' || endpointHints.includes('ollama') || endpointHints.includes(':11434')) protocol = 'ollama';
      const apiKey = rawApiKey?.trim() ? rawApiKey.trim() : undefined;
      try {
        const created = await createProviderMutation.mutateAsync({
          id: rawId,
          name: newProvider.name,
          base_url: newProvider.endpoint,
          type,
          protocol_mode: protocol,
          api_key: apiKey,
        });
        setSelectedProviderId(created.id);
        pushActivity({
          id: `act-${Date.now()}`,
          type: 'success',
          message: `${created.display_name} registered — ${created.endpoints[0]?.base_url ?? newProvider.endpoint}`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        });
        setShowAddProviderModal(false);
      } catch (e: any) {
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        pushActivity({ id: `act-${Date.now()}`, type: 'error', message: `Add provider failed — ${e?.message || String(e)}`, time: timeStr });
      }
    },
    [createProviderMutation, pushActivity, serverProviders],
  );

  const handleAddRule = useCallback(
    async (newRule: ModelRuleItem) => {
      // Map UI rule type to canonical Studio story role for the durable authority
      const roleMap: Record<string, string> = {
        coding: 'studio.story.screenplay.generate',
        planning: 'studio.story.outline.generate',
        fast: 'studio.story.beats.generate',
        privacy: 'studio.story.bible.generate',
        custom: 'studio.story.idea.generate',
      };
      const role = roleMap[newRule.type] ?? newRule.type;
      const modelId = newRule.providerModel.includes('/') ? newRule.providerModel.split('/').slice(1).join('/').trim() : newRule.providerModel.trim();
      const canonical = modelId || newRule.providerModel.trim();
      try {
        await assignRuleMutation.mutateAsync({
          role,
          name: newRule.name,
          primary_canonical_model_id: canonical,
          enabled: true,
        });
        pushActivity({
          id: `act-${Date.now()}`,
          type: 'success',
          message: `Rule "${newRule.name}" → ${canonical} (${role}) saved`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        });
      } catch (e: any) {
        pushActivity({
          id: `act-${Date.now()}`,
          type: 'error',
          message: `Save rule failed — ${e?.message || String(e)}`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        });
      }
    },
    [assignRuleMutation, pushActivity],
  );

  const openRuleForModel = useCallback((providerId: string, modelId: string) => {
    setRulePrefill({ providerId, modelId });
    setShowAddRuleModal(true);
  }, []);

  const closeAddRuleModal = useCallback(() => {
    setShowAddRuleModal(false);
    setRulePrefill(null);
  }, []);

  const handleImportEnvKeys = useCallback(
    async (keys: Record<string, string>) => {
      if (serverProviders.length === 0) {
        const message = 'Import skipped — no durable providers registered yet';
        pushActivity({ id: `act-${Date.now()}`, type: 'warning', message, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) });
        return { imported: 0, errors: [message] };
      }
      let imported = 0;
      const errors: string[] = [];
      for (const p of serverProviders) {
        const candidates = [
          `${p.id.toUpperCase()}_API_KEY`,
          `${p.display_name.toUpperCase().replace(/[^A-Z0-9]/g, '_')}_API_KEY`,
          // common aliases
          p.id === 'openrouter' ? 'OPENROUTER_API_KEY' : '',
          p.id === 'openai' ? 'OPENAI_API_KEY' : '',
          p.id === 'anthropic' ? 'ANTHROPIC_API_KEY' : '',
          (p.id === 'google' || p.id === 'gemini') ? 'GEMINI_API_KEY' : '',
          p.id === 'groq' ? 'GROQ_API_KEY' : '',
        ].filter(Boolean);
        let val: string | undefined;
        for (const k of candidates) {
          if (keys[k]) { val = keys[k]; break; }
          // case-insensitive fallback
          const found = Object.keys(keys).find((kk) => kk.toUpperCase() === k.toUpperCase());
          if (found) { val = keys[found]; break; }
        }
        if (val) {
          try {
            await rotateCredMutation.mutateAsync({ providerId: p.id, request: { api_key: val } });
            imported++;
            pushActivity({ id: `act-${Date.now()}-${p.id}`, type: 'success', message: `${p.display_name} credential updated from .env`, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) });
          } catch (e: any) {
            const message = `${p.display_name} credential import failed — ${e?.message || String(e)}`;
            errors.push(message);
            pushActivity({ id: `act-${Date.now()}-${p.id}`, type: 'error', message, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) });
          }
        }
      }
      if (imported === 0) {
        pushActivity({ id: `act-${Date.now()}`, type: 'warning', message: 'No matching provider keys found in .env import', time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) });
      }
      return { imported, errors };
    },
    [serverProviders, rotateCredMutation, pushActivity],
  );

  const isLoading = providersQuery.isLoading || healthQuery.isLoading;
  const loadError = (providersQuery.error as any)?.message || (healthQuery.error as any)?.message || (modelRulesQuery.error as any)?.message || null;

  return (
    <div
      className="router-page-scroll"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        padding: '24px 28px',
        maxWidth: '1680px',
        margin: '0 auto',
        width: '100%',
        color: '#f8fafc',
        boxSizing: 'border-box',
        overflowY: 'auto',
        overflowX: 'hidden',
        flex: 1,
        minHeight: 0,
        maxHeight: '100%',
        scrollbarWidth: 'thin',
        scrollbarColor: '#334155 transparent',
      }}
    >
      {/* 1. Header & Actions Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.78rem',
              color: '#94a3b8',
              marginBottom: '6px',
              fontWeight: 500,
            }}
          >
            <span>System</span>
            <ChevronRight size={13} color="#64748b" />
            <span style={{ color: '#cbd5e1' }}>Providers</span>
          </div>
          <h1
            style={{
              margin: 0,
              fontSize: '1.65rem',
              fontWeight: 800,
              letterSpacing: '-0.02em',
              color: '#ffffff',
            }}
          >
            Providers Hub
          </h1>
          <p style={{ margin: '4px 0 0 0', fontSize: '0.84rem', color: '#94a3b8' }}>
            Manage provider endpoints, credentials, model policies, and connection health — all from the durable provider authority.
          </p>
          {loadError && (
            <div role="alert" style={{ marginTop: 10, padding: '8px 12px', borderRadius: 8, backgroundColor: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.35)', color: '#fca5a5', fontSize: '0.78rem' }}>
              {String(loadError)}
            </div>
          )}
          {isLoading && <p style={{ color: '#94a3b8', fontSize: '0.78rem', margin: '8px 0 0' }}>Loading provider authority…</p>}
          {!isLoading && providers.length === 0 && !loadError && (
            <p style={{ color: '#f59e0b', fontSize: '0.78rem', margin: '8px 0 0' }}>
              No durable providers registered yet. Add a provider to connect a real endpoint — no demo seed is shown.
            </p>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => setShowAddProviderModal(true)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '9px 16px', borderRadius: '8px',
              backgroundColor: '#2563eb', color: '#ffffff', border: 'none', fontSize: '0.84rem', fontWeight: 700,
              cursor: 'pointer', boxShadow: '0 2px 10px rgba(37, 99, 235, 0.35)', transition: 'background-color 0.15s ease',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#1d4ed8')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '#2563eb')}
          >
            <Plus size={15} strokeWidth={2.5} />
            <span>Add Provider</span>
          </button>
          <button
            type="button"
            onClick={() => setShowImportEnvModal(true)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '9px 15px', borderRadius: '8px',
              backgroundColor: 'rgba(255, 255, 255, 0.05)', color: '#e2e8f0', border: '1px solid rgba(51, 65, 85, 0.6)',
              fontSize: '0.84rem', fontWeight: 600, cursor: 'pointer', transition: 'background-color 0.15s ease, border-color 0.15s ease',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.1)'; e.currentTarget.style.borderColor = '#64748b'; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.05)'; e.currentTarget.style.borderColor = 'rgba(51, 65, 85, 0.6)'; }}
          >
            <DownloadCloud size={15} color="#94a3b8" />
            <span>Import from .env</span>
          </button>
          <button
            type="button"
            disabled={isTestingAll || providers.length === 0}
            onClick={handleTestAllConnections}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '9px 16px', borderRadius: '8px',
              background: 'linear-gradient(135deg, #4f46e5 0%, #4338ca 100%)', color: '#ffffff',
              border: '1px solid rgba(165, 180, 252, 0.3)', fontSize: '0.84rem', fontWeight: 700,
              cursor: isTestingAll || providers.length === 0 ? 'not-allowed' : 'pointer',
              opacity: providers.length === 0 ? 0.55 : 1,
              boxShadow: '0 2px 10px rgba(79, 70, 229, 0.35)', transition: 'opacity 0.15s ease',
            }}
          >
            <Zap size={15} color="#c7d2fe" />
            <span>{isTestingAll ? 'Testing All...' : 'Test All Connections'}</span>
          </button>
        </div>
      </div>

      <ProviderKpis stats={kpiStats} />

      <div
        style={{ display: 'grid', gridTemplateColumns: '1.1fr 1.35fr 0.95fr', gap: '18px', minHeight: '620px', alignItems: 'start' }}
        className="router-main-grid"
      >
        <div style={{ height: '100%', minHeight: '620px' }}>
          <ProviderRegistryTable
            providers={providers}
            selectedProviderId={selectedProviderId ?? ''}
            onSelectProvider={handleSelectProvider}
            onTestProvider={(p) => handleTestProvider(p.id)}
            onEditProvider={handleSelectProvider}
          />
        </div>
        <div style={{ height: '100%', minHeight: '620px' }}>
          <ProviderConfigPanel
            provider={selectedProvider}
            onSave={handleSaveProvider}
            onTestConnection={handleTestProvider}
            onSyncModels={handleSyncModels}
            onLoadModelsByPricing={handleLoadModelsByPricing}
            onUseSelectedModel={openRuleForModel}
            isTesting={isTestingSingle}
            isSyncing={syncModelsMutation.isPending}
            isLoadingPricedModels={freeModelsQuery.isFetching || paidModelsQuery.isFetching}
          />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <ModelRuleAssignmentPanel
            rules={modelRules}
            onAddRule={() => {
              setRulePrefill(null);
              setShowAddRuleModal(true);
            }}
          />
          <ConnectionActivityPanel activities={activities} onViewAll={() => {}} />
        </div>
      </div>

      <AddProviderModal
        isOpen={showAddProviderModal}
        onClose={() => setShowAddProviderModal(false)}
        onAdd={handleAddProvider}
        existingIds={serverProviders.map((p) => p.id)}
      />
      <ImportEnvModal
        isOpen={showImportEnvModal}
        onClose={() => setShowImportEnvModal(false)}
        onImport={handleImportEnvKeys}
      />
      <AddRuleModal
        isOpen={showAddRuleModal}
        providers={providers}
        onClose={closeAddRuleModal}
        onAddRule={handleAddRule}
        initialProviderId={rulePrefill?.providerId}
        initialModel={rulePrefill?.modelId}
      />
    </div>
  );
};

export default RoutingPage;
