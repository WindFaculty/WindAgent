import React from 'react';
import type { TrafficDistributionItem } from '@windagent/api-contracts';
import { BarChart2, Cpu, Activity } from 'lucide-react';

interface TrafficDistributionProps {
  distribution: TrafficDistributionItem[];
}

export const TrafficDistribution: React.FC<TrafficDistributionProps> = ({ distribution }) => {
  const getProviderConfig = (provider: string, modelName: string) => {
    const name = modelName.toLowerCase();
    if (name.includes('claude') || provider.toLowerCase().includes('anthropic')) {
      return {
        color: '#fb923c',
        gradient: 'linear-gradient(90deg, #f97316 0%, #fb923c 100%)',
        bg: 'rgba(251, 146, 60, 0.12)',
        border: 'rgba(251, 146, 60, 0.3)',
      };
    }
    if (name.includes('gemini') || provider.toLowerCase().includes('google')) {
      return {
        color: '#60a5fa',
        gradient: 'linear-gradient(90deg, #2563eb 0%, #60a5fa 100%)',
        bg: 'rgba(96, 165, 250, 0.12)',
        border: 'rgba(96, 165, 250, 0.3)',
      };
    }
    if (name.includes('gpt') || provider.toLowerCase().includes('openai')) {
      return {
        color: '#2dd4bf',
        gradient: 'linear-gradient(90deg, #0d9488 0%, #2dd4bf 100%)',
        bg: 'rgba(45, 212, 191, 0.12)',
        border: 'rgba(45, 212, 191, 0.3)',
      };
    }
    if (name.includes('deepseek') || provider.toLowerCase().includes('deepseek')) {
      return {
        color: '#c084fc',
        gradient: 'linear-gradient(90deg, #9333ea 0%, #c084fc 100%)',
        bg: 'rgba(192, 132, 252, 0.12)',
        border: 'rgba(192, 132, 252, 0.3)',
      };
    }
    if (name.includes('qwen') || provider.toLowerCase().includes('ollama') || provider.toLowerCase().includes('local')) {
      return {
        color: '#4edea3',
        gradient: 'linear-gradient(90deg, #059669 0%, #4edea3 100%)',
        bg: 'rgba(78, 222, 163, 0.12)',
        border: 'rgba(78, 222, 163, 0.3)',
      };
    }
    return {
      color: '#38bdf8',
      gradient: 'linear-gradient(90deg, #0284c7 0%, #38bdf8 100%)',
      bg: 'rgba(56, 189, 248, 0.12)',
      border: 'rgba(56, 189, 248, 0.3)',
    };
  };

  const totalReqs = distribution.reduce((sum, item) => sum + item.request_count, 0);

  return (
    <div
      style={{
        padding: '24px',
        borderRadius: '14px',
        backgroundColor: 'rgba(19, 27, 46, 0.75)',
        border: '1px solid rgba(66, 71, 84, 0.4)',
        backdropFilter: 'blur(16px)',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        boxShadow: '0 8px 32px -4px rgba(0, 0, 0, 0.4)',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <BarChart2 size={20} color="#38bdf8" />
            <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main, #dae2fd)' }}>
              Live Traffic & Gateway Load Breakdown
            </h3>
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '0.84rem', color: 'var(--text-muted, #c2c6d6)' }}>
            Real-time percentage and volume of token requests routed across active AI endpoints.
          </p>
        </div>

        <div
          style={{
            padding: '4px 12px',
            borderRadius: '6px',
            backgroundColor: 'rgba(11, 19, 38, 0.8)',
            border: '1px solid rgba(66, 71, 84, 0.5)',
            fontSize: '0.8rem',
            color: 'var(--text-main, #dae2fd)',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Activity size={13} color="#4edea3" />
          <span>Total Stream: <strong style={{ color: '#38bdf8' }}>{totalReqs.toLocaleString()}</strong> calls</span>
        </div>
      </div>

      {/* Distribution Bars */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {distribution.map((item) => {
          const config = getProviderConfig(item.provider, item.model_name);

          return (
            <div
              key={item.model_id}
              style={{
                padding: '14px 16px',
                borderRadius: '10px',
                backgroundColor: 'rgba(11, 19, 38, 0.6)',
                border: '1px solid rgba(66, 71, 84, 0.3)',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                transition: 'border-color 0.2s ease',
              }}
            >
              {/* Top Row: Model Info and Percentage */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div
                    style={{
                      width: '24px',
                      height: '24px',
                      borderRadius: '6px',
                      backgroundColor: config.bg,
                      border: `1px solid ${config.border}`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: config.color,
                    }}
                  >
                    <Cpu size={14} />
                  </div>
                  <strong style={{ color: 'var(--text-main, #dae2fd)', fontSize: '0.9rem' }}>{item.model_name}</strong>
                  <span
                    style={{
                      fontSize: '0.72rem',
                      fontWeight: 600,
                      padding: '1px 6px',
                      borderRadius: '4px',
                      backgroundColor: config.bg,
                      color: config.color,
                      border: `1px solid ${config.border}`,
                    }}
                  >
                    {item.provider}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                  <span style={{ color: 'var(--text-dim, #8c909f)', fontSize: '0.78rem' }}>
                    {item.request_count.toLocaleString()} reqs
                  </span>
                  <div
                    style={{
                      minWidth: '58px',
                      textAlign: 'right',
                      fontSize: '1rem',
                      fontWeight: 800,
                      color: config.color,
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {item.percentage}%
                  </div>
                </div>
              </div>

              {/* Glowing Progress Bar */}
              <div
                style={{
                  width: '100%',
                  height: '8px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(255, 255, 255, 0.06)',
                  overflow: 'hidden',
                  position: 'relative',
                }}
              >
                <div
                  style={{
                    width: `${item.percentage}%`,
                    height: '100%',
                    borderRadius: '6px',
                    background: config.gradient,
                    boxShadow: `0 0 12px ${config.color}66`,
                    transition: 'width 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
