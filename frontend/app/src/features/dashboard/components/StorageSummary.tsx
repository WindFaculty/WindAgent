/**
 * StorageSummary (Phase 6).
 * Shows workspace asset disk usage and capacity breakdown.
 */

import React from 'react';
import { Database, HardDrive, Layers } from 'lucide-react';
import type { DashboardSummary } from '@windagent/api-contracts';
import { Card } from '@windagent/ui';

export interface StorageSummaryProps {
  summary?: DashboardSummary;
}

export const StorageSummary: React.FC<StorageSummaryProps> = ({ summary }) => {
  const storage = summary?.storage;
  const usedMb = storage ? (storage.workspace_used_bytes / (1024 * 1024)).toFixed(1) : '0';
  const totalGb = storage ? (storage.workspace_total_bytes / (1024 * 1024 * 1024)).toFixed(0) : '0';
  const usedPercent =
    storage && storage.workspace_total_bytes > 0
      ? ((storage.workspace_used_bytes / storage.workspace_total_bytes) * 100).toFixed(1)
      : '0.5';

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
      data-testid="storage-summary"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
        <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' }}>
          <Database size={18} />
        </div>
        <div>
          <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#f8fafc' }}>
            Dung Lượng Workspace & Assets
          </h3>
          <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#94a3b8' }}>
            Tổng hợp dữ liệu lưu trữ kịch bản, âm thanh và keyframes
          </p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
        <div style={{ padding: '14px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>
            <HardDrive size={14} color="#f59e0b" />
            <span>Đã Dùng</span>
          </div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>{usedMb} MB</div>
          <div style={{ fontSize: '11px', color: '#64748b' }}>Trên {totalGb} GB hạn mức ({usedPercent}%)</div>
        </div>

        <div style={{ padding: '14px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>
            <Layers size={14} color="#4d8eff" />
            <span>Tổng Assets</span>
          </div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>{storage?.assets_count ?? 0} Items</div>
          <div style={{ fontSize: '11px', color: '#64748b' }}>Characters, Prompts, Media</div>
        </div>
      </div>
    </Card>
  );
};
