import React from 'react';

/**
 * ModelCapabilities — Visual capability matrix for a canonical ModelDefinition.
 */
interface ModelCapabilitiesProps {
  capabilities: string[];
  isLocal?: boolean;
}

const CAPABILITY_CONFIG: Record<string, { label: string; bg: string; color: string; icon: string }> = {
  chat: { label: 'Chat', bg: 'rgba(59, 130, 246, 0.12)', color: '#60a5fa', icon: 'chat' },
  code: { label: 'Code', bg: 'rgba(168, 85, 247, 0.12)', color: '#c084fc', icon: 'code' },
  vision: { label: 'Vision', bg: 'rgba(236, 72, 153, 0.12)', color: '#f472b6', icon: 'visibility' },
  audio: { label: 'Audio', bg: 'rgba(245, 158, 11, 0.12)', color: '#fbbf24', icon: 'mic' },
  tools: { label: 'Tools', bg: 'rgba(16, 185, 129, 0.12)', color: '#34d399', icon: 'build' },
  reasoning: { label: 'Reasoning', bg: 'rgba(239, 68, 68, 0.12)', color: '#f87171', icon: 'psychology' },
  embedding: { label: 'Embedding', bg: 'rgba(99, 102, 241, 0.12)', color: '#818cf8', icon: 'dataset' },
};

export const ModelCapabilities: React.FC<ModelCapabilitiesProps> = ({ capabilities, isLocal }) => {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
      {isLocal && (
        <span
          style={{
            fontSize: '0.72rem',
            fontWeight: 700,
            padding: '2px 8px',
            borderRadius: '4px',
            backgroundColor: 'rgba(34, 197, 94, 0.15)',
            color: '#4ade80',
            border: '1px solid rgba(34, 197, 94, 0.3)',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }}
        >
          Local / Offline
        </span>
      )}
      {capabilities.map((cap) => {
        const conf = CAPABILITY_CONFIG[cap.toLowerCase()] || {
          label: cap,
          bg: 'rgba(156, 163, 175, 0.12)',
          color: '#9ca3af',
          icon: 'token',
        };
        return (
          <span
            key={cap}
            style={{
              fontSize: '0.72rem',
              fontWeight: 600,
              padding: '2px 8px',
              borderRadius: '4px',
              backgroundColor: conf.bg,
              color: conf.color,
              border: `1px solid ${conf.color}22`,
            }}
          >
            {conf.label}
          </span>
        );
      })}
    </div>
  );
};
