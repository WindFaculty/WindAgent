/**
 * ResourceMetrics (Phase 6).
 * Detailed CPU, RAM, Disk, and GPU hardware telemetry.
 */

import React from 'react';
import { Cpu, Server, HardDrive, Zap } from 'lucide-react';
import type { SystemMetrics } from '@windagent/api-contracts';
import { Card } from '@windagent/ui';

export interface ResourceMetricsProps {
  metrics?: SystemMetrics | null;
}

export const ResourceMetrics: React.FC<ResourceMetricsProps> = ({ metrics }) => {
  const cpuPercent = metrics ? Math.round(metrics.cpu.usage_percent) : 0;
  const ramPercent = metrics ? Math.round(metrics.memory.usage_percent) : 0;
  const diskPercent = metrics ? Math.round(metrics.disk.usage_percent) : 0;
  const gpu = metrics && metrics.gpu.length > 0 ? metrics.gpu[0] : null;

  return (
    <Card
      elevation="raised"
      style={{
        padding: '24px',
        background: 'linear-gradient(135deg, rgba(23, 31, 51, 0.9), rgba(15, 23, 42, 0.95))',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '12px',
        marginBottom: '24px',
      }}
      data-testid="monitoring-resource-metrics"
    >
      <h3 style={{ margin: '0 0 16px', fontSize: '16px', fontWeight: 600, color: '#f8fafc' }}>
        Tài Nguyên Phần Cứng Chi Tiết
      </h3>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
        {/* CPU */}
        <div style={{ padding: '16px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#4d8eff', marginBottom: '8px' }}>
            <Cpu size={16} />
            <span style={{ fontSize: '13px', fontWeight: 600 }}>CPU Processor</span>
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700, color: '#f8fafc', marginBottom: '6px' }}>{cpuPercent}%</div>
          <div style={{ fontSize: '12px', color: '#94a3b8' }}>
            {metrics?.cpu.cores_count ?? 1} Cores {metrics?.cpu.frequency_mhz ? `• ${Math.round(metrics.cpu.frequency_mhz)} MHz` : ''}
          </div>
        </div>

        {/* RAM */}
        <div style={{ padding: '16px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#c0c1ff', marginBottom: '8px' }}>
            <Server size={16} />
            <span style={{ fontSize: '13px', fontWeight: 600 }}>Physical RAM</span>
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700, color: '#f8fafc', marginBottom: '6px' }}>{ramPercent}%</div>
          <div style={{ fontSize: '12px', color: '#94a3b8' }}>
            {metrics ? (metrics.memory.used_bytes / (1024 ** 3)).toFixed(1) : 0} / {metrics ? (metrics.memory.total_bytes / (1024 ** 3)).toFixed(0) : 0} GB
          </div>
        </div>

        {/* Disk */}
        <div style={{ padding: '16px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#4edea3', marginBottom: '8px' }}>
            <HardDrive size={16} />
            <span style={{ fontSize: '13px', fontWeight: 600 }}>Host Storage</span>
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700, color: '#f8fafc', marginBottom: '6px' }}>{diskPercent}%</div>
          <div style={{ fontSize: '12px', color: '#94a3b8' }}>
            {metrics ? (metrics.disk.free_bytes / (1024 ** 3)).toFixed(0) : 0} GB Khả Dụng
          </div>
        </div>

        {/* GPU */}
        <div style={{ padding: '16px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#f59e0b', marginBottom: '8px' }}>
            <Zap size={16} />
            <span style={{ fontSize: '13px', fontWeight: 600 }}>GPU / Accelerator</span>
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700, color: '#f8fafc', marginBottom: '6px' }}>
            {gpu ? `${Math.round(gpu.utilization_percent)}%` : 'N/A'}
          </div>
          <div style={{ fontSize: '12px', color: '#94a3b8' }}>
            {gpu ? gpu.name : 'Chạy qua CPU Threading'}
          </div>
        </div>
      </div>
    </Card>
  );
};
