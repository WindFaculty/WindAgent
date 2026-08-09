import React, { useState } from 'react';
import { ProductionPlatformAdapter } from '@windagent/production-platform';
import { SelectedFile } from '@windagent/production-contracts';

export interface ImportFileDialogProps {
  platformAdapter: ProductionPlatformAdapter;
  isOpen: boolean;
  onClose: () => void;
  onFilesSelected: (files: SelectedFile[]) => void;
}

export const ImportFileDialog: React.FC<ImportFileDialogProps> = ({
  platformAdapter,
  isOpen,
  onClose,
  onFilesSelected,
}) => {
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleChoose = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const files = await platformAdapter.selectLocalFile({ multiple: true });
      onFilesSelected(files);
      onClose();
    } catch (err) {
      if ((err as Error).name === 'PlatformError' && (err as { code?: string }).code === 'CANCELLED') {
        // User cancelled, clear error
        setErrorMsg(null);
      } else {
        setErrorMsg((err as Error).message);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0, 0, 0, 0.65)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000
    }}>
      <div style={{
        background: '#1e222b',
        border: '1px solid #374151',
        borderRadius: '12px',
        padding: '24px',
        width: '440px',
        color: '#fff'
      }}>
        <h3 style={{ marginTop: 0, marginBottom: '12px', fontSize: '18px' }}>Import Assets or Script</h3>
        <p style={{ color: '#9ca3af', fontSize: '14px', marginBottom: '20px' }}>
          Platform filesystem support: {platformAdapter.supportsLocalFilesystem() ? 'Native Filesystem' : 'Web Upload'}
        </p>

        {errorMsg && (
          <div style={{ background: '#7f1d1d', color: '#fca5a5', padding: '10px', borderRadius: '6px', marginBottom: '16px', fontSize: '13px' }}>
            {errorMsg}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: '1px solid #4b5563', color: '#d1d5db', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer' }}
          >
            Cancel
          </button>
          <button
            onClick={handleChoose}
            disabled={loading}
            style={{ background: '#2563eb', border: 'none', color: '#fff', padding: '8px 18px', borderRadius: '6px', cursor: 'pointer', fontWeight: 600 }}
          >
            {loading ? 'Opening...' : 'Browse File...'}
          </button>
        </div>
      </div>
    </div>
  );
};
