/**
 * RecentActivityFeed (Phase 6).
 * Realtime studio event and activity log feed.
 */

import React from 'react';
import { History, CheckCircle2, Clapperboard, Sparkles } from 'lucide-react';
import type { DashboardSummary } from '@windagent/api-contracts';
import { Card } from '@windagent/ui';

export interface RecentActivityFeedProps {
  summary?: DashboardSummary;
}

export const RecentActivityFeed: React.FC<RecentActivityFeedProps> = ({ summary }) => {
  const activities = summary?.recent_activities ?? [];

  const getIconForType = (type: string) => {
    if (type.includes('screenplay')) return <Clapperboard size={15} color="#4d8eff" />;
    if (type.includes('storyboard')) return <Sparkles size={15} color="#f59e0b" />;
    return <CheckCircle2 size={15} color="#4edea3" />;
  };

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
      data-testid="recent-activity-feed"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
        <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(77, 142, 255, 0.15)', color: '#4d8eff' }}>
          <History size={18} />
        </div>
        <div>
          <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#f8fafc' }}>
            Nhật Ký Hoạt Động Gần Đây
          </h3>
          <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#94a3b8' }}>
            Các sự kiện hoàn tất mới nhất từ Swarm & Pipeline
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {activities.length === 0 ? (
          <div style={{ padding: '24px 16px', textAlign: 'center', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px dashed rgba(255,255,255,0.08)' }}>
            <div style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '4px' }}>Chưa có hoạt động gần đây</div>
            <div style={{ fontSize: '11px', color: '#64748b' }}>Các sự kiện từ Swarm & Pipeline sẽ hiển thị tại đây</div>
          </div>
        ) : (
          activities.map((act) => (
            <div
              key={act.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '12px 14px',
                background: 'rgba(255, 255, 255, 0.02)',
                borderRadius: '8px',
                border: '1px solid rgba(255, 255, 255, 0.04)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)' }}>
                  {getIconForType(act.type)}
                </div>
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 500, color: '#f8fafc' }}>{act.title}</div>
                  <div style={{ fontSize: '11px', color: '#64748b' }}>Loại: {act.type}</div>
                </div>
              </div>
              <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '10px', background: 'rgba(78, 222, 163, 0.15)', color: '#4edea3' }}>
                {act.status}
              </span>
            </div>
          ))
        )}
      </div>
    </Card>
  );
};
