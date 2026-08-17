/**
 * MonitoringPage (Phase 6).
 * In-depth operational observability surface for infrastructure, workers, and inference.
 */

import React from 'react';
import { Activity, RefreshCw, ArrowLeft } from 'lucide-react';
import { Button } from '@windagent/ui';
import { useRouter } from '../../../app/router';
import { useSystemMetrics } from '../../dashboard/hooks/useSystemMetrics';
import { useMonitoring } from '../hooks/useMonitoring';
import { ResourceMetrics } from '../components/ResourceMetrics';
import { WorkerStatus } from '../components/WorkerStatus';
import { QueueMetrics } from '../components/QueueMetrics';
import { ProviderHealth } from '../components/ProviderHealth';
import { AgentMetrics } from '../components/AgentMetrics';
import { RuntimeMetrics } from '../components/RuntimeMetrics';

export const MonitoringPage: React.FC = () => {
  const { navigate } = useRouter();
  const { metrics, refetch: refetchSystemMetrics } = useSystemMetrics();
  const { workers, providers, agents, queues, runs, isLoading, refetchAll } = useMonitoring();

  const handleRefresh = async () => {
    await Promise.all([refetchSystemMetrics(), refetchAll()]);
  };

  return (
    <div
      style={{
        padding: '24px 32px',
        maxWidth: '1600px',
        margin: '0 auto',
        fontFamily: 'var(--font-sans, system-ui, sans-serif)',
        color: '#f8fafc',
      }}
      data-testid="monitoring-page"
    >
      {/* Header */}
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
              <Activity size={20} />
            </div>
            <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 700, letterSpacing: '-0.5px' }}>
              Giám Sát Hệ Thống & Hạ Tầng
            </h1>
          </div>
          <p style={{ margin: 0, fontSize: '14px', color: '#94a3b8' }}>
            Chi tiết vận hành tài nguyên máy chủ, background workers, độ trễ provider và throughput hàng đợi.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/dashboard')}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
          >
            <ArrowLeft size={15} />
            <span>Quay lại Dashboard</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isLoading}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
          >
            <RefreshCw size={15} className={isLoading ? 'animate-spin' : ''} />
            <span>Làm Mới</span>
          </Button>
        </div>
      </header>

      {/* Main Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1fr)', gap: '24px' }}>
        <div>
          <ResourceMetrics metrics={metrics} />
          <WorkerStatus workers={workers} />
          <QueueMetrics queues={queues} />
        </div>

        <div>
          <ProviderHealth providers={providers} />
          <AgentMetrics agents={agents} />
          <RuntimeMetrics metrics={metrics} runs={runs} />
        </div>
      </div>
    </div>
  );
};
