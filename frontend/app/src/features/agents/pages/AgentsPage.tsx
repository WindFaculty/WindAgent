import React, { useState } from 'react';
import type { AgentDefinitionResource } from '@windagent/api-contracts';
import { AgentRuntimeMetrics } from '../components/AgentRuntimeMetrics';
import { AgentDefinitionsList } from '../components/AgentDefinitionsPage';
import { AgentDefinitionEditor } from '../components/AgentDefinitionEditor';
import { AgentInstancesPanel } from '../components/AgentInstancesPanel';
import { AgentActivity } from '../components/AgentActivity';

export const AgentsPage: React.FC = () => {
  const [selectedDefinition, setSelectedDefinition] = useState<AgentDefinitionResource | null>(null);
  const [isCreatingNew, setIsCreatingNew] = useState(false);

  return (
    <div
      style={{
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        maxWidth: '1600px',
        margin: '0 auto',
        fontFamily: 'var(--font-sans, sans-serif)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
            Agents & Registry
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>
            Manage canonical Agent Definitions, review policies, and monitor active runtime instances.
          </p>
        </div>
      </div>

      <AgentRuntimeMetrics />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(380px, 1.2fr) minmax(380px, 1.4fr)',
          gap: '20px',
          alignItems: 'start',
        }}
      >
        {/* Left Column: Definitions Catalog & Instances */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <AgentDefinitionsList
            selectedDefinitionId={selectedDefinition?.id}
            onSelectDefinition={(def) => {
              setSelectedDefinition(def);
              setIsCreatingNew(false);
            }}
            onCreateNew={() => {
              setSelectedDefinition(null);
              setIsCreatingNew(true);
            }}
          />
          <AgentInstancesPanel />
        </div>

        {/* Right Column: Editor / Activity */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {(isCreatingNew || selectedDefinition) && (
            <AgentDefinitionEditor
              definition={selectedDefinition}
              onSaved={() => {
                setIsCreatingNew(false);
              }}
              onCancelled={() => {
                setIsCreatingNew(false);
                setSelectedDefinition(null);
              }}
            />
          )}
          <AgentActivity definitionId={selectedDefinition?.id} />
        </div>
      </div>
    </div>
  );
};
