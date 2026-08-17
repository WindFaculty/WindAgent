/**
 * DashboardPage (Phase 6).
 * Authoritative production dashboard surface wired to React Query and WebSocket telemetry.
 * Zero synthetic data.
 */

import React, { useState } from 'react';
import { Sparkles, RefreshCw, PlusCircle, Activity } from 'lucide-react';
import { Button } from '@windagent/ui';
import { useRouter } from '../../../app/router';
import { useDashboardSummary } from '../hooks/useDashboardSummary';
import { useSystemMetrics } from '../hooks/useSystemMetrics';
import { StudioSummaryCards } from '../components/StudioSummaryCards';
import { SystemResourceCards } from '../components/SystemResourceCards';
import { StudioActivityChart } from '../components/StudioActivityChart';
import { ModelUsagePanel } from '../components/ModelUsagePanel';
import { AgentSwarmSummary } from '../components/AgentSwarmSummary';
import { RecentActivityFeed } from '../components/RecentActivityFeed';
import { StorageSummary } from '../components/StorageSummary';

export const DashboardPage: React.FC = () => {
  const { navigate } = useRouter();
  const { summary, isLoading: summaryLoading, isFetching: summaryFetching, refetch: refetchSummary, invalidate } = useDashboardSummary();
  const { metrics, history, isRealtime, isLoading: metricsLoading, refetch: refetchMetrics } = useSystemMetrics();
  const [isManualRefreshing, setIsManualRefreshing] = useState(false);

  const handleRefresh = async () => {
    setIsManualRefreshing(true);
    invalidate();
    await Promise.all([refetchSummary(), refetchMetrics()]);
    setIsManualRefreshing(false);
  };

  const isLoading = summaryLoading || metricsLoading;
  const isRefreshing = summaryFetching || isManualRefreshing;

  return (
    <div
      style={{
        padding: '24px 32px',
        maxWidth: '1600px',
        margin: '0 auto',
        fontFamily: 'var(--font-sans, system-ui, sans-serif)',
        color: '#f8fafc',
      }}
      data-testid="dashboard-page"
    >
      {/* 1. Header */}
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: '28px',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '6px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #4d8eff, #60a5fa)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
              }}
            >
              <Sparkles size={20} />
            </div>
            <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 700, letterSpacing: '-0.5px' }}>
              Bảng Điều Khiển Studio
            </h1>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '20px',
                background: isRealtime ? 'rgba(78, 222, 163, 0.15)' : 'rgba(77, 142, 255, 0.15)',
                color: isRealtime ? '#4edea3' : '#60a5fa',
                fontSize: '12px',
                fontWeight: 600,
                border: `1px solid ${isRealtime ? 'rgba(78, 222, 163, 0.3)' : 'rgba(77, 142, 255, 0.3)'}`,
              }}
            >
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  background: 'currentColor',
                }}
              />
              <span>{isRealtime ? 'Live Swarm & WebSocket' : 'Active Workspace'}</span>
            </div>
          </div>
          <p style={{ margin: 0, fontSize: '14px', color: '#94a3b8' }}>
            Trung tâm giám sát tài nguyên phần cứng, điều phối Multi-Agent swarm và phân tích tác phẩm điện ảnh.
          </p>
        </div>

        {/* Header Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/monitoring')}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
          >
            <Activity size={15} />
            <span>Monitoring Chi Tiết</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isRefreshing}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
            title="Làm mới toàn bộ thông số"
          >
            <RefreshCw size={15} className={isRefreshing ? 'animate-spin' : ''} />
            <span>Làm Mới</span>
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate('/studio/projects')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '13px',
              background: 'linear-gradient(135deg, #4d8eff, #3b82f6)',
              boxShadow: '0 4px 12px rgba(77, 142, 255, 0.3)',
            }}
          >
            <PlusCircle size={15} />
            <span>Tạo Kịch Bản Mới</span>
          </Button>
        </div>
      </header>

      {/* 2. Top Metric KPI Deck */}
      <StudioSummaryCards summary={summary} metrics={metrics} isLoading={isLoading} />

      {/* 3. Main Content Grid (2 Columns) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)',
          gap: '24px',
        }}
      >
        {/* Left Column: Visual Analytics & Model Distribution */}
        <div>
          <StudioActivityChart summary={summary} />
          <ModelUsagePanel summary={summary} />
          <RecentActivityFeed summary={summary} />
        </div>

        {/* Right Column: Real Telemetry & Swarm Summary */}
        <div>
          <SystemResourceCards metrics={metrics} history={history} isRealtime={isRealtime} />
          <AgentSwarmSummary summary={summary} />
          <StorageSummary summary={summary} />
        </div>
      </div>
    </div>
  );
};
