import React from 'react';
import { ProductionProject, ProductionRevision, SyncStatus, BackendStatus } from '@windagent/production-contracts';

export interface ProductionHeaderProps {
  currentProject: ProductionProject | null;
  currentRevision: ProductionRevision | null;
  syncStatus: SyncStatus;
  backendStatus: BackendStatus;
  availableProjects: ProductionProject[];
  onSelectProject: (projectId: string) => void;
  onOpenImportDialog: () => void;
}

export const ProductionHeader: React.FC<ProductionHeaderProps> = ({
  currentProject,
  currentRevision,
  syncStatus,
  backendStatus,
  availableProjects,
  onSelectProject,
  onOpenImportDialog,
}) => {
  return (
    <header className="production-header" style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '12px 20px',
      background: '#1a1d24',
      color: '#ffffff',
      borderBottom: '1px solid #2d3139'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{ fontWeight: 600, fontSize: '16px', letterSpacing: '0.5px', color: '#60a5fa' }}>
          PRODUCTION WORKSPACE
        </div>

        {/* Project Switcher */}
        <select
          value={currentProject?.id || ''}
          onChange={(e) => onSelectProject(e.target.value)}
          style={{
            background: '#252932',
            color: '#fff',
            border: '1px solid #3b4252',
            borderRadius: '6px',
            padding: '6px 12px',
            cursor: 'pointer'
          }}
        >
          {!currentProject && <option value="">Select a Project...</option>}
          {availableProjects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.id})
            </option>
          ))}
        </select>

        {currentRevision && (
          <span style={{ fontSize: '13px', background: '#374151', padding: '4px 8px', borderRadius: '4px' }}>
            Revision: {currentRevision.id} ({currentRevision.status})
          </span>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {/* Sync Status Badge */}
        <span style={{
          fontSize: '12px',
          fontWeight: 500,
          padding: '4px 10px',
          borderRadius: '12px',
          background: syncStatus === 'synced' ? '#065f46' : syncStatus === 'unsaved' ? '#92400e' : '#1e3a8a',
          color: '#ffffff'
        }}>
          ● {syncStatus.toUpperCase()}
        </span>

        {/* Backend Status Badge */}
        <span style={{
          fontSize: '12px',
          padding: '4px 10px',
          borderRadius: '12px',
          background: backendStatus === 'online' ? '#14532d' : '#7f1d1d',
          color: '#ffffff'
        }}>
          Backend: {backendStatus}
        </span>

        {/* Import Action */}
        <button
          onClick={onOpenImportDialog}
          style={{
            background: '#2563eb',
            color: '#fff',
            border: 'none',
            borderRadius: '6px',
            padding: '6px 14px',
            fontWeight: 500,
            cursor: 'pointer'
          }}
        >
          + Import File
        </button>
      </div>
    </header>
  );
};
