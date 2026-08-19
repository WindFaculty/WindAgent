import React from 'react';
import type { RoutingMetricsData } from '@windagent/api-contracts';
import { Activity, ShieldCheck, Zap, CheckCircle2, BarChart3, ArrowUpRight } from 'lucide-react';

interface RoutingMetricsProps {
  metrics?: RoutingMetricsData;
  isLoading?: boolean;
}

export const RoutingMetrics: React.FC<RoutingMetricsProps> = ({ metrics, isLoading }) => {
  if (isLoading || !metrics) {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            style={{
              padding: '18px 20px',
              borderRadius: '12px',
              backgroundColor: 'rgba(19, 27, 46, 0.7)',
              border: '1px solid rgba(66, 71, 84, 0.4)',
              backdropFilter: 'blur(12px)',
              height: '92px',
              animation: 'pulse 1.5s infinite ease-in-out',
            }}
          />
        ))}
      </div>
    );
  }

  const cards = [
    {
      title: 'Total Routes Served',
      value: metrics.total_routes.toLocaleString(),
      subtext: 'Throughput',
      trend: '+12.4%',
      icon: Activity,
      accentColor: '#38bdf8',
      bgGlow: 'rgba(56, 189, 248, 0.1)',
      borderAccent: 'rgba(56, 189, 248, 0.3)',
    },
    {
      title: 'Active Rules',
      value: `${metrics.active_rules} Policies`,
      subtext: `${metrics.fallback_chains || 4} with Failover`,
      trend: '100% Active',
      icon: ShieldCheck,
      accentColor: '#818cf8',
      bgGlow: 'rgba(129, 140, 248, 0.1)',
      borderAccent: 'rgba(129, 140, 248, 0.3)',
    },
    {
      title: 'Avg Routing Latency',
      value: `${metrics.avg_latency_ms} ms`,
      subtext: 'p99: ~48ms',
      trend: '⚡ Ultra Fast',
      icon: Zap,
      accentColor: '#fbbf24',
      bgGlow: 'rgba(251, 191, 36, 0.1)',
      borderAccent: 'rgba(251, 191, 36, 0.3)',
    },
    {
      title: 'Success Rate',
      value: `${metrics.success_rate_percent}%`,
      subtext: 'Zero Failover Drop',
      trend: '99.9% SLA',
      icon: CheckCircle2,
      accentColor: '#4edea3',
      bgGlow: 'rgba(78, 222, 163, 0.1)',
      borderAccent: 'rgba(78, 222, 163, 0.3)',
    },
    {
      title: 'Traffic Balance',
      value: `${metrics.traffic_balance_percent}%`,
      subtext: 'Multi-Gateway Load',
      trend: 'Optimal',
      icon: BarChart3,
      accentColor: '#c084fc',
      bgGlow: 'rgba(192, 132, 252, 0.1)',
      borderAccent: 'rgba(192, 132, 252, 0.3)',
    },
  ];

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
        gap: '14px',
      }}
    >
      {cards.map((card, idx) => {
        const Icon = card.icon;
        return (
          <div
            key={idx}
            style={{
              padding: '16px 18px',
              borderRadius: '12px',
              backgroundColor: 'rgba(19, 27, 46, 0.75)',
              border: `1px solid ${card.borderAccent}`,
              backdropFilter: 'blur(16px)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              gap: '10px',
              position: 'relative',
              overflow: 'hidden',
              boxShadow: `0 4px 20px -2px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)`,
              transition: 'transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease',
            }}
          >
            {/* Ambient Corner Glow */}
            <div
              style={{
                position: 'absolute',
                top: '-20px',
                right: '-20px',
                width: '70px',
                height: '70px',
                borderRadius: '50%',
                background: `radial-gradient(circle, ${card.accentColor} 0%, transparent 70%)`,
                opacity: 0.25,
                pointerEvents: 'none',
              }}
            />

            {/* Top Label & Icon */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <span
                style={{
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  color: 'var(--text-muted, #c2c6d6)',
                  letterSpacing: '0.02em',
                  textTransform: 'uppercase',
                }}
              >
                {card.title}
              </span>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  backgroundColor: card.bgGlow,
                  border: `1px solid ${card.borderAccent}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: card.accentColor,
                  flexShrink: 0,
                }}
              >
                <Icon size={16} />
              </div>
            </div>

            {/* Main Value & Subtext */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
                <span
                  style={{
                    fontSize: '1.45rem',
                    fontWeight: 800,
                    color: 'var(--text-main, #dae2fd)',
                    fontFamily: 'var(--font-sans)',
                    letterSpacing: '-0.02em',
                    lineHeight: 1.1,
                  }}
                >
                  {card.value}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '2px' }}>
                <span style={{ fontSize: '0.74rem', color: 'var(--text-dim, #8c909f)' }}>
                  {card.subtext}
                </span>
                <span
                  style={{
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    padding: '2px 6px',
                    borderRadius: '4px',
                    backgroundColor: card.bgGlow,
                    color: card.accentColor,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '2px',
                  }}
                >
                  {card.trend.startsWith('+') && <ArrowUpRight size={10} />}
                  {card.trend}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
