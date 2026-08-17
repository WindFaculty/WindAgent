import React, { useState } from 'react';
import type { RoutingRuleResource } from '@windagent/api-contracts';
import { useCreateRoutingRule, useUpdateRoutingRule, useDeleteRoutingRule } from '../hooks/useRouting';

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
  const [priority, setPriority] = useState(rule?.priority ?? 50);
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
    if (window.confirm(`Are you sure you want to delete routing rule '${rule.name}'?`)) {
      await deleteMutation.mutateAsync(rule.id);
      onSaved();
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: '20px',
      }}
      onClick={onCancelled}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          width: '100%',
          maxWidth: '640px',
          maxHeight: '90vh',
          overflowY: 'auto',
          backgroundColor: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
          borderRadius: '12px',
          padding: '24px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
              {isEditing ? `Edit Routing Rule: ${rule?.name}` : 'Create New Routing Rule'}
            </h3>
            {isEditing && (
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted, #9ca3af)' }}>
                Rule ID: {rule?.id} (v{rule?.version})
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onCancelled}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted, #9ca3af)',
              cursor: 'pointer',
              fontSize: '1.2rem',
            }}
          >
            ✕
          </button>
        </div>

        {/* Rule Name */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary, #d1d5db)' }}>
            Rule Name *
          </label>
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Master Planner Policy"
            style={{
              padding: '8px 12px',
              backgroundColor: 'var(--bg-subpanel, #1f2937)',
              border: '1px solid var(--border-color, #374151)',
              borderRadius: '6px',
              color: 'var(--text-primary, #f9fafb)',
              fontSize: '0.85rem',
            }}
          />
        </div>

        {/* Description */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary, #d1d5db)' }}>
            Description
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Purpose and triggering scenario for this rule"
            style={{
              padding: '8px 12px',
              backgroundColor: 'var(--bg-subpanel, #1f2937)',
              border: '1px solid var(--border-color, #374151)',
              borderRadius: '6px',
              color: 'var(--text-primary, #f9fafb)',
              fontSize: '0.85rem',
            }}
          />
        </div>

        {/* Models Target Selection */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary, #d1d5db)' }}>
              Primary Canonical Model *
            </label>
            <select
              value={canonicalModelId}
              onChange={(e) => setCanonicalModelId(e.target.value)}
              style={{
                padding: '8px 12px',
                backgroundColor: 'var(--bg-subpanel, #1f2937)',
                border: '1px solid var(--border-color, #374151)',
                borderRadius: '6px',
                color: 'var(--text-primary, #f9fafb)',
                fontSize: '0.85rem',
              }}
            >
              <option value="anthropic/claude-3-5-sonnet">Claude 3.5 Sonnet</option>
              <option value="google/gemini-1.5-pro">Gemini 1.5 Pro</option>
              <option value="google/gemini-1.5-flash">Gemini 1.5 Flash</option>
              <option value="openai/gpt-4o">GPT-4o</option>
              <option value="openai/gpt-4o-mini">GPT-4o mini</option>
              <option value="deepseek/deepseek-r1">DeepSeek R1</option>
              <option value="ollama/qwen2.5-coder">Qwen 2.5 Coder (Local)</option>
            </select>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary, #d1d5db)' }}>
              Fallback Model
            </label>
            <select
              value={fallbackModelId}
              onChange={(e) => setFallbackModelId(e.target.value)}
              style={{
                padding: '8px 12px',
                backgroundColor: 'var(--bg-subpanel, #1f2937)',
                border: '1px solid var(--border-color, #374151)',
                borderRadius: '6px',
                color: 'var(--text-primary, #f9fafb)',
                fontSize: '0.85rem',
              }}
            >
              <option value="">None</option>
              <option value="google/gemini-1.5-pro">Gemini 1.5 Pro</option>
              <option value="google/gemini-1.5-flash">Gemini 1.5 Flash</option>
              <option value="anthropic/claude-3-5-sonnet">Claude 3.5 Sonnet</option>
              <option value="anthropic/claude-3-haiku">Claude 3 Haiku</option>
              <option value="openai/gpt-4o">GPT-4o</option>
              <option value="openai/gpt-4o-mini">GPT-4o mini</option>
              <option value="deepseek/deepseek-r1">DeepSeek R1</option>
              <option value="ollama/qwen2.5-coder">Qwen 2.5 Coder (Local)</option>
            </select>
          </div>
        </div>

        {/* Priority & Toggles */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', alignItems: 'center' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary, #d1d5db)' }}>
              Priority (0=Critical, 10=High, 50=Normal, 100=Low)
            </label>
            <input
              type="number"
              min={0}
              max={100}
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
              style={{
                padding: '8px 12px',
                backgroundColor: 'var(--bg-subpanel, #1f2937)',
                border: '1px solid var(--border-color, #374151)',
                borderRadius: '6px',
                color: 'var(--text-primary, #f9fafb)',
                fontSize: '0.85rem',
              }}
            />
          </div>

          <div style={{ display: 'flex', gap: '16px', marginTop: '16px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--text-primary, #f9fafb)' }}>
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              Enabled
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.85rem', color: '#4ade80' }}>
              <input type="checkbox" checked={requiresLocal} onChange={(e) => setRequiresLocal(e.target.checked)} />
              Require Offline/Local
            </label>
          </div>
        </div>

        {/* Matching Predicates */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary, #d1d5db)' }}>
            Target Agent Roles (comma separated)
          </label>
          <input
            type="text"
            value={agentTypes}
            onChange={(e) => setAgentTypes(e.target.value)}
            placeholder="Coordinator, Planner, Coder, Worker"
            style={{
              padding: '8px 12px',
              backgroundColor: 'var(--bg-subpanel, #1f2937)',
              border: '1px solid var(--border-color, #374151)',
              borderRadius: '6px',
              color: 'var(--text-primary, #f9fafb)',
              fontSize: '0.85rem',
            }}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary, #d1d5db)' }}>
            Required Capabilities (comma separated)
          </label>
          <input
            type="text"
            value={requiredCaps}
            onChange={(e) => setRequiredCaps(e.target.value)}
            placeholder="reasoning, tools, vision, code"
            style={{
              padding: '8px 12px',
              backgroundColor: 'var(--bg-subpanel, #1f2937)',
              border: '1px solid var(--border-color, #374151)',
              borderRadius: '6px',
              color: 'var(--text-primary, #f9fafb)',
              fontSize: '0.85rem',
            }}
          />
        </div>

        {/* Footer Actions */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '12px', borderTop: '1px solid var(--border-color, #1f2937)' }}>
          {isEditing ? (
            <button
              type="button"
              onClick={handleDelete}
              disabled={isPending}
              style={{
                padding: '8px 14px',
                borderRadius: '6px',
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                color: '#f87171',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                cursor: 'pointer',
                fontSize: '0.82rem',
                fontWeight: 600,
              }}
            >
              Delete Rule
            </button>
          ) : <div />}

          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              type="button"
              onClick={onCancelled}
              style={{
                padding: '8px 16px',
                borderRadius: '6px',
                backgroundColor: 'var(--btn-secondary-bg, #374151)',
                color: 'var(--text-primary, #f9fafb)',
                border: 'none',
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
                padding: '8px 18px',
                borderRadius: '6px',
                backgroundColor: 'var(--color-primary, #2563eb)',
                color: '#ffffff',
                border: 'none',
                cursor: isPending ? 'not-allowed' : 'pointer',
                fontSize: '0.85rem',
                fontWeight: 600,
                opacity: isPending ? 0.7 : 1,
              }}
            >
              {isPending ? 'Saving...' : (isEditing ? 'Save Changes' : 'Create Rule')}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
