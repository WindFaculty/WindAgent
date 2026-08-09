import React from 'react';

export interface ScriptEditorPlaceholderProps {
  projectId: string;
  revisionId?: string;
  selectedEntityId?: string;
}

export const ScriptEditorPlaceholder: React.FC<ScriptEditorPlaceholderProps> = ({
  projectId,
  revisionId,
  selectedEntityId,
}) => {
  return (
    <div style={{ padding: '24px', color: '#e5e7eb' }}>
      <h2 style={{ fontSize: '20px', margin: '0 0 12px 0', color: '#60a5fa' }}>📜 Screenplay Editor</h2>
      <div style={{ background: '#252932', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
        <p style={{ margin: '0 0 8px 0' }}>Project: <strong>{projectId}</strong></p>
        {revisionId && <p style={{ margin: '0 0 8px 0' }}>Revision: <strong>{revisionId}</strong></p>}
        {selectedEntityId && <p style={{ margin: '0 0 8px 0' }}>Scene Entity: <strong>{selectedEntityId}</strong></p>}
        <div style={{ marginTop: '16px', color: '#9ca3af', fontSize: '14px', fontStyle: 'italic' }}>
          [Stage A Shared Production Shell Placeholder — Full Screenplay Editor will be mounted in Stage C]
        </div>
      </div>
    </div>
  );
};
