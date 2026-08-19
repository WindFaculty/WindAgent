import React, { useState } from 'react';
import type { RoutingRuleResource } from '@windagent/api-contracts';
import { useCreateRoutingRule, useUpdateRoutingRule, useDeleteRoutingRule } from '../hooks/useRouting';
import {
  X,
  Save,
  Trash2,
  Zap,
  Lock,
  CheckCircle2,
} from 'lucide-react';

interface RoutingRuleEditorProps {
  rule?: RoutingRuleResource | null;
  onSaved: () => void;
  onCancelled: () => void;
}

export const RoutingRuleEditor: React.FC<RoutingRuleEditorProps> = ({
  rule,
  onSaved,
  onCancelled,
}) => {
  const createMutation = useCreateRoutingRule();
  const updateMutation = useUpdateRoutingRule();
  const deleteMutation = useDeleteRoutingRule();

  const [name, setName] = useState(rule?.name || '');
  const [description, setDescription] = useState(rule?.description || '');
  const [canonicalModelId, setCanonicalModelId] = useState(rule?.canonical_model_id || 'anthropic/claude-3-5-sonnet');
  const [fallbackModelId, setFallbackModelId] = useState(rule?.fallback_model_id || 'google/gemini-1.5-pro');
  const [priority, setPriority] = useState(rule?.priority ?? 10);
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  const [agentTypes, setAgentTypes] = useState(rule?.agent_types?.join(', ') || 'Coordinator, Planner');
  const [requiredCaps, setRequiredCaps] = useState(rule?.required_capabilities?.join(', ') || 'reasoning, tools');
  const [requiresLocal, setRequiresLocal] = useState(rule?.requires_local ?? false);

  const isEditing = Boolean(rule);
  const isPending = createMutation.isPending || updateMutation.isPending || deleteMutation.isPending;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      name,
      description,
      canonical_model_id: canonicalModelId,
      fallback_model_id: fallbackModelId || undefined,
      priority: Number(priority),
      enabled,
      agent_types: agentTypes.split(',').map((s) => s.trim()).filter(Boolean),
      required_capabilities: requiredCaps.split(',').map((s) => s.trim()).filter(Boolean),
      requires_local: requiresLocal,
    };

    if (isEditing && rule) {
      await updateMutation.mutateAsync({
        ruleId: rule.id,
        updates: { ...payload, expected_version: rule.version },
      });
    } else {
      await createMutation.mutateAsync(payload);
    }
    onSaved();
  };

  const handleDelete = async () => {
    if (!rule) return;
    if (window.confirm(`Are you sure you want to permanently delete routing rule "${rule.name}"?`)) {
      await deleteMutation.mutateAsync(rule.id);
      onSaved();
    }
  };

  const getPriorityBadge = (p: number) => {
    if (p <= 0) return { text: 'Critical (P0)', color: '#f87171', bg: 'rgba(239, 68, 68, 0.15)' };
    if (p <= 10) return { text: `High (P${p})`, color: '#fbbf24', bg: 'rgba(245, 158, 11, 0.15)' };
    if (p <= 50) return { text: `Normal (P${p})`, color: '#60a5fa', bg: 'rgba(59, 130, 246, 0.15)' };
    return { text: `Low (P${p})`, color: '#9ca3af', bg: 'rgba(156, 163, 175, 0.15)' };
  };

  const pBadge = getPriorityBadge(Number(priority));

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(6, 14, 32, 0.82)',
        backdropFilter: 'blur(16px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: '24px',
      }}
      onClick={onCancelled}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          width: '100%',
          maxWidth: '720px',
          maxHeight: '90vh',
          overflowY: 'auto',
          backgroundColor: 'rgba(19, 27, 46, 0.95)',
          border: '1px solid rgba(77, 142, 255, 0.35)',
          borderRadius: '16px',
          padding: '28px',
          boxShadow: '0 25px 60px -12px rgba(0, 0, 0, 0.8), 0 0 30px rgba(77, 142, 255, 0.15)',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', paddingBottom: '16px', borderBottom: '1px solid rgba(66, 71, 84, 0.4)' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={20} color="#4d8eff" />
              <h3 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 800, color: 'var(--text-main, #dae2fd)' }}>
                {isEditing ? `Edit Routing Policy: ${rule?.name}` : 'Create New Routing Policy'}
              </h3>
            </div>
            {isEditing && (
              <span style={{ fontSize: '0.78rem', color: 'var(--text-dim, #8c909f)', marginTop: '4px', display: 'block' }}>
                Policy ID: <code>{rule?.id}</code> • Version: v{rule?.version}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={onCancelled}
            style={{
              background: 'rgba(34, 42, 61, 0.6)',
              border: '1px solid rgba(66, 71, 84, 0.4)',
              borderRadius: '8px',
              color: 'var(--text-muted, #c2c6d6)',
              cursor: 'pointer',
              padding: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Section 1: Basic Information */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted, #c2c6d6)', textTransform: 'uppercase' }}>
                Policy Name *
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Master Planner Policy"
                style={{
                  padding: '9px 12px',
                  backgroundColor: 'rgba(11, 19, 38, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  color: 'var(--text-main, #dae2fd)',
                  fontSize: '0.88rem',
                  outline: 'none',
                }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted, #c2c6d6)', textTransform: 'uppercase' }}>
                  Priority *
                </label>
                <span style={{ fontSize: '0.72rem', fontWeight: 700, padding: '1px 6px', borderRadius: '4px', backgroundColor: pBadge.bg, color: pBadge.color }}>
                  {pBadge.text}
                </span>
              </div>
              <input
                type="number"
                min={0}
                max={100}
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value))}
                style={{
                  padding: '9px 12px',
                  backgroundColor: 'rgba(11, 19, 38, 0.8)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  color: 'var(--text-main, #dae2fd)',
                  fontSize: '0.88rem',
                  outline: 'none',
                }}
              />
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted, #c2c6d6)', textTransform: 'uppercase' }}>
              Description
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="High-reasoning routing for episodic coordinator and storyboard orchestration"
              style={{
                padding: '9px 12px',
                backgroundColor: 'rgba(11, 19, 38, 0.8)',
                border: '1px solid rgba(66, 71, 84, 0.5)',
                borderRadius: '8px',
                color: 'var(--text-main, #dae2fd)',
                fontSize: '0.88rem',
                outline: 'none',
              }}
            />
          </div>
        </div>

        {/* Section 2: Model Targets */}
        <div
          style={{
            padding: '16px',
            borderRadius: '10px',
            backgroundColor: 'rgba(11, 19, 38, 0.65)',
            border: '1px solid rgba(66, 71, 84, 0.35)',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Zap size={16} color="#fbbf24" />
            <h4 style={{ margin: 0, fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-main, #dae2fd)', textTransform: 'uppercase' }}>
              Model Resolution & Failover Strategy
            </h4>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted, #c2c6d6)' }}>
                Primary Canonical Model *
              </label>
              <select
                value={canonicalModelId}
                onChange={(e) => setCanonicalModelId(e.target.value)}
                style={{
                  padding: '9px 12px',
                  backgroundColor: 'rgba(19, 27, 46, 0.9)',
                  border: '1px solid rgba(77, 142, 255, 0.4)',
                  borderRadius: '8px',
                  color: 'var(--text-main, #dae2fd)',
                  fontSize: '0.85rem',
                  outline: 'none',
                }}
              >
                <option value="anthropic/claude-3-5-sonnet">Claude 3.5 Sonnet (Anthropic)</option>
                <option value="google/gemini-1.5-pro">Gemini 1.5 Pro (Google)</option>
                <option value="google/gemini-1.5-flash">Gemini 1.5 Flash (Google)</option>
                <option value="openai/gpt-4o">GPT-4o (OpenAI)</option>
                <option value="openai/gpt-4o-mini">GPT-4o mini (OpenAI)</option>
                <option value="deepseek/deepseek-r1">DeepSeek R1 (DeepSeek)</option>
                <option value="ollama/qwen2.5-coder">Qwen 2.5 Coder (Local Ollama)</option>
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted, #c2c6d6)' }}>
                Fallback Model (Auto-Failover)
              </label>
              <select
                value={fallbackModelId}
                onChange={(e) => setFallbackModelId(e.target.value)}
                style={{
                  padding: '9px 12px',
                  backgroundColor: 'rgba(19, 27, 46, 0.9)',
                  border: '1px solid rgba(66, 71, 84, 0.5)',
                  borderRadius: '8px',
                  color: 'var(--text-main, #dae2fd)',
                  fontSize: '0.85rem',
                  outline: 'none',
                }}
              >
                <option value="">None (No Fallback)</option>
                <option value="google/gemini-1.5-pro">Gemini 1.5 Pro (Google)</option>
                <option value="google/gemini-1.5-flash">Gemini 1.5 Flash (Google)</option>
                <option value="anthropic/claude-3-5-sonnet">Claude 3.5 Sonnet (Anthropic)</option>
                <option value="anthropic/claude-3-haiku">Claude 3 Haiku (Anthropic)</option>
                <option value="openai/gpt-4o">GPT-4o (OpenAI)</option>
                <option value="openai/gpt-4o-mini">GPT-4o mini (OpenAI)</option>
                <option value="deepseek/deepseek-r1">DeepSeek R1 (DeepSeek)</option>
                <option value="ollama/qwen2.5-coder">Qwen 2.5 Coder (Local Ollama)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Section 3: Matching Predicates & Constraints */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted, #c2c6d6)', textTransform: 'uppercase' }}>
              Target Agent Roles (comma separated)
            </label>
            <input
              type="text"
              value={agentTypes}
              onChange={(e) => setAgentTypes(e.target.value)}
              placeholder="Coordinator, Planner, Coder, Worker, Director"
              style={{
                padding: '9px 12px',
                backgroundColor: 'rgba(11, 19, 38, 0.8)',
                border: '1px solid rgba(66, 71, 84, 0.5)',
                borderRadius: '8px',
                color: 'var(--text-main, #dae2fd)',
                fontSize: '0.88rem',
                outline: 'none',
              }}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted, #c2c6d6)', textTransform: 'uppercase' }}>
              Required Capabilities (comma separated)
            </label>
            <input
              type="text"
              value={requiredCaps}
              onChange={(e) => setRequiredCaps(e.target.value)}
              placeholder="reasoning, tools, vision, code"
              style={{
                padding: '9px 12px',
                backgroundColor: 'rgba(11, 19, 38, 0.8)',
                border: '1px solid rgba(66, 71, 84, 0.5)',
                borderRadius: '8px',
                color: 'var(--text-main, #dae2fd)',
                fontSize: '0.88rem',
                outline: 'none',
              }}
            />
          </div>

          {/* Toggles */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '20px', padding: '10px 0' }}>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--text-main, #dae2fd)', fontWeight: 600 }}>
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                style={{ accentColor: '#4edea3', width: '16px', height: '16px' }}
              />
              <CheckCircle2 size={16} color={enabled ? '#4edea3' : '#8c909f'} />
              Policy Active & Enabled
            </label>

            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.85rem', color: '#4edea3', fontWeight: 600 }}>
              <input
                type="checkbox"
                checked={requiresLocal}
                onChange={(e) => setRequiresLocal(e.target.checked)}
                style={{ accentColor: '#4edea3', width: '16px', height: '16px' }}
              />
              <Lock size={16} color="#4edea3" />
              Require Offline / Privacy-Locked
            </label>
          </div>
        </div>

        {/* Live Preview Card */}
        <div
          style={{
            padding: '12px 16px',
            borderRadius: '8px',
            backgroundColor: 'rgba(11, 19, 38, 0.7)',
            border: '1px dashed rgba(77, 142, 255, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.82rem' }}>
            <span style={{ color: 'var(--text-dim, #8c909f)', textTransform: 'uppercase', fontWeight: 700 }}>Preview:</span>
            <strong style={{ color: 'var(--text-main, #dae2fd)' }}>{name || 'Untitled Policy'}</strong>
            <span style={{ color: 'var(--text-dim, #8c909f)' }}>➔</span>
            <code style={{ color: '#38bdf8', fontWeight: 700 }}>{canonicalModelId}</code>
            {fallbackModelId && (
              <>
                <span style={{ color: 'var(--text-dim, #8c909f)' }}>↳</span>
                <code style={{ color: '#fbbf24' }}>{fallbackModelId}</code>
              </>
            )}
          </div>
          <span style={{ fontSize: '0.72rem', color: '#4edea3', fontWeight: 600 }}>Ready</span>
        </div>

        {/* Footer Actions */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '16px', borderTop: '1px solid rgba(66, 71, 84, 0.4)' }}>
          {isEditing ? (
            <button
              type="button"
              onClick={handleDelete}
              disabled={isPending}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 14px',
                borderRadius: '8px',
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                color: '#f87171',
                border: '1px solid rgba(239, 68, 68, 0.35)',
                cursor: 'pointer',
                fontSize: '0.82rem',
                fontWeight: 600,
              }}
            >
              <Trash2 size={14} /> Delete Policy
            </button>
          ) : <div />}

          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              type="button"
              onClick={onCancelled}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                backgroundColor: 'rgba(34, 42, 61, 0.8)',
                color: 'var(--text-main, #dae2fd)',
                border: '1px solid rgba(66, 71, 84, 0.5)',
                cursor: 'pointer',
                fontSize: '0.85rem',
                fontWeight: 600,
              }}
            >
              Cancel
            </button>

            <button
              type="submit"
              disabled={isPending}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 20px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #4d8eff 0%, #2563eb 100%)',
                color: '#ffffff',
                border: '1px solid rgba(173, 198, 255, 0.4)',
                boxShadow: '0 4px 14px rgba(77, 142, 255, 0.35)',
                cursor: isPending ? 'not-allowed' : 'pointer',
                fontSize: '0.85rem',
                fontWeight: 700,
                opacity: isPending ? 0.7 : 1,
              }}
            >
              <Save size={15} />
              {isPending ? 'Saving Policy...' : (isEditing ? 'Save Changes' : 'Create Policy')}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
