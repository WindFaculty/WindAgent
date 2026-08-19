import React, { useState } from 'react';
import { X, Upload, CheckCircle2 } from 'lucide-react';

interface ImportEnvModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImport: (detectedKeys: Record<string, string>) => void;
}

export const ImportEnvModal: React.FC<ImportEnvModalProps> = ({ isOpen, onClose, onImport }) => {
  const [envContent, setEnvContent] = useState(
    `# Upstream AI Provider API Keys
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxx
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxx
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxx`
  );
  const [success, setSuccess] = useState(false);

  if (!isOpen) return null;

  const handleParseAndImport = () => {
    const lines = envContent.split('\n');
    const detected: Record<string, string> = {};

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx !== -1) {
        const key = trimmed.slice(0, eqIdx).trim();
        const val = trimmed.slice(eqIdx + 1).trim();
        detected[key] = val;
      }
    }

    onImport(detected);
    setSuccess(true);
    setTimeout(() => {
      setSuccess(false);
      onClose();
    }, 1200);
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
                cursor: 'pointer',
              }}
            >
              <Upload size={14} />
              <span>Import Variables</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
