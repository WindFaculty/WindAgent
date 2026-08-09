import React from 'react';
import { ScreenplayReadModelDTO, DraftSaveStatus } from '@windagent/production-contracts';

interface ScreenplayHeaderProps {
  readModel: ScreenplayReadModelDTO | null;
  editorMode: 'STRUCTURED' | 'TEXT';
  saveStatus: DraftSaveStatus;
  onToggleMode: (mode: 'STRUCTURED' | 'TEXT') => void;
  onCreateDraft: () => void;
  onLockRevision: () => void;
  onSaveDraft: () => void;
}

export const ScreenplayHeader: React.FC<ScreenplayHeaderProps> = ({
  readModel,
  editorMode,
  saveStatus,
  onToggleMode,
  onCreateDraft,
  onLockRevision,
  onSaveDraft,
}) => {
  const isLocked = readModel?.is_locked ?? false;
  const revId = readModel?.revision_id ?? 'rev_001';
  const blockingIssues = readModel?.validation?.blocking_count ?? 0;

  const saveStatusBadge = () => {
    switch (saveStatus) {
      case 'SAVED':
      case 'SERVER':
        return <span style={{ color: '#10B981', fontSize: '0.8rem', fontWeight: 600 }}>● All changes saved</span>;
      case 'LOCAL_MODIFIED':
        return <span style={{ color: '#F59E0B', fontSize: '0.8rem', fontWeight: 600 }}>● Unsaved local edits</span>;
      case 'SAVING':
        return <span style={{ color: '#3B82F6', fontSize: '0.8rem', fontWeight: 600 }}>● Saving draft...</span>;
      case 'CONFLICT':
      case 'FAILED':
        return <span style={{ color: '#EF4444', fontSize: '0.8rem', fontWeight: 600 }}>● Save conflict</span>;
      default:
        return null;
    }
  };

  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.75rem 1.25rem',
        backgroundColor: '#1E1E2E',
        borderBottom: '1px solid #313244',
        color: '#CDD6F4',
        fontFamily: 'Inter, system-ui, sans-serif',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#F5E0DC' }}>
            {readModel?.title || 'Screenplay Workspace'}
          </h2>
          <div style={{ fontSize: '0.75rem', color: '#A6ADC8', marginTop: '0.15rem' }}>
            Project: <code style={{ color: '#89B4FA' }}>{readModel?.project_id || 'proj_01'}</code>
          </div>
        </div>

        {/* Revision & Lock Badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginLeft: '1rem' }}>
          <span
            style={{
              padding: '0.2rem 0.6rem',
              borderRadius: '6px',
              fontSize: '0.75rem',
              fontWeight: 600,
              backgroundColor: isLocked ? '#F38BA8' : '#A6E3A1',
              color: '#11111B',
            }}
          >
            {revId} ({isLocked ? 'LOCKED' : 'DRAFT'})
          </span>

          {isLocked ? (
            <button
              onClick={onCreateDraft}
              style={{
                padding: '0.3rem 0.75rem',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: '#89B4FA',
                color: '#11111B',
                fontWeight: 600,
                fontSize: '0.75rem',
                cursor: 'pointer',
              }}
            >
              + Create New Draft to Edit
            </button>
          ) : (
            <button
              onClick={onLockRevision}
              disabled={blockingIssues > 0}
              style={{
                padding: '0.3rem 0.75rem',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: blockingIssues > 0 ? '#45475A' : '#FAB387',
                color: blockingIssues > 0 ? '#6C7086' : '#11111B',
                fontWeight: 600,
                fontSize: '0.75rem',
                cursor: blockingIssues > 0 ? 'not-allowed' : 'pointer',
              }}
              title={blockingIssues > 0 ? 'Resolve blocking validation issues before locking' : 'Lock revision'}
            >
              🔒 Lock Revision
            </button>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
        {saveStatusBadge()}

        {!isLocked && (
          <button
            onClick={onSaveDraft}
            disabled={saveStatus === 'SAVED' || saveStatus === 'SERVER'}
            style={{
              padding: '0.35rem 0.85rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: saveStatus === 'LOCAL_MODIFIED' ? '#A6E3A1' : '#313244',
              color: saveStatus === 'LOCAL_MODIFIED' ? '#11111B' : '#A6ADC8',
              fontWeight: 600,
              fontSize: '0.75rem',
              cursor: saveStatus === 'LOCAL_MODIFIED' ? 'pointer' : 'default',
            }}
          >
            💾 Save Draft
          </button>
        )}

        {/* Mode Switcher Toggle */}
        <div style={{ display: 'flex', backgroundColor: '#313244', borderRadius: '8px', padding: '0.15rem' }}>
          <button
            onClick={() => onToggleMode('STRUCTURED')}
            style={{
              padding: '0.3rem 0.75rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: editorMode === 'STRUCTURED' ? '#89B4FA' : 'transparent',
              color: editorMode === 'STRUCTURED' ? '#11111B' : '#CDD6F4',
              fontWeight: 600,
              fontSize: '0.75rem',
              cursor: 'pointer',
            }}
          >
            Structured
          </button>
          <button
            onClick={() => onToggleMode('TEXT')}
            style={{
              padding: '0.3rem 0.75rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: editorMode === 'TEXT' ? '#89B4FA' : 'transparent',
              color: editorMode === 'TEXT' ? '#11111B' : '#CDD6F4',
              fontWeight: 600,
              fontSize: '0.75rem',
              cursor: 'pointer',
            }}
          >
            Text (Fountain)
          </button>
        </div>
      </div>
    </header>
  );
};
