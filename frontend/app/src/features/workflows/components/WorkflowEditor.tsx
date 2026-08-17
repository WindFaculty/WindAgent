import React, { useState, useEffect } from 'react';
import { useCreateWorkflow, useUpdateWorkflow } from '../hooks/useWorkflows';
import type { WorkflowDefinitionResource } from '@windagent/api-contracts';

interface WorkflowEditorProps {
  workflow: WorkflowDefinitionResource | null;
  onSaved: () => void;
  onCancelled: () => void;
}

export const WorkflowEditor: React.FC<WorkflowEditorProps> = ({
  workflow,
  onSaved,
  onCancelled,
}) => {
  const isEditing = Boolean(workflow);
  const [name, setName] = useState('');
  const [type, setType] = useState('Standard');
  const [trigger, setTrigger] = useState('Manual');
  const [description, setDescription] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (workflow) {
      setName(workflow.name);
      setType(workflow.type || 'Standard');
      setTrigger(workflow.trigger || 'Manual');
      setDescription(workflow.description || '');
      setErrorMsg(null);
    } else {
      setName('');
      setType('Standard');
      setTrigger('Manual');
      setDescription('');
      setErrorMsg(null);
    }
  }, [workflow]);

  const createMutation = useCreateWorkflow();
  const updateMutation = useUpdateWorkflow();

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (!name.trim()) {
      setErrorMsg('Name is required');
      return;
    }

    try {
      if (isEditing && workflow) {
        await updateMutation.mutateAsync({
          workflowId: workflow.id,
          data: {
            name,
            type,
            trigger,
            description,
            expected_version: workflow.version,
          },
        });
      } else {
        await createMutation.mutateAsync({
          name,
          type,
          trigger,
          description,
        });
      }
      onSaved();
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to save workflow definition');
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
          {isEditing ? `Edit Workflow (${workflow?.name})` : 'Create Workflow Definition'}
        </h4>
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
              Type
            </label>
            <input
              type="text"
              value={type}
              onChange={(e) => setType(e.target.value)}
              placeholder="e.g. ML Pipeline, DevOps"
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
              Trigger Mode
            </label>
            <select
              value={trigger}
              onChange={(e) => setTrigger(e.target.value)}
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
              <option value="Manual">Manual</option>
              <option value="Scheduled">Scheduled</option>
              <option value="Event-based">Event-based</option>
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
            {createMutation.isPending || updateMutation.isPending ? 'Saving...' : 'Save Workflow'}
          </button>
        </div>
      </form>
    </div>
  );
};
