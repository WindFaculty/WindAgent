import React from 'react';
import type { TrafficDistributionItem } from '@windagent/api-contracts';

interface TrafficDistributionProps {
  distribution: TrafficDistributionItem[];
}

export const TrafficDistribution: React.FC<TrafficDistributionProps> = ({ distribution }) => {
  return (
    <div
      style={{
        padding: '20px',
        borderRadius: '10px',
        backgroundColor: 'var(--bg-panel, #111827)',
        border: '1px solid var(--border-color, #1f2937)',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
      }}
    >
      <div>
        <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary, #f9fafb)' }}>
          Traffic Distribution Breakdown
        </h3>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted, #9ca3af)' }}>
          Live percentage of requests served across models and gateways.
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {distribution.map((item) => (
          <div key={item.model_id} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.85rem' }}>
              <div>
                <strong style={{ color: 'var(--text-primary, #f9fafb)' }}>{item.model_name}</strong>
                <span style={{ color: 'var(--text-muted, #9ca3af)', marginLeft: '8px', fontSize: '0.78rem' }}>
                  ({item.provider})
                </span>
              </div>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-muted, #9ca3af)', fontSize: '0.78rem' }}>
                  {item.request_count.toLocaleString()} reqs
                </span>
                <strong style={{ color: '#38bdf8', minWidth: '48px', textAlign: 'right' }}>
                  {item.percentage}%
                </strong>
              </div>
            </div>

            {/* Progress Bar */}
            <div
              style={{
                width: '100%',
                height: '8px',
                borderRadius: '4px',
                backgroundColor: 'var(--bg-subpanel, #1e293b)',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  width: `${item.percentage}%`,
                  height: '100%',
                  borderRadius: '4px',
                  backgroundColor: '#3b82f6',
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
