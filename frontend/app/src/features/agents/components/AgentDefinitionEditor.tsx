import React, { useState, useEffect } from 'react';
import { useCreateAgentDefinition, useUpdateAgentDefinition, useDeleteAgentDefinition } from '../hooks/useAgents';
import type { AgentDefinitionResource } from '@windagent/api-contracts';

interface AgentDefinitionEditorProps {
  definition: AgentDefinitionResource | null;
  onSaved: () => void;
  onCancelled: () => void;
}

export const AgentDefinitionEditor: React.FC<AgentDefinitionEditorProps> = ({
  definition,
  onSaved,
  onCancelled,
}) => {
  const isEditing = Boolean(definition);
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [role, setRole] = useState('coder');
  const [description, setDescription] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (definition) {
      setName(definition.name);
      setSlug(definition.slug || '');
      setRole(definition.role);
      setDescription(definition.description || '');
      setErrorMsg(null);
    } else {
      setName('');
      setSlug('');
      setRole('coder');
      setDescription('');
      setErrorMsg(null);
    }
  }, [definition]);

  const createMutation = useCreateAgentDefinition();
  const updateMutation = useUpdateAgentDefinition();
  const deleteMutation = useDeleteAgentDefinition();

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (!name.trim()) {
      setErrorMsg('Name is required');
      return;
    }

    try {
      if (isEditing && definition) {
        await updateMutation.mutateAsync({
          definitionId: definition.id,
          data: {
            name,
            slug: slug || undefined,
            role,
            description,
            expected_version: definition.version,
          },
        });
      } else {
        await createMutation.mutateAsync({
          name,
          slug: slug || undefined,
          role,
          description,
        });
      }
      onSaved();
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to save definition');
    }
  };

  const handleDelete = async () => {
    if (!definition || !window.confirm(`Delete agent definition '${definition.name}'?`)) return;
    try {
      await deleteMutation.mutateAsync(definition.id);
      onSaved();
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to delete definition');
    }
  };

  return (
    <div
      style={{
        background: 'var(--bg-panel, #111827)',
        border: '1px solid var(--border-color, #1f2937)',
        borderRadius: '12px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary, #f9fafb)' }}>
          {isEditing ? `Edit Definition (v${definition?.version})` : 'Create Agent Definition'}
        </h4>
        {isEditing && (
          <button
            type="button"
            onClick={handleDelete}
            style={{
              background: 'rgba(239, 68, 68, 0.15)',
              color: '#ef4444',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: '4px',
              padding: '4px 8px',
              fontSize: '0.75rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Delete
          </button>
        )}
      </div>

      {errorMsg && (
        <div style={{ padding: '8px 12px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '6px', color: '#ef4444', fontSize: '0.8rem' }}>
          {errorMsg}
        </div>
      )}

      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <div>
          <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', marginBottom: '4px' }}>
            Name *
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            style={{
              width: '100%',
              background: 'var(--bg-card, #1f2937)',
              border: '1px solid var(--border-color, #374151)',
              borderRadius: '6px',
              padding: '8px 10px',
              color: '#f9fafb',
              fontSize: '0.85rem',
              boxSizing: 'border-box',
            }}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', marginBottom: '4px' }}>
              Slug
            </label>
            <input
              type="text"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="e.g. coder-pro"
              style={{
                width: '100%',
                background: 'var(--bg-card, #1f2937)',
                border: '1px solid var(--border-color, #374151)',
                borderRadius: '6px',
                padding: '8px 10px',
                color: '#f9fafb',
                fontSize: '0.85rem',
                boxSizing: 'border-box',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', marginBottom: '4px' }}>
              Role *
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              style={{
                width: '100%',
                background: 'var(--bg-card, #1f2937)',
                border: '1px solid var(--border-color, #374151)',
                borderRadius: '6px',
                padding: '8px 10px',
                color: '#f9fafb',
                fontSize: '0.85rem',
                boxSizing: 'border-box',
              }}
            >
              <option value="orchestrator">Orchestrator</option>
              <option value="coder">Coder</option>
              <option value="researcher">Researcher</option>
              <option value="reviewer">Reviewer</option>
              <option value="planner">Planner</option>
              <option value="tester">Tester</option>
            </select>
          </div>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', marginBottom: '4px' }}>
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            style={{
              width: '100%',
              background: 'var(--bg-card, #1f2937)',
              border: '1px solid var(--border-color, #374151)',
              borderRadius: '6px',
              padding: '8px 10px',
              color: '#f9fafb',
              fontSize: '0.85rem',
              boxSizing: 'border-box',
              resize: 'vertical',
            }}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
          <button
            type="button"
            onClick={onCancelled}
            style={{
              background: 'transparent',
              color: 'var(--text-muted, #9ca3af)',
              border: '1px solid var(--border-color, #374151)',
              borderRadius: '6px',
              padding: '6px 12px',
              fontSize: '0.8rem',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={createMutation.isPending || updateMutation.isPending}
            style={{
              background: 'var(--color-primary, #3b82f6)',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              padding: '6px 14px',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {createMutation.isPending || updateMutation.isPending ? 'Saving...' : 'Save Definition'}
          </button>
        </div>
      </form>
    </div>
  );
};
