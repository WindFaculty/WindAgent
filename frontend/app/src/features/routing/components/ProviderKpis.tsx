import React from 'react';
import { Link2, Box, ShieldCheck, Clock, Zap } from 'lucide-react';

export interface ProviderKpiStats {
  connectedProviders: number;
  totalProviders: number;
  activeModels: number;
  healthyEndpoints: number;
  lastSyncTime: string;
  lastSyncFormatted: string;
  avgResponseTimeMs: number;
}

interface ProviderKpisProps {
  stats: ProviderKpiStats;
}

export const ProviderKpis: React.FC<ProviderKpisProps> = ({ stats }) => {
  const percentOnline = Math.round((stats.connectedProviders / (stats.totalProviders || 1)) * 100);
  const percentHealthy = Math.round((stats.healthyEndpoints / (stats.totalProviders || 1)) * 100);

  const kpis = [
    {
      label: 'Connected Providers',
      value: `${stats.connectedProviders} / ${stats.totalProviders}`,
      subtext: `${percentOnline}% online`,
      icon: <Link2 size={20} color="#60a5fa" />,
      iconBg: 'rgba(59, 130, 246, 0.15)',
      iconBorder: 'rgba(59, 130, 246, 0.3)',
    },
    {
      label: 'Active Models',
      value: stats.activeModels.toString(),
      subtext: 'Across all providers',
      icon: <Box size={20} color="#c084fc" />,
      iconBg: 'rgba(168, 85, 247, 0.15)',
      iconBorder: 'rgba(168, 85, 247, 0.3)',
    },
    {
      label: 'Healthy Endpoints',
      value: stats.healthyEndpoints.toString(),
      subtext: `${percentHealthy}% healthy`,
      icon: <ShieldCheck size={20} color="#34d399" />,
      iconBg: 'rgba(16, 185, 129, 0.15)',
      iconBorder: 'rgba(16, 185, 129, 0.3)',
    },
    {
      label: 'Last Sync',
      value: stats.lastSyncTime,
      subtext: stats.lastSyncFormatted,
      icon: <Clock size={20} color="#22d3ee" />,
      iconBg: 'rgba(6, 182, 212, 0.15)',
      iconBorder: 'rgba(6, 182, 212, 0.3)',
    },
    {
      label: 'Avg Response Time',
      value: `${stats.avgResponseTimeMs} ms`,
      subtext: 'Across healthy endpoints',
      icon: <Zap size={20} color="#a78bfa" />,
      iconBg: 'rgba(139, 92, 246, 0.15)',
      iconBorder: 'rgba(139, 92, 246, 0.3)',
    },
  ];

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: '14px',
        width: '100%',
      }}
    >
      {kpis.map((kpi, index) => (
        <div
          key={index}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            padding: '14px 18px',
            borderRadius: '12px',
            backgroundColor: 'rgba(17, 24, 39, 0.75)',
            border: '1px solid rgba(66, 71, 84, 0.4)',
            backdropFilter: 'blur(12px)',
            transition: 'transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'rgba(77, 142, 255, 0.4)';
            e.currentTarget.style.transform = 'translateY(-2px)';
            e.currentTarget.style.boxShadow = '0 6px 18px rgba(0, 0, 0, 0.35)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'rgba(66, 71, 84, 0.4)';
            e.currentTarget.style.transform = 'translateY(0)';
            e.currentTarget.style.boxShadow = 'none';
          }}
        >
          {/* Circular Icon */}
          <div
            style={{
              width: '42px',
              height: '42px',
              borderRadius: '50%',
              backgroundColor: kpi.iconBg,
              border: `1px solid ${kpi.iconBorder}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            {kpi.icon}
          </div>

          {/* Text Information */}
          <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            <span
              style={{
                fontSize: '0.74rem',
                color: 'var(--text-muted, #94a3b8)',
                fontWeight: 500,
                letterSpacing: '0.01em',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {kpi.label}
            </span>
            <span
              style={{
                fontSize: '1.25rem',
                fontWeight: 700,
                color: 'var(--text-main, #f8fafc)',
                letterSpacing: '-0.02em',
                lineHeight: 1.2,
                marginTop: '2px',
              }}
            >
              {kpi.value}
            </span>
            <span
              style={{
                fontSize: '0.70rem',
                color: 'var(--text-dim, #64748b)',
                marginTop: '2px',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {kpi.subtext}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
};
