import React from 'react';
import { RecoveryStatus, ProductionRecoverySnapshot } from '@windagent/production-contracts';

export interface RecoveryPromptBannerProps {
  status: RecoveryStatus;
  activeSnapshot: ProductionRecoverySnapshot | null;
  isOffline?: boolean;
  onReviewStaleDraft?: () => void;
  onDiscardDraft?: () => void;
  onOpenConflictResolver?: () => void;
  onReconnect?: () => void;
}

export const RecoveryPromptBanner: React.FC<RecoveryPromptBannerProps> = ({
  status,
  activeSnapshot,
  isOffline,
  onReviewStaleDraft,
  onDiscardDraft,
  onOpenConflictResolver,
  onReconnect,
}) => {
  if (status === 'IDLE' && !isOffline) {
    return null;
  }

  if (isOffline || status === 'OFFLINE_READ_ONLY') {
    return (
      <div
        data-testid="recovery-banner-offline"
        style={{
          backgroundColor: '#fffbe6',
          border: '1px solid #ffe58f',
          padding: '10px 16px',
          borderRadius: '6px',
          display: 'flex',
          justify: 'space-between',
          alignItems: 'center',
          marginBottom: '12px',
          color: '#8c6b00',
        }}
      >
        <div>
          <strong>⚡ Offline Mode (Read-Only)</strong>: You are currently working offline. Local edits are stored safely in recovery snapshot but cannot be committed until reconnected.
        </div>
        {onReconnect && (
          <button
            onClick={onReconnect}
            style={{
              padding: '4px 12px',
              backgroundColor: '#faad14',
              color: '#fff',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Reconnect
          </button>
        )}
      </div>
    );
  }

  if (status === 'RECOVERED' && activeSnapshot) {
    return (
      <div
        data-testid="recovery-banner-recovered"
        style={{
          backgroundColor: '#e6f7ff',
          border: '1px solid #91d5ff',
          padding: '10px 16px',
          borderRadius: '6px',
          display: 'flex',
          justify: 'space-between',
          alignItems: 'center',
          marginBottom: '12px',
          color: '#0050b3',
        }}
      >
        <div>
          <strong>📦 Unsaved Local Draft Restored</strong>: Recovered unsaved local edits from {activeSnapshot.saved_at}.
        </div>
        <div>
          {onDiscardDraft && (
            <button
              onClick={onDiscardDraft}
              style={{
                padding: '4px 12px',
                backgroundColor: '#ffffff',
                border: '1px solid #d9d9d9',
                borderRadius: '4px',
                cursor: 'pointer',
                marginRight: '8px',
              }}
            >
              Discard Draft
            </button>
          )}
        </div>
      </div>
    );
  }

  if (status === 'STALE_DRAFT_DETECTED') {
    return (
      <div
        data-testid="recovery-banner-stale"
        style={{
          backgroundColor: '#fff0f6',
          border: '1px solid #ffadd2',
          padding: '10px 16px',
          borderRadius: '6px',
          display: 'flex',
          justify: 'space-between',
          alignItems: 'center',
          marginBottom: '12px',
          color: '#c41d7f',
        }}
      >
        <div>
          <strong>⚠️ Stale Draft Detected</strong>: Server state has advanced while your app was closed/offline. Review changes before merging.
        </div>
        <div>
          {onReviewStaleDraft && (
            <button
              onClick={onReviewStaleDraft}
              style={{
                padding: '4px 12px',
                backgroundColor: '#eb2f96',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                marginRight: '8px',
              }}
            >
              Compare & Resolve
            </button>
          )}
          {onDiscardDraft && (
            <button
              onClick={onDiscardDraft}
              style={{
                padding: '4px 12px',
                backgroundColor: '#ffffff',
                border: '1px solid #d9d9d9',
                borderRadius: '4px',
                cursor: 'pointer',
              }}
            >
              Discard Draft
            </button>
          )}
        </div>
      </div>
    );
  }

  if (status === 'CONFLICT') {
    return (
      <div
        data-testid="recovery-banner-conflict"
        style={{
          backgroundColor: '#fff1f0',
          border: '1px solid #ffa39e',
          padding: '10px 16px',
          borderRadius: '6px',
          display: 'flex',
          justify: 'space-between',
          alignItems: 'center',
          marginBottom: '12px',
          color: '#cf1322',
        }}
      >
        <div>
          <strong>🚫 409 Concurrent Edit Conflict</strong>: Your edit was rejected because another contributor or agent committed changes first.
        </div>
        {onOpenConflictResolver && (
          <button
            onClick={onOpenConflictResolver}
            style={{
              padding: '4px 12px',
              backgroundColor: '#ff4d4f',
              color: '#fff',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Open 3-Way Merge Resolver
          </button>
        )}
      </div>
    );
  }

  return null;
};
