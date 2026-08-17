import React, { useState } from 'react';
import type { WorkflowDefinitionResource, WorkflowRunResource } from '@windagent/api-contracts';
import { useWorkflowDefinitions } from '../hooks/useWorkflows';
import { WorkflowRunsPanel } from '../components/WorkflowRunsPanel';
import { WorkflowRunDetail } from '../components/WorkflowRunDetail';
import { WorkflowEditor } from '../components/WorkflowEditor';

export const WorkflowsPage: React.FC = () => {
  const [selectedRun, setSelectedRun] = useState<WorkflowRunResource | null>(null);
  const [selectedDefinition, setSelectedDefinition] = useState<WorkflowDefinitionResource | null>(null);
  const [isCreatingNew, setIsCreatingNew] = useState(false);

  const { data: workflows = [], isLoading, isError } = useWorkflowDefinitions();

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
            Workflows & Automation
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted, #9ca3af)' }}>
            Authoritative workflow catalog, automated step execution, and live pipeline monitoring.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setSelectedDefinition(null);
            setIsCreatingNew(true);
          }}
          style={{
            background: 'var(--color-primary, #3b82f6)',
            color: '#ffffff',
            border: 'none',
            borderRadius: '6px',
            padding: '8px 16px',
            fontSize: '0.8rem',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          + New Workflow
        </button>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(380px, 1.2fr) minmax(380px, 1.4fr)',
          gap: '20px',
          alignItems: 'start',
        }}
      >
        {/* Left Column: Runs Panel & Catalog Overview */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <WorkflowRunsPanel
            workflows={workflows}
            selectedRunId={selectedRun?.id}
            onSelectRun={(run) => setSelectedRun(run)}
          />

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
            <h4 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary, #f9fafb)' }}>
              Definitions Catalog ({workflows.length})
            </h4>
            {isLoading ? (
              <div style={{ padding: '12px', color: 'var(--text-muted, #9ca3af)', fontSize: '0.85rem' }}>
                Loading catalog...
              </div>
            ) : isError ? (
              <div style={{ padding: '12px', color: '#ef4444', fontSize: '0.85rem' }}>
                Failed to load catalog
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {workflows.map((wf) => (
                  <div
                    key={wf.id}
                    onClick={() => {
                      setSelectedDefinition(wf);
                      setIsCreatingNew(false);
                    }}
                    style={{
                      background: 'var(--bg-card, #1f2937)',
                      border: '1px solid var(--border-color, #1f2937)',
                      borderRadius: '8px',
                      padding: '12px',
                      cursor: 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '4px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, fontSize: '0.875rem', color: '#f9fafb' }}>
                        {wf.name}
                      </span>
                      <span style={{ fontSize: '0.7rem', color: '#38bdf8', fontWeight: 600 }}>
                        {wf.type}
                      </span>
                    </div>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)' }}>
                      {wf.description}
                    </span>
                    <div style={{ display: 'flex', gap: '8px', fontSize: '0.7rem', color: '#6b7280', marginTop: '4px' }}>
                      <span>Steps: {wf.steps.length}</span>
                      <span>Trigger: {wf.trigger}</span>
                      <span>v{wf.version}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Run Detail or Workflow Editor */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {(isCreatingNew || selectedDefinition) && (
            <WorkflowEditor
              workflow={selectedDefinition}
              onSaved={() => {
                setIsCreatingNew(false);
                setSelectedDefinition(null);
              }}
              onCancelled={() => {
                setIsCreatingNew(false);
                setSelectedDefinition(null);
              }}
            />
          )}
          <WorkflowRunDetail runId={selectedRun?.id} />
        </div>
      </div>
    </div>
  );
};
