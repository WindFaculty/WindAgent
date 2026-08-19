import React, { useState } from 'react';
import { Plus, Upload, Activity } from 'lucide-react';
import { ProviderKpis, type ProviderKpiStats } from '../components/ProviderKpis';
import { ProviderRegistryTable, type ProviderItem } from '../components/ProviderRegistryTable';
import { ProviderConfigPanel } from '../components/ProviderConfigPanel';
import { ModelRuleAssignmentPanel, type ModelRuleItem } from '../components/ModelRuleAssignmentPanel';
import { ConnectionActivityPanel, type ActivityItem } from '../components/ConnectionActivityPanel';
import { AddProviderModal } from '../components/AddProviderModal';
import { ImportEnvModal } from '../components/ImportEnvModal';
import { AddRuleModal } from '../components/AddRuleModal';

// Initial Mock Data corresponding accurately to the requested UI
const INITIAL_PROVIDERS: ProviderItem[] = [
  {
    id: 'openrouter',
    name: 'OpenRouter',
    subName: 'OpenRouter',
    endpoint: 'https://openrouter.ai/api/v1',
    credentialsStatus: 'valid',
    modelsCount: 14,
    ruleSet: 'Coding',
    status: 'connected',
    apiKeyMasked: 'sk-or-v1-••••••••••••••••••••••••••••••••',
    orgId: 'org_1a2b3c4d5e6f',
    timeoutSec: 30,
    maxRetries: 3,
    models: ['deepseek-v4-flash', 'qwen2.5-coder', 'meta-llama/llama-3.5-70b'],
    perModelRules: [
      { model: 'deepseek-v4-flash', rule: 'Coding' },
      { model: 'qwen2.5-coder', rule: 'General' },
      { model: 'meta-llama/llama-3.5-70b', rule: 'Fast Inference' },
    ],
    fallbackProvider: 'OpenAI',
    maxTokens: 4096,
    streaming: true,
    enableCache: true,
    lastTestLatency: 289,
    lastTestTime: 'Just now (16:23)',
  },
  {
    id: 'google-ai-studio',
    name: 'Google AI Studio',
    subName: 'Google',
    endpoint: 'https://generativelanguage.googleapis.com',
    credentialsStatus: 'valid',
    modelsCount: 9,
    ruleSet: 'Planning',
    status: 'connected',
    apiKeyMasked: 'AIzaSy••••••••••••••••••••••••••••••••',
    orgId: '',
    timeoutSec: 30,
    maxRetries: 3,
    models: ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-1.5-pro'],
    fallbackProvider: 'Anthropic',
    maxTokens: 8192,
    streaming: true,
    enableCache: true,
    lastTestLatency: 398,
    lastTestTime: 'May 14, 2025 10:41 AM',
  },
  {
    id: 'groq',
    name: 'Groq',
    subName: 'Groq',
    endpoint: 'https://api.groq.com/openai/v1',
    credentialsStatus: 'warning',
    modelsCount: 8,
    ruleSet: 'Fast inference',
    status: 'warning',
    apiKeyMasked: 'gsk_••••••••••••••••••••••••••••••••',
    orgId: '',
    timeoutSec: 15,
    maxRetries: 2,
    models: ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768'],
    fallbackProvider: 'OpenRouter',
    maxTokens: 4096,
    streaming: true,
    enableCache: false,
    lastTestLatency: 86,
    lastTestTime: 'May 14, 2025 10:39 AM',
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    subName: 'Anthropic',
    endpoint: 'https://api.anthropic.com',
    credentialsStatus: 'valid',
    modelsCount: 7,
    ruleSet: 'General',
    status: 'connected',
    apiKeyMasked: 'sk-ant-api03-••••••••••••••••••••••••••••••••',
    orgId: '',
    timeoutSec: 60,
    maxRetries: 3,
    models: ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022'],
    fallbackProvider: 'Google AI Studio',
    maxTokens: 4096,
    streaming: true,
    enableCache: true,
    lastTestLatency: 440,
    lastTestTime: 'May 14, 2025 10:37 AM',
  },
  {
    id: 'ollama-local',
    name: 'Ollama Local',
    subName: 'Local',
    endpoint: 'http://localhost:11434',
    credentialsStatus: 'valid',
    modelsCount: 6,
    ruleSet: 'Local privacy',
    status: 'connected',
    apiKeyMasked: 'None (Local Loopback)',
    orgId: '',
    timeoutSec: 120,
    maxRetries: 1,
    models: ['qwen2.5-coder', 'llama3.2:3b', 'deepseek-r1:14b'],
    fallbackProvider: 'None',
    maxTokens: 4096,
    streaming: true,
    enableCache: false,
    lastTestLatency: 58,
    lastTestTime: 'May 14, 2025 10:36 AM',
  },
  {
    id: 'openai',
    name: 'OpenAI',
    subName: 'OpenAI',
    endpoint: 'https://api.openai.com/v1',
    credentialsStatus: 'offline',
    modelsCount: 4,
    ruleSet: 'General',
    status: 'offline',
    apiKeyMasked: 'sk-proj-••••••••••••••••••••••••••••••••',
    orgId: '',
    timeoutSec: 30,
    maxRetries: 3,
    models: ['gpt-4o', 'gpt-4o-mini', 'o3-mini'],
    fallbackProvider: 'Anthropic',
    maxTokens: 4096,
    streaming: true,
    enableCache: true,
    lastTestLatency: 0,
    lastTestTime: 'May 14, 2025 10:34 AM',
  },
];

