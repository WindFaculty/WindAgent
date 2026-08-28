import React, { useState, useEffect } from 'react';
import { X, Plus, Layers } from 'lucide-react';
import type { ModelRuleItem } from './ModelRuleAssignmentPanel';
import type { ProviderItem } from './ProviderRegistryTable';

interface AddRuleModalProps {
  isOpen: boolean;
  onClose: () => void;
  providers: ProviderItem[];
  onAddRule: (rule: ModelRuleItem) => void;
  initialProviderId?: string;
  initialModel?: string;
}

export const AddRuleModal: React.FC<AddRuleModalProps> = ({
  isOpen,
  onClose,
  providers,
  onAddRule,
  initialProviderId,
  initialModel,
}) => {
  const [taskName, setTaskName] = useState('');
  const [taskType, setTaskType] = useState<ModelRuleItem['type']>('coding');
  const [selectedProvider, setSelectedProvider] = useState(providers[0]?.name || 'OpenRouter');
  const [modelName, setModelName] = useState('deepseek-r1');
  const [isPrimary, setIsPrimary] = useState(true);

  // Keep provider selection in sync when provider list loads async or changes
  useEffect(() => {
    if (!isOpen) return;
    if (providers.length === 0) return;
    const exists = providers.some((p) => p.name === selectedProvider || p.id === selectedProvider);
    if (!exists) {
      setSelectedProvider(providers[0].name);
      // Suggest first model from provider allowlist if available
      if (providers[0].models && providers[0].models.length > 0) {
        setModelName(providers[0].models[0].split('/').pop() || providers[0].models[0]);
      }
    }
  }, [providers, selectedProvider, isOpen]);

  useEffect(() => {
    if (!isOpen || !initialModel) return;
    const provider = providers.find((item) => item.id === initialProviderId);
    if (provider) setSelectedProvider(provider.name);
    setModelName(initialModel);
  }, [initialModel, initialProviderId, isOpen, providers]);

  useEffect(() => {
    if (!isOpen) {
      setTaskName('');
      setModelName('deepseek-r1');
      setIsPrimary(true);
      setTaskType('coding');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskName.trim() || !modelName.trim()) return;
    if (providers.length === 0) return;

    const resolvedProvider = providers.find((p) => p.name === selectedProvider || p.id === selectedProvider)?.name ?? selectedProvider;
    const newRule: ModelRuleItem = {
      id: `rule-${Date.now()}`,
      name: taskName.trim(),
      providerModel: `${resolvedProvider} / ${modelName.trim()}`,
      type: taskType,
      isPrimary,
    };

    onAddRule(newRule);
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
          maxWidth: '480px',
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
        {/* Header */}
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
            <Layers size={18} color="#60a5fa" />
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#f8fafc' }}>
              Assign Model Routing Rule
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

        {/* Body Form */}
        <form onSubmit={handleSubmit} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label style={{ fontSize: '0.74rem', color: '#94a3b8', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
              Task Category / Rule Name *
            </label>
            <input
              type="text"
              required
              placeholder="e.g. Reasoning, Image Generation, Code Review"
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
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

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={{ fontSize: '0.74rem', color: '#94a3b8', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
                Icon / Strategy Type
              </label>
              <select
                value={taskType}
                onChange={(e) => setTaskType(e.target.value as any)}
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
                <option value="coding">Coding (Code & Refactor)</option>
                <option value="planning">Planning (Architecture & Tree)</option>
                <option value="fast">Fast inference (Low Latency)</option>
                <option value="privacy">Local privacy (Zero Cloud)</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.74rem', color: '#94a3b8', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
                Assigned Provider
              </label>
              <select
                value={selectedProvider}
                onChange={(e) => {
                  const val = e.target.value;
                  setSelectedProvider(val);
                  const prov = providers.find((p) => p.name === val);
                  if (prov?.models?.[0]) setModelName(prov.models[0].split('/').pop() || prov.models[0]);
                }}
                disabled={providers.length === 0}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(0, 0, 0, 0.4)',
                  border: '1px solid rgba(66, 71, 84, 0.6)',
                  color: providers.length === 0 ? '#64748b' : '#f8fafc',
                  fontSize: '0.8rem',
                  outline: 'none',
                }}
              >
                {providers.length === 0 ? (
                  <option value="">No providers registered</option>
                ) : (
                  providers.map((p) => (
                    <option key={p.id} value={p.name}>
                      {p.name}
                    </option>
                  ))
                )}
              </select>
              {providers.length === 0 && (
                <span style={{ fontSize: '0.68rem', color: '#f59e0b', marginTop: '4px', display: 'block' }}>
                  Register a provider first.
                </span>
              )}
            </div>
          </div>

          <div>
            <label style={{ fontSize: '0.74rem', color: '#94a3b8', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
              Target Model Identifier
            </label>
            <input
              type="text"
              required
              placeholder="e.g. deepseek-v4-flash or gpt-4o"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
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

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <input
              type="checkbox"
              id="isPrimary"
              checked={isPrimary}
              onChange={(e) => setIsPrimary(e.target.checked)}
              style={{ cursor: 'pointer' }}
            />
            <label htmlFor="isPrimary" style={{ fontSize: '0.78rem', color: '#cbd5e1', cursor: 'pointer' }}>
              Mark as Primary Executor for this task
            </label>
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
              disabled={providers.length === 0 || !taskName.trim() || !modelName.trim()}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 18px',
                borderRadius: '6px',
                background: providers.length === 0 ? 'rgba(59,130,246,0.3)' : 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
                border: 'none',
                color: '#ffffff',
                fontSize: '0.8rem',
                fontWeight: 700,
                cursor: providers.length === 0 ? 'not-allowed' : 'pointer',
                opacity: providers.length === 0 ? 0.6 : 1,
              }}
            >
              <Plus size={14} />
              <span>Create Rule</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
