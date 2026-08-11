import React, { useState } from 'react';
import { ThreeWayDiffResultDTO, ResolutionStrategy } from '@windagent/production-contracts';
import { SemanticDiffViewer } from './SemanticDiffViewer';

export interface ConflictResolverModalProps {
  isOpen: boolean;
  diffResult: ThreeWayDiffResultDTO | null;
  onResolve: (strategy: ResolutionStrategy, customPayload?: Record<string, unknown>) => void;
  onDiscardLocalDraft: () => void;
  onClose: () => void;
}

export const ConflictResolverModal: React.FC<ConflictResolverModalProps> = ({
  isOpen,
  diffResult,
  onResolve,
  onDiscardLocalDraft,
  onClose,
}) => {
  const [selectedStrategy, setSelectedStrategy] = useState<ResolutionStrategy>('MERGE_CANDIDATE');
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);

  if (!isOpen || !diffResult) {
    return null;
  }

  const canAutoMerge = diffResult.can_auto_merge;

  return (
    <div
      data-testid="conflict-resolver-modal"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        style={{
          width: '720px',
          maxHeight: '90vh',
          backgroundColor: '#ffffff',
          borderRadius: '8px',
          boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 24px',
            backgroundColor: '#fafafa',
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <h3 style={{ margin: 0, fontSize: '18px', color: '#1f1f1f' }}>
              3-Way Semantic Conflict Resolver
            </h3>
            <span style={{ fontSize: '12px', color: '#8c8c8c' }}>
              Base: {diffResult.base_revision_id} | Server Latest: {diffResult.latest_revision_id}
            </span>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '20px',
              cursor: 'pointer',
              color: '#8c8c8c',
            }}
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '20px 24px', overflowY: 'auto', flex: 1 }}>
          <div
            style={{
              padding: '12px 16px',
              borderRadius: '6px',
              marginBottom: '16px',
              backgroundColor: canAutoMerge ? '#f6ffed' : '#fff1f0',
              border: `1px solid ${canAutoMerge ? '#b7eb8f' : '#ffa39e'}`,
              color: canAutoMerge ? '#389e0d' : '#cf1322',
            }}
          >
            <strong>Status: {diffResult.overall_classification}</strong>
            <p style={{ margin: '4px 0 0 0', fontSize: '13px' }}>
              {canAutoMerge
                ? 'Non-overlapping changes detected. Safe auto-merge candidate available.'
                : 'Overlapping field modifications or entity deletions detected. Review required before merging.'}
            </p>
          </div>

          <SemanticDiffViewer entityConflicts={diffResult.entity_conflicts} />

          {/* Strategy Selection */}
          <div style={{ marginTop: '20px' }}>
            <label style={{ fontWeight: 'bold', fontSize: '14px', display: 'block', marginBottom: '8px' }}>
              Resolution Strategy:
            </label>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                data-testid="strategy-merge"
                disabled={!canAutoMerge}
                onClick={() => setSelectedStrategy('MERGE_CANDIDATE')}
                style={{
                  flex: 1,
                  padding: '10px',
                  borderRadius: '6px',
                  border: `2px solid ${selectedStrategy === 'MERGE_CANDIDATE' ? '#1890ff' : '#d9d9d9'}`,
                  backgroundColor: selectedStrategy === 'MERGE_CANDIDATE' ? '#e6f7ff' : '#ffffff',
                  cursor: canAutoMerge ? 'pointer' : 'not-allowed',
                  opacity: canAutoMerge ? 1 : 0.5,
                  textAlign: 'left',
                }}
              >
                <div style={{ fontWeight: 600 }}>Merge Into New Revision</div>
                <div style={{ fontSize: '12px', color: '#8c8c8c' }}>Combine non-overlapping edits</div>
              </button>

              <button
                data-testid="strategy-local"
                onClick={() => setSelectedStrategy('ACCEPT_LOCAL')}
                style={{
                  flex: 1,
                  padding: '10px',
                  borderRadius: '6px',
                  border: `2px solid ${selectedStrategy === 'ACCEPT_LOCAL' ? '#1890ff' : '#d9d9d9'}`,
                  backgroundColor: selectedStrategy === 'ACCEPT_LOCAL' ? '#e6f7ff' : '#ffffff',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <div style={{ fontWeight: 600 }}>Keep My Local Edit</div>
                <div style={{ fontSize: '12px', color: '#8c8c8c' }}>Overwrite remote with local draft</div>
              </button>

              <button
                data-testid="strategy-remote"
                onClick={() => setSelectedStrategy('ACCEPT_REMOTE')}
                style={{
                  flex: 1,
                  padding: '10px',
                  borderRadius: '6px',
                  border: `2px solid ${selectedStrategy === 'ACCEPT_REMOTE' ? '#1890ff' : '#d9d9d9'}`,
                  backgroundColor: selectedStrategy === 'ACCEPT_REMOTE' ? '#e6f7ff' : '#ffffff',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <div style={{ fontWeight: 600 }}>Accept Remote Server</div>
                <div style={{ fontSize: '12px', color: '#8c8c8c' }}>Use current server revision</div>
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '16px 24px',
            backgroundColor: '#fafafa',
            borderTop: '1px solid #f0f0f0',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <button
            data-testid="discard-local-draft-btn"
            onClick={() => setShowDiscardConfirm(true)}
            style={{
              padding: '8px 16px',
              backgroundColor: '#fff',
              border: '1px solid #ff4d4f',
              color: '#ff4d4f',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Discard Local Changes
          </button>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={onClose}
              style={{
                padding: '8px 16px',
                backgroundColor: '#ffffff',
                border: '1px solid #d9d9d9',
                borderRadius: '4px',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              data-testid="submit-resolution-btn"
              onClick={() => onResolve(selectedStrategy, diffResult.auto_merged_payload)}
              style={{
                padding: '8px 16px',
                backgroundColor: '#1890ff',
                color: '#ffffff',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              Apply Resolution
            </button>
          </div>
        </div>

        {/* Confirmation Modal overlay for Discard Local Draft */}
        {showDiscardConfirm && (
          <div
            data-testid="discard-confirm-dialog"
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(0,0,0,0.4)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 1100,
            }}
          >
            <div
              style={{
                width: '400px',
                padding: '24px',
                backgroundColor: '#ffffff',
                borderRadius: '8px',
                boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
              }}
            >
              <h4 style={{ margin: '0 0 12px 0', color: '#ff4d4f' }}>
                Confirm Discard Local Changes?
              </h4>
              <p style={{ fontSize: '14px', color: '#595959', marginBottom: '20px' }}>
                Are you sure you want to discard your unsaved local edits? This action cannot be undone.
              </p>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button
                  onClick={() => setShowDiscardConfirm(false)}
                  style={{
                    padding: '6px 14px',
                    backgroundColor: '#ffffff',
                    border: '1px solid #d9d9d9',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                >
                  Keep Editing
                </button>
                <button
                  data-testid="confirm-discard-btn"
                  onClick={() => {
                    setShowDiscardConfirm(false);
                    onDiscardLocalDraft();
                  }}
                  style={{
                    padding: '6px 14px',
                    backgroundColor: '#ff4d4f',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  Yes, Discard
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
