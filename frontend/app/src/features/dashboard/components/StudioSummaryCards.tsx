/**
 * StudioSummaryCards (Phase 6).
 * Top KPI deck backed by real summary and telemetry data.
 */

import React from 'react';
import { Film, Bot, Activity, Cpu, Zap, TrendingUp, CheckCircle2 } from 'lucide-react';
import type { DashboardSummary, SystemMetrics } from '@windagent/api-contracts';
import { Card } from '@windagent/ui';
import { useRouter } from '../../../app/router';

export interface StudioSummaryCardsProps {
  summary?: DashboardSummary;
  metrics?: SystemMetrics | null;
  isLoading?: boolean;
}

export const StudioSummaryCards: React.FC<StudioSummaryCardsProps> = ({
  summary,
  metrics,
  isLoading,
}) => {
  const { navigate } = useRouter();

  const totalProjects = summary?.projects.total ?? 0;
  const activeEpisodes = summary?.episodes.active ?? 0;
  const totalEpisodes = summary?.episodes.total ?? 0;

  const totalAgents = summary?.agents.total ?? 0;
  const runningAgents = summary?.agents.running ?? 0;
  const agentPercent = totalAgents > 0 ? Math.round((runningAgents / totalAgents) * 100) : 0;
  const activeRolesText = summary?.agents.active_roles.length
    ? summary.agents.active_roles.slice(0, 3).join(', ')
    : 'No active roles';

  const ramPercent = metrics ? Math.round(metrics.memory.usage_percent) : 0;
  const ramGb = metrics ? (metrics.memory.used_bytes / (1024 * 1024 * 1024)).toFixed(1) : '0.0';
  const ramTotalGb = metrics ? (metrics.memory.total_bytes / (1024 * 1024 * 1024)).toFixed(0) : '0';
  const cpuPercent = metrics ? Math.round(metrics.cpu.usage_percent) : 0;

  const hasGpu = metrics && metrics.gpu_supported && metrics.gpu.length > 0;
  const primaryGpu = hasGpu ? metrics.gpu[0] : null;
  const gpuPercent = primaryGpu ? Math.round(primaryGpu.utilization_percent) : 0;
  const gpuName = primaryGpu ? primaryGpu.name : 'Host CPU Architecture';

  return (
    <section
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
        gap: '16px',
        marginBottom: '24px',
      }}
      data-testid="studio-summary-cards"
    >
      {/* 1. Projects & Episodes Card */}
      <Card
        elevation="flat"
        interactive
        onClick={() => navigate('/studio/projects')}
        style={{
          padding: '20px',
          background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8))',
          border: '1px solid rgba(77, 142, 255, 0.2)',
          borderRadius: '12px',
          cursor: 'pointer',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Dự Án & Tập Phim
          </span>
          <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(77, 142, 255, 0.15)', color: '#4d8eff' }}>
            <Film size={18} />
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '12px' }}>
          <span style={{ fontSize: '28px', fontWeight: 700, color: '#f8fafc' }}>
            {isLoading ? '...' : totalProjects}
          </span>
          <span style={{ fontSize: '14px', color: '#94a3b8' }}>
            {isLoading ? '' : `${activeEpisodes}/${totalEpisodes} Tập Active`}
          </span>
        </div>
        <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden', marginBottom: '12px' }}>
          <div
            style={{
              width: `${totalEpisodes > 0 ? Math.min(100, Math.round((activeEpisodes / totalEpisodes) * 100)) : 0}%`,
              height: '100%',
              background: 'linear-gradient(90deg, #4d8eff, #60a5fa)',
              borderRadius: '3px',
              transition: 'width 0.5s ease',
            }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#38bdf8' }}>
          <TrendingUp size={14} />
          <span>{summary?.projects.recent_created_count ?? 0} dự án mới 7 ngày qua</span>
        </div>
      </Card>

      {/* 2. Agent Swarm Card */}
      <Card
        elevation="flat"
        interactive
        onClick={() => navigate('/workspace')}
        style={{
          padding: '20px',
          background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8))',
          border: '1px solid rgba(78, 222, 163, 0.2)',
          borderRadius: '12px',
          cursor: 'pointer',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Agent Swarm
          </span>
          <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(78, 222, 163, 0.15)', color: '#4edea3' }}>
            <Bot size={18} />
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '12px' }}>
          <span style={{ fontSize: '28px', fontWeight: 700, color: '#f8fafc' }}>
            {isLoading ? '...' : `${runningAgents} / ${totalAgents}`}
          </span>
          <span style={{ fontSize: '14px', color: '#94a3b8' }}>
            {isLoading ? '' : `${agentPercent}% Hoạt Động`}
          </span>
        </div>
        <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden', marginBottom: '12px' }}>
          <div
            style={{
              width: `${agentPercent}%`,
              height: '100%',
              background: 'linear-gradient(90deg, #4edea3, #22c55e)',
              borderRadius: '3px',
              transition: 'width 0.5s ease',
            }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#4edea3', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          <CheckCircle2 size={14} style={{ flexShrink: 0 }} />
          <span title={activeRolesText}>{activeRolesText}</span>
        </div>
      </Card>

      {/* 3. Memory & CPU Card */}
      <Card
        elevation="flat"
        interactive
        onClick={() => navigate('/monitoring')}
        style={{
          padding: '20px',
          background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8))',
          border: '1px solid rgba(192, 193, 255, 0.2)',
          borderRadius: '12px',
          cursor: 'pointer',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Bộ Nhớ RAM
          </span>
          <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(192, 193, 255, 0.15)', color: '#c0c1ff' }}>
            <Activity size={18} />
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '12px' }}>
          <span style={{ fontSize: '28px', fontWeight: 700, color: '#f8fafc' }}>
            {ramPercent}%
          </span>
          <span style={{ fontSize: '14px', color: '#94a3b8' }}>
            {ramGb} / {ramTotalGb} GB
          </span>
        </div>
        <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden', marginBottom: '12px' }}>
          <div
            style={{
              width: `${ramPercent}%`,
              height: '100%',
              background: 'linear-gradient(90deg, #c0c1ff, #8083ff)',
              borderRadius: '3px',
              transition: 'width 0.5s ease',
            }}
          />
        </div>
        <div style={{ fontSize: '12px', color: '#cbd5e1' }}>
          CPU Load: <strong style={{ color: '#fff' }}>{cpuPercent}%</strong> ({metrics?.cpu.cores_count ?? 1} Cores)
        </div>
      </Card>

      {/* 4. GPU & Inference Acceleration Card */}
      <Card
        elevation="flat"
        interactive
        onClick={() => navigate('/monitoring')}
        style={{
          padding: '20px',
          background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8))',
          border: '1px solid rgba(245, 158, 11, 0.2)',
          borderRadius: '12px',
          cursor: 'pointer',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Tăng Tốc Phần Cứng
          </span>
          <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' }}>
            <Cpu size={18} />
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '12px' }}>
          <span style={{ fontSize: '28px', fontWeight: 700, color: '#f8fafc' }}>
            {hasGpu ? `${gpuPercent}%` : 'Standard'}
          </span>
          <span style={{ fontSize: '14px', color: '#94a3b8' }}>
            {hasGpu ? 'GPU Active' : 'CPU Threading'}
          </span>
        </div>
        <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden', marginBottom: '12px' }}>
          <div
            style={{
              width: `${hasGpu ? gpuPercent : 100}%`,
              height: '100%',
              background: hasGpu ? 'linear-gradient(90deg, #f59e0b, #fbbf24)' : '#64748b',
              borderRadius: '3px',
              transition: 'width 0.5s ease',
            }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#f59e0b' }}>
          <Zap size={14} style={{ flexShrink: 0 }} />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{gpuName}</span>
        </div>
      </Card>
    </section>
  );
};
