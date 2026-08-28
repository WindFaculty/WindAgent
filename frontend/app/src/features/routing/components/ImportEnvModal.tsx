import React, { useState } from 'react';
import { X, Upload, CheckCircle2 } from 'lucide-react';

interface ImportEnvModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImport: (detectedKeys: Record<string, string>) => Promise<{ imported: number; errors: string[] }>;
}

export const ImportEnvModal: React.FC<ImportEnvModalProps> = ({ isOpen, onClose, onImport }) => {
  // No prefilled fake keys — user must paste real .env content; placeholder shows format only.
  const [envContent, setEnvContent] = useState('');
  const [success, setSuccess] = useState(false);
  const [parseError, setParseError] = useState('');
  const [isImporting, setIsImporting] = useState(false);

  if (!isOpen) return null;

  const handleParseAndImport = async () => {
    const lines = envContent.split('\n');
    const detected: Record<string, string> = {};

    for (let raw of lines) {
      let trimmed = raw.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      // Support `export KEY=val` prefix commonly present in shell exports
      if (trimmed.toLowerCase().startsWith('export ')) trimmed = trimmed.slice(7).trim();
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx === -1) continue;
      let key = trimmed.slice(0, eqIdx).trim();
      let val = trimmed.slice(eqIdx + 1).trim();
      // Strip inline comment not inside quotes (simple: ` #` separator)
      // Preserve quoted values intact
      if (!((val.startsWith('"') && val.includes('"', 1)) || (val.startsWith("'") && val.includes("'", 1)))) {
        const hashIdx = val.indexOf(' #');
        if (hashIdx !== -1) val = val.slice(0, hashIdx).trim();
      }
      // Strip surrounding single/double quotes
      if ((val.startsWith('"') && val.endsWith('"') && val.length >= 2) || (val.startsWith("'") && val.endsWith("'") && val.length >= 2)) {
        val = val.slice(1, -1);
      }
      // Unescape escaped quotes
      val = val.replace(/\\"/g, '"').replace(/\\'/g, "'");
      if (!key || !val) continue;
      // Skip placeholder values
      if (val === '...' || val.toLowerCase() === 'changeme') continue;
      // Validate key shape
      if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) continue;
      detected[key] = val;
    }

    if (Object.keys(detected).length === 0) {
      setParseError('No valid keys found. Expected format: KEY=value (quotes are optional).');
      setTimeout(() => setParseError(''), 3000);
      return;
    }
    setParseError('');
    setIsImporting(true);
    try {
      const result = await onImport(detected);
      if (result.imported === 0) {
        setParseError(result.errors[0] || 'No matching provider keys could be saved.');
        return;
      }
      setSuccess(true);
      setTimeout(() => {
        setSuccess(false);
        setEnvContent('');
        onClose();
      }, 1200);
    } catch (error) {
      setParseError(error instanceof Error ? error.message : 'Unable to import provider credentials.');
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '20px',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '520px',
          backgroundColor: '#0f172a',
          borderRadius: '14px',
          border: '1px solid rgba(66, 71, 84, 0.6)',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.6)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '16px 20px',
            borderBottom: '1px solid rgba(66, 71, 84, 0.4)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Upload size={18} color="#60a5fa" />
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#f8fafc' }}>
              Import API Keys from .env
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer',
              padding: '4px',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <p style={{ margin: 0, fontSize: '0.78rem', color: '#94a3b8', lineHeight: 1.4 }}>
            Paste your environment variables below. Any recognized keys (OpenRouter, OpenAI, Anthropic, Gemini, Groq) will automatically update provider credentials.
          </p>

          <textarea
            rows={7}
            value={envContent}
            onChange={(e) => setEnvContent(e.target.value)}
            placeholder={`# Paste your real .env — keys are sent to POST /api/v3/providers/{id}/credential (encrypted at rest)\nOPENROUTER_API_KEY=sk-or-v1-...\nOPENAI_API_KEY=sk-proj-...\nANTHROPIC_API_KEY=sk-ant-...\nGEMINI_API_KEY=AIza...\nGROQ_API_KEY=gsk_...`}
            style={{
              width: '100%',
              backgroundColor: 'rgba(0, 0, 0, 0.5)',
              border: '1px solid rgba(66, 71, 84, 0.6)',
              borderRadius: '8px',
              padding: '10px 12px',
              color: '#f8fafc',
              fontFamily: 'var(--font-mono, monospace)',
              fontSize: '0.78rem',
              outline: 'none',
              resize: 'vertical',
            }}
          />

          {parseError && (
            <div role="alert" style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#fbbf24', fontSize: '0.76rem', fontWeight: 600, padding: '6px 8px', borderRadius: '6px', backgroundColor: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.3)' }}>
              {parseError}
            </div>
          )}
          {success && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                color: '#34d399',
                fontSize: '0.78rem',
                fontWeight: 600,
              }}
            >
              <CheckCircle2 size={15} /> Imported keys successfully!
            </div>
          )}

          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '10px',
              paddingTop: '10px',
              borderTop: '1px solid rgba(66, 71, 84, 0.3)',
            }}
          >
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '8px 16px',
                borderRadius: '6px',
                backgroundColor: 'transparent',
                border: '1px solid rgba(66, 71, 84, 0.5)',
                color: '#94a3b8',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>

            <button
              type="button"
              onClick={handleParseAndImport}
              disabled={isImporting}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 18px',
                borderRadius: '6px',
                background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
                border: 'none',
                color: '#ffffff',
                fontSize: '0.8rem',
                fontWeight: 700,
                cursor: isImporting ? 'wait' : 'pointer',
                opacity: isImporting ? 0.7 : 1,
              }}
            >
              <Upload size={14} />
              <span>{isImporting ? 'Importing…' : 'Import Variables'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
