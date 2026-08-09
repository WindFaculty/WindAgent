import React from 'react';

export interface VideoWorkspacePlaceholderProps {
  projectId: string;
  revisionId?: string;
  selectedEntityId?: string;
}

export const VideoWorkspacePlaceholder: React.FC<VideoWorkspacePlaceholderProps> = ({
  projectId,
  revisionId,
  selectedEntityId,
}) => {
  return (
    <div style={{ padding: '24px', color: '#e5e7eb' }}>
      <h2 style={{ fontSize: '20px', margin: '0 0 12px 0', color: '#f472b6' }}>🎬 Video Workspace (3D & Compositor)</h2>
      <div style={{ background: '#252932', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
        <p style={{ margin: '0 0 8px 0' }}>Project: <strong>{projectId}</strong></p>
        {revisionId && <p style={{ margin: '0 0 8px 0' }}>Revision: <strong>{revisionId}</strong></p>}
        {selectedEntityId && <p style={{ margin: '0 0 8px 0' }}>Shot Entity: <strong>{selectedEntityId}</strong></p>}
        <div style={{ marginTop: '16px', color: '#9ca3af', fontSize: '14px', fontStyle: 'italic' }}>
          [Stage A Shared Production Shell Placeholder — Video Production & Scene Compositor integration ready]
        </div>
      </div>
    </div>
  );
};
