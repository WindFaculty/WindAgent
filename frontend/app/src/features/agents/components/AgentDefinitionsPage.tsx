import React, { useState } from 'react';
import { useAgentDefinitions } from '../hooks/useAgents';
import type { AgentDefinitionResource } from '@windagent/api-contracts';

interface AgentDefinitionsListProps {
  selectedDefinitionId?: string | null;
  onSelectDefinition: (def: AgentDefinitionResource) => void;
  onCreateNew: () => void;
}

export const AgentDefinitionsList: React.FC<AgentDefinitionsListProps> = ({
  selectedDefinitionId,
  onSelectDefinition,
  onCreateNew,
}) => {
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('all');

  const { data: definitions = [], isLoading, isError } = useAgentDefinitions({
    search: search || undefined,
    role: roleFilter !== 'all' ? roleFilter : undefined,
  });

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
          Agent Definitions Catalog
        </h4>
        <button
          type="button"
          onClick={onCreateNew}
          style={{
            background: 'var(--color-primary, #3b82f6)',
            color: '#ffffff',
            border: 'none',
            borderRadius: '6px',
            padding: '6px 12px',
            fontSize: '0.75rem',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          + New Definition
        </button>
      </div>

      <div style={{ display: 'flex', gap: '8px' }}>
        <input
          type="text"
          placeholder="Search definitions..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            flex: 1,
            background: 'var(--bg-card, #1f2937)',
            border: '1px solid var(--border-color, #374151)',
            borderRadius: '6px',
            padding: '6px 10px',
            color: '#f9fafb',
            fontSize: '0.8rem',
          }}
        />
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          style={{
            background: 'var(--bg-card, #1f2937)',
            border: '1px solid var(--border-color, #374151)',
            borderRadius: '6px',
            padding: '6px 10px',
            color: '#f9fafb',
            fontSize: '0.8rem',
          }}
        >
          <option value="all">All Roles</option>
          <option value="orchestrator">Orchestrator</option>
          <option value="coder">Coder</option>
          <option value="researcher">Researcher</option>
          <option value="reviewer">Reviewer</option>
        </select>
      </div>

      {isLoading ? (
        <div style={{ padding: '16px', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
          Loading definitions...
        </div>
      ) : isError ? (
        <div style={{ padding: '16px', color: '#ef4444', fontSize: '0.85rem' }}>
          Failed to load definitions
        </div>
      ) : definitions.length === 0 ? (
        <div style={{ padding: '16px', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
          No agent definitions match query.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {definitions.map((def) => {
            const isSelected = def.id === selectedDefinitionId;
            return (
              <div
                key={def.id}
                onClick={() => onSelectDefinition(def)}
                style={{
                  background: isSelected ? 'rgba(59, 130, 246, 0.1)' : 'var(--bg-card, #1f2937)',
                  border: `1px solid ${isSelected ? 'var(--color-primary, #3b82f6)' : 'var(--border-color, #1f2937)'}`,
                  borderRadius: '8px',
                  padding: '12px',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                  transition: 'border-color 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.875rem', color: '#f9fafb' }}>
                    {def.name}
                  </span>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: 600,
                      padding: '1px 6px',
                      borderRadius: '4px',
                      background: 'rgba(59, 130, 246, 0.15)',
                      color: '#60a5fa',
                      textTransform: 'uppercase',
                    }}
                  >
                    {def.role}
                  </span>
                </div>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)', lineHeight: 1.4 }}>
                  {def.description || 'No description provided.'}
                </span>
                <div style={{ display: 'flex', gap: '8px', fontSize: '0.7rem', color: '#6b7280', marginTop: '4px' }}>
                  <span>slug: <code>{def.slug}</code></span>
                  <span>v{def.version}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