const INITIAL_MODEL_RULES: ModelRuleItem[] = [
  {
    id: 'rule-coding',
    name: 'Coding',
    providerModel: 'OpenRouter / deepseek-v4-flash',
    type: 'coding',
    isPrimary: true,
  },
  {
    id: 'rule-planning',
    name: 'Planning',
    providerModel: 'Google AI Studio / gemini-2.5-pro',
    type: 'planning',
    isPrimary: true,
  },
  {
    id: 'rule-fast',
    name: 'Fast inference',
    providerModel: 'Groq / llama-3.3-70b',
    type: 'fast',
    isPrimary: true,
  },
  {
    id: 'rule-privacy',
    name: 'Local privacy',
    providerModel: 'Ollama / qwen2.5-coder',
    type: 'privacy',
    isPrimary: true,
  },
];

const INITIAL_ACTIVITIES: ActivityItem[] = [
  {
    id: 'act-1',
    type: 'success',
    message: 'OpenRouter tested successfully - 214 ms',
    time: '10:42 AM',
  },
  {
    id: 'act-2',
    type: 'success',
    message: 'Google AI Studio tested successfully - 398 ms',
    time: '10:41 AM',
  },
  {
    id: 'act-3',
    type: 'error',
    message: 'Groq authentication failed - invalid key',
    time: '10:39 AM',
  },
  {
    id: 'act-4',
    type: 'warning',
    message: 'Anthropic rate limit approaching (80%)',
    time: '10:37 AM',
  },
  {
    id: 'act-5',
    type: 'success',
    message: 'Ollama reachable on localhost - 58 ms',
    time: '10:36 AM',
  },
  {
    id: 'act-6',
    type: 'error',
    message: 'OpenAI connection failed - timeout',
    time: '10:34 AM',
  },
];

