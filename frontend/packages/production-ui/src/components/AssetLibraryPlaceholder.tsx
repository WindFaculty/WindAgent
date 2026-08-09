import React from 'react';

export interface AssetLibraryPlaceholderProps {
  projectId: string;
  revisionId?: string;
  selectedEntityId?: string;
}

export const AssetLibraryPlaceholder: React.FC<AssetLibraryPlaceholderProps> = ({
  projectId,
  revisionId,
  selectedEntityId,
}) => {
  return (
    <div style={{ padding: '24px', color: '#e5e7eb' }}>
      <h2 style={{ fontSize: '20px', margin: '0 0 12px 0', color: '#34d399' }}>🎨 Asset Library Workspace</h2>
      <div style={{ background: '#252932', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
        <p style={{ margin: '0 0 8px 0' }}>Project: <strong>{projectId}</strong></p>
        {revisionId && <p style={{ margin: '0 0 8px 0' }}>Revision: <strong>{revisionId}</strong></p>}
        {selectedEntityId && <p style={{ margin: '0 0 8px 0' }}>Selected Asset: <strong>{selectedEntityId}</strong></p>}
        <div style={{ marginTop: '16px', color: '#9ca3af', fontSize: '14px', fontStyle: 'italic' }}>
          [Stage A Shared Production Shell Placeholder — Universal Asset Domain will be mounted in Stage D]
        </div>
      </div>
    </div>
  );
};
