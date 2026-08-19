import React, { useState, useEffect } from 'react';
import {
  Eye,
  EyeOff,
  ChevronDown,
  ChevronUp,
  Save,
  Zap,
  CheckCircle2,
  X,
  Plus,
  Loader2,
  Gift,
  CreditCard,
  Info,
} from 'lucide-react';
import type { ProviderItem, ModelRuleMapping } from './ProviderRegistryTable';
import { ModelBrandIcon } from './ProviderIcons';

interface ProviderConfigPanelProps {
  provider: ProviderItem | null;
  onSave: (updated: ProviderItem) => void;
  onTestConnection: (providerId: string) => Promise<void>;
  isTesting?: boolean;
}

export const ProviderConfigPanel: React.FC<ProviderConfigPanelProps> = ({
  provider,
  onSave,
  onTestConnection,
  isTesting = false,
}) => {
  const [formData, setFormData] = useState<ProviderItem | null>(provider);
  const [showApiKey, setShowApiKey] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [newModelInput, setNewModelInput] = useState('');
  const [showAddModelDropdown, setShowAddModelDropdown] = useState(false);
  const [saveToast, setSaveToast] = useState(false);

  // Default initial per-model rules if not present
  const defaultPerModelRules: ModelRuleMapping[] = [
    { model: 'deepseek-v4-flash', rule: 'Coding' },
    { model: 'qwen2.5-coder', rule: 'General' },
    { model: 'meta-llama/llama-3.5-70b', rule: 'Fast Inference' },
  ];

  useEffect(() => {
    if (provider) {
      setFormData({
        ...provider,
        perModelRules: provider.perModelRules && provider.perModelRules.length > 0
          ? provider.perModelRules
          : defaultPerModelRules,
      });
      setShowApiKey(false);
    }
  }, [provider]);

  if (!formData) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          minHeight: '300px',
          backgroundColor: 'rgba(11, 19, 38, 0.85)',
          borderRadius: '14px',
          border: '1px solid rgba(66, 71, 84, 0.4)',
          color: '#64748b',
          fontSize: '0.85rem',
        }}
      >
        Select a provider from the registry to view and edit its configuration.
      </div>
    );
  }

  const handleInputChange = (field: keyof ProviderItem, value: any) => {
    setFormData((prev) => (prev ? { ...prev, [field]: value } : null));
  };

  const handleRemoveModel = (modelName: string) => {
    if (!formData) return;
    const nextModels = formData.models.filter((m) => m !== modelName);
    const nextPerModelRules = (formData.perModelRules || []).filter((r) => r.model !== modelName);
    setFormData({
      ...formData,
      models: nextModels,
      modelsCount: nextModels.length,
      perModelRules: nextPerModelRules,
    });
  };

  const handleAddModel = (modelName: string) => {
    if (!formData || !modelName.trim()) return;
    const trimmed = modelName.trim();
    if (!formData.models.includes(trimmed)) {
      const nextModels = [...formData.models, trimmed];
      const nextPerModelRules = [
        ...(formData.perModelRules || []),
        { model: trimmed, rule: 'General' },
      ];
      setFormData({
        ...formData,
        models: nextModels,
        modelsCount: nextModels.length,
        perModelRules: nextPerModelRules,
      });
    }
    setNewModelInput('');
    setShowAddModelDropdown(false);
  };

  const handleGetFreeModels = () => {
    if (!formData) return;
    const freeModels = [
      'deepseek/deepseek-r1:free',
      'meta-llama/llama-3.3-70b-instruct:free',
      'google/gemini-2.0-flash-exp:free',
      'qwen/qwen-2.5-coder-32b-instruct:free',
    ];
    const unique = Array.from(new Set([...formData.models, ...freeModels]));
    const nextPerModelRules = [...(formData.perModelRules || [])];
    freeModels.forEach((m) => {
      if (!nextPerModelRules.some((r) => r.model === m)) {
        nextPerModelRules.push({ model: m, rule: m.includes('coder') ? 'Coding' : 'Fast Inference' });
      }
    });
    setFormData({
      ...formData,
      models: unique,
      modelsCount: unique.length,
      perModelRules: nextPerModelRules,
    });
  };

  const handleGetPaidModels = () => {
    if (!formData) return;
    const paidModels = [
      'anthropic/claude-3.5-sonnet',
      'openai/gpt-4o',
      'google/gemini-2.5-pro',
      'deepseek/deepseek-chat',
    ];
    const unique = Array.from(new Set([...formData.models, ...paidModels]));
    const nextPerModelRules = [...(formData.perModelRules || [])];
    paidModels.forEach((m) => {
      if (!nextPerModelRules.some((r) => r.model === m)) {
        nextPerModelRules.push({ model: m, rule: m.includes('sonnet') ? 'Coding' : 'Planning' });
      }
    });
    setFormData({
      ...formData,
      models: unique,
      modelsCount: unique.length,
      perModelRules: nextPerModelRules,
    });
  };

  const handlePerModelRuleChange = (modelName: string, newRule: string) => {
    if (!formData) return;
    const currentRules = formData.perModelRules || defaultPerModelRules;
    const exists = currentRules.some((r) => r.model === modelName);
    let updatedRules: ModelRuleMapping[];

    if (exists) {
      updatedRules = currentRules.map((r) =>
        r.model === modelName ? { ...r, rule: newRule } : r
      );
    } else {
      updatedRules = [...currentRules, { model: modelName, rule: newRule }];
    }

    setFormData({ ...formData, perModelRules: updatedRules });
  };

  const handleSave = () => {
    if (!formData) return;
    onSave(formData);
    setSaveToast(true);
    setTimeout(() => setSaveToast(false), 2500);
  };

  const currentRules = formData.perModelRules && formData.perModelRules.length > 0
    ? formData.perModelRules
    : defaultPerModelRules;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'rgba(11, 19, 38, 0.85)',
        borderRadius: '14px',
        border: '1px solid rgba(66, 71, 84, 0.4)',
        backdropFilter: 'blur(16px)',
        overflow: 'hidden',
        height: '100%',
        position: 'relative',
      }}
    >
      {/* Toast Notification */}
      {saveToast && (
        <div
          style={{
            position: 'absolute',
            top: '16px',
            right: '16px',
            backgroundColor: 'rgba(16, 185, 129, 0.95)',
            color: '#ffffff',
            padding: '8px 14px',
            borderRadius: '8px',
            boxShadow: '0 4px 16px rgba(0, 0, 0, 0.4)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '0.78rem',
            fontWeight: 600,
            zIndex: 50,
          }}
        >
          <CheckCircle2 size={14} /> Changes saved successfully!
        </div>
      )}

      {/* Header Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px 18px',
          borderBottom: '1px solid rgba(66, 71, 84, 0.3)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h2
            style={{
              margin: 0,
              fontSize: '1rem',
              fontWeight: 700,
              color: 'var(--text-main, #f8fafc)',
              letterSpacing: '-0.01em',
            }}
          >
            Provider Configuration
          </h2>

          <span
            style={{
              fontSize: '0.72rem',
              fontWeight: 600,
              padding: '2px 8px',
              borderRadius: '6px',
              backgroundColor: 'rgba(59, 130, 246, 0.15)',
              color: '#60a5fa',
              border: '1px solid rgba(59, 130, 246, 0.3)',
            }}
          >
            {formData.name}
          </span>
        </div>

        <button
          type="button"
          onClick={() => setIsCollapsed(!isCollapsed)}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#94a3b8',
            cursor: 'pointer',
            padding: '4px',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          {isCollapsed ? <ChevronDown size={18} /> : <ChevronUp size={18} />}
        </button>
      </div>

      {/* Form Content */}
      {!isCollapsed && (
        <div
          style={{
            padding: '18px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            overflowY: 'auto',
            flex: 1,
          }}
        >
          {/* Row 1: Provider Name & Base URL */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1.3fr',
              gap: '14px',
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
                Provider Name
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => handleInputChange('name', e.target.value)}
                style={{
                  backgroundColor: 'rgba(17, 24, 39, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  color: '#f8fafc',
                  fontSize: '0.82rem',
                  outline: 'none',
                }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
                Base URL / Endpoint
              </label>
              <input
                type="text"
                value={formData.endpoint}
                onChange={(e) => handleInputChange('endpoint', e.target.value)}
                style={{
                  backgroundColor: 'rgba(17, 24, 39, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  color: '#f8fafc',
                  fontSize: '0.82rem',
                  fontFamily: 'var(--font-mono, monospace)',
                  outline: 'none',
                }}
              />
            </div>
          </div>

          {/* Row 2: API Key & Organization ID */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1.4fr 1fr',
              gap: '14px',
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
                API Key
              </label>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  backgroundColor: 'rgba(17, 24, 39, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  padding: '0 8px 0 12px',
                }}
              >
                <input
                  type={showApiKey ? 'text' : 'password'}
                  value={formData.apiKeyMasked}
                  onChange={(e) => handleInputChange('apiKeyMasked', e.target.value)}
                  style={{
                    backgroundColor: 'transparent',
                    border: 'none',
                    padding: '8px 0',
                    color: '#f8fafc',
                    fontSize: '0.82rem',
                    fontFamily: 'var(--font-mono, monospace)',
                    outline: 'none',
                    width: '100%',
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#94a3b8',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    fontSize: '0.72rem',
                    padding: '4px 6px',
                    borderRadius: '4px',
                  }}
                >
                  {showApiKey ? <EyeOff size={13} /> : <Eye size={13} />}
                  <span>{showApiKey ? 'Hide' : 'Reveal'}</span>
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
                Organization / Project ID (Optional)
              </label>
              <input
                type="text"
                placeholder="org_..."
                value={formData.orgId || ''}
                onChange={(e) => handleInputChange('orgId', e.target.value)}
                style={{
                  backgroundColor: 'rgba(17, 24, 39, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  color: '#f8fafc',
                  fontSize: '0.82rem',
                  fontFamily: 'var(--font-mono, monospace)',
                  outline: 'none',
                }}
              />
            </div>
          </div>

          {/* Row 3: Timeout & Max Retries */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '14px',
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
                Timeout (s)
              </label>
              <select
                value={formData.timeoutSec}
                onChange={(e) => handleInputChange('timeoutSec', Number(e.target.value))}
                style={{
                  backgroundColor: 'rgba(17, 24, 39, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  color: '#f8fafc',
                  fontSize: '0.82rem',
                  outline: 'none',
                  cursor: 'pointer',
                }}
              >
                <option value={10}>10</option>
                <option value={15}>15</option>
                <option value={30}>30</option>
                <option value={60}>60</option>
                <option value={120}>120</option>
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
                Max Retries
              </label>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  backgroundColor: 'rgba(17, 24, 39, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  padding: '4px',
                  justifyContent: 'space-between',
                }}
              >
                <button
                  type="button"
                  onClick={() =>
                    handleInputChange('maxRetries', Math.max(0, formData.maxRetries - 1))
                  }
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.05)',
                    border: 'none',
                    color: '#94a3b8',
                    width: '28px',
                    height: '26px',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 700,
                  }}
                >
                  -
                </button>
                <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#f8fafc' }}>
                  {formData.maxRetries}
                </span>
                <button
                  type="button"
                  onClick={() =>
                    handleInputChange('maxRetries', Math.min(10, formData.maxRetries + 1))
                  }
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.05)',
                    border: 'none',
                    color: '#94a3b8',
                    width: '28px',
                    height: '26px',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 700,
                  }}
                >
                  +
                </button>
              </div>
            </div>
          </div>

          {/* Row 4: Model Allowlist with Get Free Models, Get Paid Models, and Add Model Buttons */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
                Model Allowlist
              </label>

              {/* Action Buttons on right */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  type="button"
                  onClick={handleGetFreeModels}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '4px 10px',
                    borderRadius: '6px',
                    backgroundColor: 'rgba(16, 185, 129, 0.12)',
                    border: '1px solid rgba(16, 185, 129, 0.35)',
                    color: '#34d399',
                    fontSize: '0.74rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  <Gift size={13} color="#34d399" />
                  <span>Get Free Models</span>
                </button>

                <button
                  type="button"
                  onClick={handleGetPaidModels}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '4px 10px',
                    borderRadius: '6px',
                    backgroundColor: 'rgba(59, 130, 246, 0.12)',
                    border: '1px solid rgba(59, 130, 246, 0.35)',
                    color: '#60a5fa',
                    fontSize: '0.74rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  <CreditCard size={13} color="#60a5fa" />
                  <span>Get Paid Models</span>
                </button>

                <button
                  type="button"
                  onClick={() => setShowAddModelDropdown(!showAddModelDropdown)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#60a5fa',
                    fontSize: '0.74rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  <Plus size={13} />
                  <span>Add Model</span>
                </button>
              </div>
            </div>

            {/* Tags Box */}
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '8px',
                padding: '8px 10px',
                backgroundColor: 'rgba(17, 24, 39, 0.8)',
                border: '1px solid rgba(66, 71, 84, 0.5)',
                borderRadius: '8px',
                minHeight: '42px',
                alignItems: 'center',
              }}
            >
              {formData.models.map((model) => (
                <span
                  key={model}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '4px 9px',
                    borderRadius: '6px',
                    backgroundColor: 'rgba(255, 255, 255, 0.07)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    color: '#e2e8f0',
                    fontSize: '0.74rem',
                    fontFamily: 'var(--font-mono, monospace)',
                  }}
                >
                  {model}
                  <button
                    type="button"
                    onClick={() => handleRemoveModel(model)}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: '#94a3b8',
                      cursor: 'pointer',
                      padding: '0',
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}

              {/* Add Input if open */}
              {showAddModelDropdown && (
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                  <input
                    type="text"
                    placeholder="model-name/id"
                    value={newModelInput}
                    onChange={(e) => setNewModelInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleAddModel(newModelInput);
                    }}
                    autoFocus
                    style={{
                      backgroundColor: 'rgba(0, 0, 0, 0.4)',
                      border: '1px solid #3b82f6',
                      borderRadius: '4px',
                      padding: '2px 6px',
                      color: '#ffffff',
                      fontSize: '0.74rem',
                      fontFamily: 'var(--font-mono, monospace)',
                      outline: 'none',
                      width: '140px',
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => handleAddModel(newModelInput)}
                    style={{
                      backgroundColor: '#3b82f6',
                      border: 'none',
                      color: '#ffffff',
                      borderRadius: '4px',
                      padding: '3px 6px',
                      fontSize: '0.7rem',
                      cursor: 'pointer',
                    }}
                  >
                    Add
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Row 5: Per-Model Rule Assignment Card (NEW FEATURE FROM SCREENSHOT) */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              backgroundColor: 'rgba(15, 23, 42, 0.65)',
              border: '1px solid rgba(66, 71, 84, 0.35)',
              borderRadius: '12px',
              padding: '16px 18px',
              gap: '14px',
            }}
          >
            {/* Header of Per-Model Card */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '0.90rem', fontWeight: 700, color: '#f8fafc' }}>
                  Per-Model Rule Assignment
                </span>
                <span
                  style={{
                    fontSize: '0.68rem',
                    fontWeight: 700,
                    padding: '2px 8px',
                    borderRadius: '10px',
                    backgroundColor: 'rgba(168, 85, 247, 0.2)',
                    color: '#c084fc',
                  }}
                >
                  New
                </span>
              </div>

              <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
                Assign a routing rule to each model for more granular control.
              </span>
            </div>

            {/* Table Header */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1.2fr 1fr',
                gap: '16px',
                fontSize: '0.72rem',
                color: '#64748b',
                fontWeight: 600,
                paddingBottom: '4px',
              }}
            >
              <span>Model</span>
              <span>Routing Rule</span>
            </div>

            {/* Per Model List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {currentRules.map((ruleMapping) => (
                <div
                  key={ruleMapping.model}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1.2fr 1fr',
                    gap: '16px',
                    alignItems: 'center',
                  }}
                >
                  {/* Model Name with Brand Icon */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <ModelBrandIcon modelName={ruleMapping.model} size={22} />
                    <span
                      style={{
                        fontSize: '0.78rem',
                        fontWeight: 600,
                        color: '#f8fafc',
                        fontFamily: 'var(--font-mono, monospace)',
                      }}
                    >
                      {ruleMapping.model}
                    </span>
                  </div>

                  {/* Routing Rule Selector + Info Icon */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <select
                      value={ruleMapping.rule}
                      onChange={(e) => handlePerModelRuleChange(ruleMapping.model, e.target.value)}
                      style={{
                        backgroundColor: 'rgba(17, 24, 39, 0.85)',
                        border: '1px solid rgba(66, 71, 84, 0.5)',
                        borderRadius: '8px',
                        padding: '7px 12px',
                        color: '#f8fafc',
                        fontSize: '0.80rem',
                        outline: 'none',
                        cursor: 'pointer',
                        width: '100%',
                      }}
                    >
                      <option value="Coding">Coding</option>
                      <option value="General">General</option>
                      <option value="Fast Inference">Fast Inference</option>
                      <option value="Planning">Planning</option>
                      <option value="Local Privacy">Local Privacy</option>
                    </select>

                    <button
                      type="button"
                      title="Override info"
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#64748b',
                        cursor: 'pointer',
                        padding: '2px',
                        display: 'flex',
                        alignItems: 'center',
                      }}
                    >
                      <Info size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Bottom Info Pill Box */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 12px',
                borderRadius: '8px',
                backgroundColor: 'rgba(0, 0, 0, 0.25)',
                border: '1px solid rgba(66, 71, 84, 0.25)',
                fontSize: '0.72rem',
                color: '#94a3b8',
                marginTop: '4px',
              }}
            >
              <Info size={14} color="#60a5fa" style={{ flexShrink: 0 }} />
              <span>
                These per-model rules override the global Routing Rule / Policy when a matching model is selected.
              </span>
            </div>
          </div>

          {/* Row 6: Routing Rule / Policy (Default for unmapped models) & Fallback Provider */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '14px',
            }}
          >
            {/* Global Rule */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
                Routing Rule / Policy (Default for unmapped models)
              </label>
              <select
                value={formData.ruleSet}
                onChange={(e) => handleInputChange('ruleSet', e.target.value)}
                style={{
                  backgroundColor: 'rgba(17, 24, 39, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  color: '#f8fafc',
                  fontSize: '0.82rem',
                  outline: 'none',
                  cursor: 'pointer',
                }}
              >
                <option value="Coding">Coding</option>
                <option value="Planning">Planning</option>
                <option value="Fast inference">Fast inference</option>
                <option value="Local privacy">Local privacy</option>
                <option value="General">General</option>
              </select>
              <span style={{ fontSize: '0.68rem', color: '#64748b', display: 'flex', alignItems: 'center', gap: '4px' }}>
                Used for any model not explicitly mapped above. <Info size={11} />
              </span>
            </div>

            {/* Fallback Provider */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
                Fallback Provider
              </label>
              <select
                value={formData.fallbackProvider}
                onChange={(e) => handleInputChange('fallbackProvider', e.target.value)}
                style={{
                  backgroundColor: 'rgba(17, 24, 39, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  color: '#f8fafc',
                  fontSize: '0.82rem',
                  outline: 'none',
                  cursor: 'pointer',
                }}
              >
                <option value="OpenAI">OpenAI</option>
                <option value="Anthropic">Anthropic</option>
                <option value="Groq">Groq</option>
                <option value="Google AI Studio">Google AI Studio</option>
                <option value="Ollama Local">Ollama Local</option>
                <option value="None">None</option>
              </select>
              <span style={{ fontSize: '0.68rem', color: '#64748b', display: 'flex', alignItems: 'center', gap: '4px' }}>
                Used when all models fail or are unavailable. <Info size={11} />
              </span>
            </div>
          </div>

          {/* Row 7: Max Tokens & Toggles */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1.2fr 1fr 1fr',
              gap: '14px',
              alignItems: 'center',
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
                Max Tokens (Default)
              </label>
              <input
                type="number"
                value={formData.maxTokens}
                onChange={(e) => handleInputChange('maxTokens', Number(e.target.value))}
                style={{
                  backgroundColor: 'rgba(17, 24, 39, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  color: '#f8fafc',
                  fontSize: '0.82rem',
                  fontFamily: 'var(--font-mono, monospace)',
                  outline: 'none',
                }}
              />
            </div>

            {/* Streaming Toggle */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
                Streaming
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', height: '36px' }}>
                <button
                  type="button"
                  onClick={() => handleInputChange('streaming', !formData.streaming)}
                  style={{
                    width: '40px',
                    height: '22px',
                    borderRadius: '12px',
                    backgroundColor: formData.streaming ? '#3b82f6' : 'rgba(255, 255, 255, 0.1)',
                    border: 'none',
                    position: 'relative',
                    cursor: 'pointer',
                    transition: 'background-color 0.15s ease',
                  }}
                >
                  <span
                    style={{
                      position: 'absolute',
                      top: '2px',
                      left: formData.streaming ? '20px' : '2px',
                      width: '18px',
                      height: '18px',
                      borderRadius: '50%',
                      backgroundColor: '#ffffff',
                      transition: 'left 0.15s ease',
                    }}
                  />
                </button>
              </div>
            </div>

            {/* Enable Cache Toggle */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
                Enable Cache
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', height: '36px' }}>
                <button
                  type="button"
                  onClick={() => handleInputChange('enableCache', !formData.enableCache)}
                  style={{
                    width: '40px',
                    height: '22px',
                    borderRadius: '12px',
                    backgroundColor: formData.enableCache ? '#3b82f6' : 'rgba(255, 255, 255, 0.1)',
                    border: 'none',
                    position: 'relative',
                    cursor: 'pointer',
                    transition: 'background-color 0.15s ease',
                  }}
                >
                  <span
                    style={{
                      position: 'absolute',
                      top: '2px',
                      left: formData.enableCache ? '20px' : '2px',
                      width: '18px',
                      height: '18px',
                      borderRadius: '50%',
                      backgroundColor: '#ffffff',
                      transition: 'left 0.15s ease',
                    }}
                  />
                </button>
              </div>
            </div>
          </div>

          {/* Action Buttons Row */}
          <div style={{ display: 'flex', gap: '12px', marginTop: '4px' }}>
            <button
              type="button"
              onClick={handleSave}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                padding: '9px 20px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
                color: '#ffffff',
                border: '1px solid rgba(147, 197, 253, 0.3)',
                boxShadow: '0 2px 10px rgba(59, 130, 246, 0.3)',
                fontSize: '0.84rem',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              <Save size={14} />
              <span>Save Changes</span>
            </button>

            <button
              type="button"
              disabled={isTesting}
              onClick={() => onTestConnection(formData.id)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                padding: '9px 18px',
                borderRadius: '8px',
                backgroundColor: 'rgba(139, 92, 246, 0.1)',
                color: '#c4b5fd',
                border: '1px solid rgba(167, 139, 250, 0.35)',
                fontSize: '0.84rem',
                fontWeight: 600,
                cursor: isTesting ? 'wait' : 'pointer',
              }}
            >
              {isTesting ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Testing...</span>
                </>
              ) : (
                <>
                  <Zap size={14} color="#a78bfa" />
                  <span>Test Connection</span>
                </>
              )}
            </button>
          </div>

          {/* Last Test Result Box */}
          <div
            style={{
              marginTop: '6px',
              padding: '14px 16px',
              borderRadius: '10px',
              backgroundColor: 'rgba(16, 185, 129, 0.04)',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={16} color="#34d399" />
                <div>
                  <span style={{ fontSize: '0.70rem', color: '#94a3b8', display: 'block' }}>
                    Last Test Result
                  </span>
                  <span
                    style={{
                      fontSize: '0.84rem',
                      fontWeight: 700,
                      color: '#34d399',
                    }}
                  >
                    Connection Successful
                  </span>
                </div>
              </div>

              <span style={{ fontSize: '0.70rem', color: '#64748b' }}>
                {formData.lastTestTime || 'Just now (16:23)'}
              </span>
            </div>

            {/* 4 Stat Items */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: '8px',
                paddingTop: '8px',
                borderTop: '1px solid rgba(16, 185, 129, 0.15)',
              }}
            >
              <div>
                <span style={{ fontSize: '0.68rem', color: '#94a3b8', display: 'block' }}>
                  Latency
                </span>
                <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#f8fafc' }}>
                  {formData.lastTestLatency || 289} ms
                </span>
              </div>

              <div>
                <span style={{ fontSize: '0.68rem', color: '#94a3b8', display: 'block' }}>
                  Authentication
                </span>
                <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#34d399' }}>
                  Success
                </span>
              </div>

              <div>
                <span style={{ fontSize: '0.68rem', color: '#94a3b8', display: 'block' }}>
                  Models Fetched
                </span>
                <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#f8fafc' }}>
                  {formData.modelsCount} models
                </span>
              </div>

              <div>
                <span style={{ fontSize: '0.68rem', color: '#94a3b8', display: 'block' }}>
                  Endpoint
                </span>
                <span
                  style={{
                    fontSize: '0.82rem',
                    fontWeight: 700,
                    color: '#34d399',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  <span
                    style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      backgroundColor: '#34d399',
                    }}
                  />
                  Healthy
                </span>
              </div>
            </div>

            <div style={{ fontSize: '0.70rem', color: '#64748b' }}>
              Full response completed in {formData.lastTestLatency || 289} ms.
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
