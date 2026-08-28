/**
 * ModelUsagePanel (Phase 6).
 * Visualizes real LLM and inference model distribution, speeds, and latency telemetry.
 */

import React from 'react';
import { Cpu, Zap, Clock } from 'lucide-react';
import type { DashboardSummary } from '@windagent/api-contracts';
import { Card } from '@windagent/ui';

export interface ModelUsagePanelProps {
  summary?: DashboardSummary;
}

const MODEL_COLORS = ['#4d8eff', '#c0c1ff', '#4edea3', '#f59e0b', '#ec4899'];

export const ModelUsagePanel: React.FC<ModelUsagePanelProps> = ({ summary }) => {
  const models = summary?.model_usage ?? [];

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
      data-testid="model-usage-panel"
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(192, 193, 255, 0.15)', color: '#c0c1ff' }}>
            <Cpu size={18} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#f8fafc' }}>
              Phân Phối Model & Hiệu Suất Suy Luận
            </h3>
            <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#94a3b8' }}>
              Tỷ trọng sử dụng, tốc độ sinh token và độ trễ phản hồi
            </p>
          </div>
        </div>
      </div>

      {models.length === 0 ? (
        <div style={{ padding: '32px 16px', textAlign: 'center', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px dashed rgba(255,255,255,0.08)' }}>
          <div style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '4px' }}>Chưa có dữ liệu model</div>
          <div style={{ fontSize: '11px', color: '#64748b' }}>Cấu hình provider & model trong Settings để thấy phân phối sử dụng</div>
        </div>
      ) : (
        <>
          {/* Multi-segment progress bar */}
          <div style={{ width: '100%', height: '10px', background: 'rgba(255,255,255,0.06)', borderRadius: '5px', overflow: 'hidden', display: 'flex', marginBottom: '20px' }}>
            {models.map((m, idx) => (
              <div
                key={m.model_id}
                title={`${m.name}: ${m.usage_percent}%`}
                style={{
                  width: `${m.usage_percent}%`,
                  height: '100%',
                  background: MODEL_COLORS[idx % MODEL_COLORS.length],
                  transition: 'width 0.4s ease',
                }}
              />
            ))}
          </div>

          {/* Model Cards List */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
            {models.map((m, idx) => {
              const color = MODEL_COLORS[idx % MODEL_COLORS.length];
              return (
                <div
                  key={m.model_id}
                  style={{
                    padding: '14px',
                    background: 'rgba(255,255,255,0.02)',
                    borderRadius: '8px',
                    border: '1px solid rgba(255,255,255,0.05)',
                    borderLeft: `4px solid ${color}`,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                    <div>
                      <div style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc' }}>{m.name}</div>
                      <div style={{ fontSize: '11px', color: '#94a3b8' }}>{m.provider}</div>
                    </div>
                    <span style={{ fontSize: '14px', fontWeight: 700, color }}>{m.usage_percent}%</span>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: '#64748b', marginTop: '10px', paddingTop: '8px', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#38bdf8' }}>
                      <Zap size={12} />
                      {m.tokens_per_second} tok/s
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#a78bfa' }}>
                      <Clock size={12} />
                      {m.latency_ms} ms
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </Card>
  );
};