export const RoutingPage: React.FC = () => {
  const [providers, setProviders] = useState<ProviderItem[]>(INITIAL_PROVIDERS);
  const [selectedProviderId, setSelectedProviderId] = useState<string>('openrouter');
  const [modelRules, setModelRules] = useState<ModelRuleItem[]>(INITIAL_MODEL_RULES);
  const [activities, setActivities] = useState<ActivityItem[]>(INITIAL_ACTIVITIES);

  // Modals state
  const [isAddProviderOpen, setIsAddProviderOpen] = useState(false);
  const [isImportEnvOpen, setIsImportEnvOpen] = useState(false);
  const [isAddRuleOpen, setIsAddRuleOpen] = useState(false);

  // Connection testing state
  const [isTestingCurrent, setIsTestingCurrent] = useState(false);
  const [isTestingAll, setIsTestingAll] = useState(false);
  const [testAllProgress, setTestAllProgress] = useState<string | null>(null);

  const selectedProvider = providers.find((p) => p.id === selectedProviderId) || providers[0] || null;

  // Calculate top KPI numbers dynamically
  const connectedCount = providers.filter((p) => p.status === 'connected').length;
  const totalModelsCount = providers.reduce((acc, p) => acc + p.modelsCount, 0);
  const healthyEndpointsCount = providers.filter((p) => p.credentialsStatus === 'valid').length;
  const avgLatency = Math.round(
    providers
      .filter((p) => p.lastTestLatency && p.lastTestLatency > 0)
      .reduce((acc, p) => acc + (p.lastTestLatency || 0), 0) /
      (providers.filter((p) => p.lastTestLatency && p.lastTestLatency > 0).length || 1)
  );

  const kpiStats: ProviderKpiStats = {
    connectedProviders: connectedCount,
    totalProviders: providers.length,
    activeModels: totalModelsCount || 48,
    healthyEndpoints: healthyEndpointsCount,
    lastSyncTime: '2m ago',
    lastSyncFormatted: 'May 14, 2025 10:42 AM',
    avgResponseTimeMs: avgLatency || 312,
  };

  const handleSelectProvider = (provider: ProviderItem) => {
    setSelectedProviderId(provider.id);
  };

  const handleSaveProviderConfig = (updated: ProviderItem) => {
    setProviders((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  };

  const handleTestSingleProvider = async (providerId: string) => {
    setIsTestingCurrent(true);
    const target = providers.find((p) => p.id === providerId);
    if (!target) return;

    // Simulate realistic network roundtrip
    await new Promise((res) => setTimeout(res, 450));

    const simulatedLatency = Math.floor(Math.random() * 200) + 120;
    const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setProviders((prev) =>
      prev.map((p) =>
        p.id === providerId
          ? {
              ...p,
              status: 'connected',
              credentialsStatus: 'valid',
              lastTestLatency: simulatedLatency,
              lastTestTime: `Just now (${nowTime})`,
            }
          : p
      )
    );

    // Append to connection activity feed
    const newAct: ActivityItem = {
      id: `act-${Date.now()}`,
      type: 'success',
      message: `${target.name} tested successfully - ${simulatedLatency} ms`,
      time: nowTime,
    };
    setActivities((prev) => [newAct, ...prev.slice(0, 7)]);
    setIsTestingCurrent(false);
  };

  const handleTestAllConnections = async () => {
    setIsTestingAll(true);
    setTestAllProgress('Pinging all provider endpoints in parallel...');

    await new Promise((res) => setTimeout(res, 800));

    const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setProviders((prev) =>
      prev.map((p) => {
        if (p.id === 'openai') {
          return {
            ...p,
            status: 'offline',
            credentialsStatus: 'offline',
            lastTestLatency: 0,
            lastTestTime: `Just now (${nowTime})`,
          };
        }
        const lat = Math.floor(Math.random() * 250) + 80;
        return {
          ...p,
          status: 'connected',
          credentialsStatus: 'valid',
          lastTestLatency: lat,
          lastTestTime: `Just now (${nowTime})`,
        };
      })
    );

    setTestAllProgress('All 6 connections probed: 5 healthy, 1 offline.');
    setTimeout(() => {
      setTestAllProgress(null);
      setIsTestingAll(false);
    }, 2000);
  };

  const handleAddProvider = (newProvider: ProviderItem) => {
    setProviders((prev) => [newProvider, ...prev]);
    setSelectedProviderId(newProvider.id);
  };

  const handleImportEnv = (detectedKeys: Record<string, string>) => {
    setProviders((prev) =>
      prev.map((p) => {
        const idLower = p.id.toLowerCase();
        let keyVal = '';
        if (idLower.includes('openrouter') && detectedKeys['OPENROUTER_API_KEY']) {
          keyVal = detectedKeys['OPENROUTER_API_KEY'];
        } else if (idLower.includes('openai') && detectedKeys['OPENAI_API_KEY']) {
          keyVal = detectedKeys['OPENAI_API_KEY'];
        } else if (idLower.includes('anthropic') && detectedKeys['ANTHROPIC_API_KEY']) {
          keyVal = detectedKeys['ANTHROPIC_API_KEY'];
        } else if ((idLower.includes('google') || idLower.includes('gemini')) && detectedKeys['GEMINI_API_KEY']) {
          keyVal = detectedKeys['GEMINI_API_KEY'];
        } else if (idLower.includes('groq') && detectedKeys['GROQ_API_KEY']) {
          keyVal = detectedKeys['GROQ_API_KEY'];
        }

        if (keyVal) {
          return {
            ...p,
            apiKeyMasked: `••••••••••••${keyVal.slice(-4)}`,
            credentialsStatus: 'valid',
            status: 'connected',
          };
        }
        return p;
      })
    );
  };

  const handleAddRule = (newRule: ModelRuleItem) => {
    setModelRules((prev) => [...prev, newRule]);
  };

  return (
    <div
      style={{
        padding: '24px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        maxWidth: '1800px',
        margin: '0 auto',
        fontFamily: 'var(--font-sans, sans-serif)',
        color: 'var(--text-main, #f8fafc)',
        minHeight: '100vh',
        boxSizing: 'border-box',
      }}
    >
      {/* Top Breadcrumb & Hero Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {/* Breadcrumb */}
          <div
            style={{
              fontSize: '0.76rem',
              color: '#64748b',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>System</span>
            <span>/</span>
            <span style={{ color: '#94a3b8' }}>Providers</span>
          </div>

          {/* Title & Subtitle */}
          <h1
            style={{
              margin: 0,
              fontSize: '1.75rem',
              fontWeight: 800,
              color: '#f8fafc',
              letterSpacing: '-0.025em',
            }}
          >
            Providers Hub
          </h1>
          <p
            style={{
              margin: 0,
              fontSize: '0.86rem',
              color: '#94a3b8',
              lineHeight: 1.4,
            }}
          >
            Manage provider endpoints, credentials, model policies, and connection health.
          </p>
        </div>

        {/* Header Action Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          {/* Add Provider Button */}
          <button
            type="button"
            onClick={() => setIsAddProviderOpen(true)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
              color: '#ffffff',
              border: '1px solid rgba(147, 197, 253, 0.3)',
              boxShadow: '0 2px 10px rgba(37, 99, 235, 0.35)',
              fontSize: '0.82rem',
              fontWeight: 700,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <Plus size={15} />
            <span>Add Provider</span>
          </button>

          {/* Import from .env Button */}
          <button
            type="button"
            onClick={() => setIsImportEnvOpen(true)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              borderRadius: '8px',
              backgroundColor: 'rgba(17, 24, 39, 0.8)',
              color: '#cbd5e1',
              border: '1px solid rgba(66, 71, 84, 0.5)',
              fontSize: '0.82rem',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <Upload size={14} color="#94a3b8" />
            <span>Import from .env</span>
          </button>

          {/* Test All Connections Button */}
          <button
            type="button"
            disabled={isTestingAll}
            onClick={handleTestAllConnections}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              borderRadius: '8px',
              backgroundColor: 'rgba(139, 92, 246, 0.12)',
              color: '#c4b5fd',
              border: '1px solid rgba(167, 139, 250, 0.35)',
              fontSize: '0.82rem',
              fontWeight: 600,
              cursor: isTestingAll ? 'wait' : 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <Activity size={14} color="#a78bfa" />
            <span>{isTestingAll ? 'Testing All...' : 'Test All Connections'}</span>
          </button>
        </div>
      </div>

      {/* Progress / Status banner if Testing All */}
      {testAllProgress && (
        <div
          style={{
            padding: '10px 16px',
            borderRadius: '8px',
            backgroundColor: 'rgba(59, 130, 246, 0.12)',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            color: '#93c5fd',
            fontSize: '0.80rem',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <Activity size={15} className="animate-spin" />
          <span>{testAllProgress}</span>
        </div>
      )}

      {/* Top 5 KPI Summary Cards */}
      <ProviderKpis stats={kpiStats} />

      {/* Main 3-Column Workspace Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(420px, 1.25fr) minmax(440px, 1.35fr) minmax(300px, 0.95fr)',
          gap: '20px',
          alignItems: 'stretch',
        }}
      >
        {/* Left Column: Provider Registry */}
        <div style={{ height: '100%', minHeight: '560px' }}>
          <ProviderRegistryTable
            providers={providers}
            selectedProviderId={selectedProviderId}
            onSelectProvider={handleSelectProvider}
            onTestProvider={(p) => handleTestSingleProvider(p.id)}
            onEditProvider={(p) => setSelectedProviderId(p.id)}
          />
        </div>

        {/* Center Column: Provider Configuration */}
        <div style={{ height: '100%', minHeight: '560px' }}>
          <ProviderConfigPanel
            provider={selectedProvider}
            onSave={handleSaveProviderConfig}
            onTestConnection={handleTestSingleProvider}
            isTesting={isTestingCurrent}
          />
        </div>

        {/* Right Column: Model Rule Assignment & Connection Activity */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <ModelRuleAssignmentPanel
            rules={modelRules}
            onAddRule={() => setIsAddRuleOpen(true)}
          />

          <ConnectionActivityPanel
            activities={activities}
            onViewAll={() => {}}
          />
        </div>
      </div>

      {/* Modals */}
      <AddProviderModal
        isOpen={isAddProviderOpen}
        onClose={() => setIsAddProviderOpen(false)}
        onAdd={handleAddProvider}
      />

      <ImportEnvModal
        isOpen={isImportEnvOpen}
        onClose={() => setIsImportEnvOpen(false)}
        onImport={handleImportEnv}
      />

      <AddRuleModal
        isOpen={isAddRuleOpen}
        onClose={() => setIsAddRuleOpen(false)}
        providers={providers}
        onAddRule={handleAddRule}
      />
    </div>
  );
};
export default RoutingPage;
