import React from 'react';
import { ArrowRight, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';

export interface ActivityItem {
  id: string;
  type: 'success' | 'warning' | 'error';
  message: string;
  time: string;
}

interface ConnectionActivityPanelProps {
  activities: ActivityItem[];
  onViewAll?: () => void;
}

export const ConnectionActivityPanel: React.FC<ConnectionActivityPanelProps> = ({
  activities,
  onViewAll,
}) => {
  const renderStatusIcon = (type: ActivityItem['type']) => {
    switch (type) {
      case 'success':
        return <CheckCircle2 size={13} color="#34d399" style={{ flexShrink: 0 }} />;
      case 'warning':
        return <AlertTriangle size={13} color="#fbbf24" style={{ flexShrink: 0 }} />;
      case 'error':
        return <XCircle size={13} color="#f87171" style={{ flexShrink: 0 }} />;
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'rgba(11, 19, 38, 0.85)',
        borderRadius: '14px',
        border: '1px solid rgba(66, 71, 84, 0.4)',
        backdropFilter: 'blur(16px)',
        overflow: 'hidden',
        padding: '16px 18px',
        gap: '14px',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2
          style={{
            margin: 0,
            fontSize: '0.95rem',
            fontWeight: 700,
            color: 'var(--text-main, #f8fafc)',
            letterSpacing: '-0.01em',
          }}
        >
          Connection Activity
        </h2>
        <button
          type="button"
          onClick={onViewAll}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#60a5fa',
            fontSize: '0.72rem',
            fontWeight: 600,
            cursor: 'pointer',
            padding: 0,
          }}
        >
          View All
        </button>
      </div>

      {/* Activity Feed */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {activities.map((act) => (
          <div
            key={act.id}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: '8px',
              fontSize: '0.74rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
              {renderStatusIcon(act.type)}
              <span
                style={{
                  color: act.type === 'error' ? '#fca5a5' : act.type === 'warning' ? '#fde047' : '#cbd5e1',
                  lineHeight: 1.3,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title={act.message}
              >
                {act.message}
              </span>
            </div>

            <span
              style={{
                fontSize: '0.68rem',
                color: '#64748b',
                whiteSpace: 'nowrap',
                flexShrink: 0,
              }}
            >
              {act.time}
            </span>
          </div>
        ))}
      </div>

      {/* Footer link */}
      <div style={{ paddingTop: '4px' }}>
        <button
          type="button"
          onClick={onViewAll}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#60a5fa',
            fontSize: '0.72rem',
            fontWeight: 600,
            cursor: 'pointer',
            padding: 0,
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          <span>View full activity log</span>
          <ArrowRight size={12} />
        </button>
      </div>
    </div>
  );
};
