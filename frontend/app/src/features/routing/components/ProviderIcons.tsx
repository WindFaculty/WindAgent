import React from 'react';

export interface ProviderIconProps {
  providerId: string;
  size?: number;
  className?: string;
}

export const ProviderIcon: React.FC<ProviderIconProps> = ({ providerId, size = 28 }) => {
  const normalized = providerId.toLowerCase();

  if (normalized.includes('openrouter')) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '7px',
          background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffffff',
          fontWeight: 800,
          fontSize: size * 0.46,
          boxShadow: '0 2px 8px rgba(59, 130, 246, 0.4)',
          flexShrink: 0,
        }}
      >
        <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 16v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          <polyline points="15 12 21 12 18 9" />
          <polyline points="18 15 21 12" />
        </svg>
      </div>
    );
  }

  if (normalized.includes('google') || normalized.includes('gemini')) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '7px',
          background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
          border: '1px solid rgba(59, 130, 246, 0.3)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.4)',
        }}
      >
        <svg width={size * 0.65} height={size * 0.65} viewBox="0 0 24 24" fill="none">
          <path
            d="M12 2L14.4 8.6L21 11L14.4 13.4L12 20L9.6 13.4L3 11L9.6 8.6L12 2Z"
            fill="url(#google-sparkle-grad)"
          />
          <defs>
            <linearGradient id="google-sparkle-grad" x1="3" y1="2" x2="21" y2="20" gradientUnits="userSpaceOnUse">
              <stop stopColor="#38bdf8" />
              <stop offset="0.5" stopColor="#818cf8" />
              <stop offset="1" stopColor="#c084fc" />
            </linearGradient>
          </defs>
        </svg>
      </div>
    );
  }

  if (normalized.includes('groq')) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '7px',
          background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffffff',
          fontWeight: 900,
          fontSize: size * 0.38,
          boxShadow: '0 2px 8px rgba(249, 115, 22, 0.4)',
          letterSpacing: '-0.5px',
          flexShrink: 0,
        }}
      >
        groq
      </div>
    );
  }

  if (normalized.includes('anthropic') || normalized.includes('claude')) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '7px',
          background: 'linear-gradient(135deg, #d97706 0%, #b45309 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffffff',
          fontWeight: 800,
          fontSize: size * 0.46,
          boxShadow: '0 2px 8px rgba(217, 119, 6, 0.4)',
          flexShrink: 0,
        }}
      >
        AI
      </div>
    );
  }

  if (normalized.includes('ollama') || normalized.includes('local')) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '7px',
          background: 'linear-gradient(135deg, #334155 0%, #1e293b 100%)',
          border: '1px solid rgba(255, 255, 255, 0.15)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffffff',
          flexShrink: 0,
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3)',
        }}
      >
        <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none" stroke="#e2e8f0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="9" />
          <path d="M9 10h.01" />
          <path d="M15 10h.01" />
          <path d="M9.5 15a3.5 3.5 0 0 0 5 0" />
        </svg>
      </div>
    );
  }

  if (normalized.includes('openai')) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '7px',
          background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffffff',
          flexShrink: 0,
          boxShadow: '0 2px 8px rgba(16, 185, 129, 0.35)',
        }}
      >
        <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 3v3" />
          <path d="M12 18v3" />
          <path d="M3 12h3" />
          <path d="M18 12h3" />
          <path d="m5.6 5.6 2.1 2.1" />
          <path d="m16.3 16.3 2.1 2.1" />
          <path d="m5.6 18.4 2.1-2.1" />
          <path d="m16.3 7.7 2.1-2.1" />
        </svg>
      </div>
    );
  }

  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: '7px',
        background: 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#ffffff',
        fontWeight: 700,
        fontSize: size * 0.46,
        flexShrink: 0,
      }}
    >
      {providerId.slice(0, 2).toUpperCase()}
    </div>
  );
};

export interface ModelBrandIconProps {
  modelName: string;
  size?: number;
}

export const ModelBrandIcon: React.FC<ModelBrandIconProps> = ({ modelName, size = 22 }) => {
  const norm = modelName.toLowerCase();

  // DeepSeek Whale icon
  if (norm.includes('deepseek')) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '6px',
          background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffffff',
          flexShrink: 0,
        }}
      >
        <svg width={size * 0.65} height={size * 0.65} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 13c1.5-3 5-6 10-6 3.5 0 6 2 8 4-1 1-3 1-5 0-3 2-6 2-8 0-2 2-3 2-5 2z" />
          <circle cx="8" cy="10" r="1" fill="currentColor" />
        </svg>
      </div>
    );
  }

  // Qwen Hexagon Flower icon
  if (norm.includes('qwen')) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '6px',
          background: 'linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffffff',
          flexShrink: 0,
        }}
      >
        <svg width={size * 0.68} height={size * 0.68} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2l3 5h6l-4 5 3 6-7-3-7 3 3-6-4-5h6z" />
        </svg>
      </div>
    );
  }

  // Meta Llama Infinity loop
  if (norm.includes('llama') || norm.includes('meta')) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '6px',
          background: 'linear-gradient(135deg, #2563eb 0%, #1e40af 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffffff',
          flexShrink: 0,
        }}
      >
        <svg width={size * 0.72} height={size * 0.72} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18.178 8c5.096 0 5.096 8 0 8-5.095 0-7.133-8-12.739-8-4.585 0-4.585 8 0 8 5.606 0 7.644-8 12.74-8z" />
        </svg>
      </div>
    );
  }

  // Claude / Anthropic
  if (norm.includes('claude') || norm.includes('anthropic')) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '6px',
          background: 'linear-gradient(135deg, #d97706 0%, #b45309 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffffff',
          fontWeight: 800,
          fontSize: size * 0.45,
          flexShrink: 0,
        }}
      >
        A\
      </div>
    );
  }

  // OpenAI
  if (norm.includes('gpt') || norm.includes('o1') || norm.includes('o3') || norm.includes('openai')) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '6px',
          background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffffff',
          flexShrink: 0,
        }}
      >
        <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
        </svg>
      </div>
    );
  }

  // Gemini / Google
  if (norm.includes('gemini') || norm.includes('google')) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '6px',
          background: 'linear-gradient(135deg, #0284c7 0%, #6366f1 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <svg width={size * 0.65} height={size * 0.65} viewBox="0 0 24 24" fill="#ffffff">
          <path d="M12 2L14.4 8.6L21 11L14.4 13.4L12 20L9.6 13.4L3 11L9.6 8.6L12 2Z" />
        </svg>
      </div>
    );
  }

  // Default fallback icon
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: '6px',
        backgroundColor: 'rgba(255, 255, 255, 0.1)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#94a3b8',
        fontSize: size * 0.42,
        fontWeight: 700,
        flexShrink: 0,
      }}
    >
      AI
    </div>
  );
};
