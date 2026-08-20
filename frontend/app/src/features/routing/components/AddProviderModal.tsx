import React, { useState } from 'react';
import { X, Plus, Server } from 'lucide-react';
import type { ProviderItem } from './ProviderRegistryTable';

interface AddProviderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (newProvider: ProviderItem) => void;
}

export const AddProviderModal: React.FC<AddProviderModalProps> = ({ isOpen, onClose, onAdd }) => {
  const [providerType, setProviderType] = useState('custom');
  const [name, setName] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [orgId, setOrgId] = useState('');
  const [ruleSet, setRuleSet] = useState('General');
  const [initialModel, setInitialModel] = useState('');

  if (!isOpen) return null;

  const handleSelectPreset = (preset: string) => {
    setProviderType(preset);
    if (preset === 'openrouter') {
      setName('OpenRouter');
      setEndpoint('https://openrouter.ai/api/v1');
      setInitialModel('deepseek/deepseek-r1, meta-llama/llama-3.3-70b-instruct');
      setRuleSet('Coding');
    } else if (preset === 'openai') {
      setName('OpenAI');
      setEndpoint('https://api.openai.com/v1');
      setInitialModel('gpt-4o, gpt-4o-mini, o3-mini');
      setRuleSet('General');
    } else if (preset === 'anthropic') {
      setName('Anthropic');
      setEndpoint('https://api.anthropic.com');
      setInitialModel('claude-3-5-sonnet-20241022, claude-3-5-haiku-20241022');
      setRuleSet('General');
    } else if (preset === 'gemini') {
      setName('Google AI Studio');
      setEndpoint('https://generativelanguage.googleapis.com');
      setInitialModel('gemini-2.5-pro, gemini-2.5-flash');
      setRuleSet('Planning');
    } else if (preset === 'groq') {
      setName('Groq');
      setEndpoint('https://api.groq.com/openai/v1');
      setInitialModel('llama-3.3-70b-versatile, mixtral-8x7b-32768');
      setRuleSet('Fast inference');
    } else if (preset === 'ollama') {
      setName('Ollama Local');
      setEndpoint('http://localhost:11434');
      setInitialModel('qwen2.5-coder:32b, llama3.2:3b');
      setRuleSet('Local privacy');
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !endpoint.trim()) return;

    const models = initialModel
      .split(',')
      .map((m) => m.trim())
      .filter(Boolean);

    const newProvider: ProviderItem = {
      id: name.toLowerCase().replace(/[^a-z0-9]/g, '-'),
      name: name.trim(),
      subName: providerType === 'custom' ? 'Custom Endpoint' : name.trim(),
      endpoint: endpoint.trim(),
      // A saved credential is configured, not validated. Only the server
      // test-connection receipt may promote connection/credential health.
      credentialsStatus: 'warning',
      modelsCount: models.length || 1,
      ruleSet: ruleSet,
      status: 'warning',
      apiKeyMasked: apiKey ? `••••••••••••${apiKey.slice(-4)}` : '••••••••••••••••••••••••',
      orgId: orgId.trim() || undefined,
      timeoutSec: 30,
      maxRetries: 3,
      models: models.length ? models : ['default-model'],
      fallbackProvider: 'None',
      maxTokens: 4096,
      streaming: true,
      enableCache: true,
      lastTestLatency: undefined,
      lastTestTime: undefined,
    };

    onAdd(newProvider);
    onClose();
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '20px',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '560px',
          backgroundColor: '#0f172a',
          borderRadius: '14px',
          border: '1px solid rgba(66, 71, 84, 0.6)',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.6)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '16px 20px',
            borderBottom: '1px solid rgba(66, 71, 84, 0.4)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Server size={18} color="#60a5fa" />
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#f8fafc' }}>
              Add AI Provider Endpoint
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer',
              padding: '4px',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSubmit} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Quick Presets */}
          <div>
            <label style={{ fontSize: '0.74rem', color: '#94a3b8', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
              Quick Provider Presets
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {[
                { id: 'openrouter', label: 'OpenRouter' },
                { id: 'gemini', label: 'Google Gemini' },
                { id: 'anthropic', label: 'Anthropic' },
                { id: 'openai', label: 'OpenAI' },
                { id: 'groq', label: 'Groq' },
                { id: 'ollama', label: 'Ollama' },
                { id: 'custom', label: 'Custom' },
              ].map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => handleSelectPreset(preset.id)}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '6px',
                    fontSize: '0.74rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    backgroundColor: providerType === preset.id ? 'rgba(59, 130, 246, 0.25)' : 'rgba(255, 255, 255, 0.05)',
                    color: providerType === preset.id ? '#60a5fa' : '#cbd5e1',
                    border: providerType === preset.id ? '1px solid #3b82f6' : '1px solid rgba(66, 71, 84, 0.4)',
                  }}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.3fr', gap: '12px' }}>
            <div>
              <label style={{ fontSize: '0.74rem', color: '#94a3b8', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
                Provider Name *
              </label>
              <input
                type="text"
                required
                placeholder="e.g. OpenRouter"
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(0, 0, 0, 0.4)',
                  border: '1px solid rgba(66, 71, 84, 0.6)',
                  color: '#f8fafc',
                  fontSize: '0.8rem',
                  outline: 'none',
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: '0.74rem', color: '#94a3b8', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
                Base URL / Endpoint *
              </label>
              <input
                type="text"
                required
                placeholder="https://..."
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(0, 0, 0, 0.4)',
                  border: '1px solid rgba(66, 71, 84, 0.6)',
                  color: '#f8fafc',
                  fontSize: '0.8rem',
                  fontFamily: 'var(--font-mono, monospace)',
                  outline: 'none',
                }}
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '12px' }}>
            <div>
              <label style={{ fontSize: '0.74rem', color: '#94a3b8', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
                API Key (Optional / Secret)
              </label>
              <input
                type="password"
                placeholder="sk-..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(0, 0, 0, 0.4)',
                  border: '1px solid rgba(66, 71, 84, 0.6)',
                  color: '#f8fafc',
                  fontSize: '0.8rem',
                  fontFamily: 'var(--font-mono, monospace)',
                  outline: 'none',
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: '0.74rem', color: '#94a3b8', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
                Default Rule Set
              </label>
              <select
                value={ruleSet}
                onChange={(e) => setRuleSet(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(0, 0, 0, 0.4)',
                  border: '1px solid rgba(66, 71, 84, 0.6)',
                  color: '#f8fafc',
                  fontSize: '0.8rem',
                  outline: 'none',
                }}
              >
                <option value="Coding">Coding</option>
                <option value="Planning">Planning</option>
                <option value="Fast inference">Fast inference</option>
                <option value="Local privacy">Local privacy</option>
                <option value="General">General</option>
              </select>
            </div>
          </div>

          <div>
            <label style={{ fontSize: '0.74rem', color: '#94a3b8', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
              Organization ID (Optional)
            </label>
            <input
              type="text"
              placeholder="org_..."
              value={orgId}
              onChange={(e) => setOrgId(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: '6px',
                backgroundColor: 'rgba(0, 0, 0, 0.4)',
                border: '1px solid rgba(66, 71, 84, 0.6)',
                color: '#f8fafc',
                fontSize: '0.8rem',
                fontFamily: 'var(--font-mono, monospace)',
                outline: 'none',
              }}
            />
          </div>

          <div>
            <label style={{ fontSize: '0.74rem', color: '#94a3b8', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
              Models List (Comma separated)
            </label>
            <input
              type="text"
              placeholder="e.g. model-1, model-2, model-3"
              value={initialModel}
              onChange={(e) => setInitialModel(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: '6px',
                backgroundColor: 'rgba(0, 0, 0, 0.4)',
                border: '1px solid rgba(66, 71, 84, 0.6)',
                color: '#f8fafc',
                fontSize: '0.8rem',
                fontFamily: 'var(--font-mono, monospace)',
                outline: 'none',
              }}
            />
          </div>

          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '10px',
              marginTop: '10px',
              paddingTop: '12px',
              borderTop: '1px solid rgba(66, 71, 84, 0.3)',
            }}
          >
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '8px 16px',
                borderRadius: '6px',
                backgroundColor: 'transparent',
                border: '1px solid rgba(66, 71, 84, 0.5)',
                color: '#94a3b8',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>

            <button
              type="submit"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 18px',
                borderRadius: '6px',
                background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
                border: 'none',
                color: '#ffffff',
                fontSize: '0.8rem',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              <Plus size={14} />
              <span>Add Provider</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
