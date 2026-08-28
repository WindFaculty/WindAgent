/**
 * AgentSwarmSummary (Phase 6).
 * Shows agent swarm topology and active role allocation.
 */

import React from 'react';
import { Bot, ArrowRight, CheckCircle2 } from 'lucide-react';
import type { DashboardSummary } from '@windagent/api-contracts';
import { Card, Button } from '@windagent/ui';
import { useRouter } from '../../../app/router';

export interface AgentSwarmSummaryProps {
  summary?: DashboardSummary;
}

export const AgentSwarmSummary: React.FC<AgentSwarmSummaryProps> = ({ summary }) => {
  const { navigate } = useRouter();
  const agents = summary?.agents;

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
      data-testid="agent-swarm-summary"
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(78, 222, 163, 0.15)', color: '#4edea3' }}>
            <Bot size={18} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#f8fafc' }}>
              Multi-Agent Orchestration Swarm
            </h3>
            <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#94a3b8' }}>
              Điều phối Agent tự động theo vai trò sáng tác
            </p>
          </div>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate('/workspace')}
          style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}
        >
          <span>Mở Workspace</span>
          <ArrowRight size={14} />
        </Button>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
        {agents?.active_roles && agents.active_roles.length > 0 ? (
          agents.active_roles.map((role) => (
            <div
              key={role}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 14px',
                background: 'rgba(78, 222, 163, 0.08)',
                border: '1px solid rgba(78, 222, 163, 0.2)',
                borderRadius: '20px',
                fontSize: '13px',
                color: '#f8fafc',
              }}
            >
              <CheckCircle2 size={14} color="#4edea3" />
              <span>{role}</span>
            </div>
          ))
        ) : (
          <div style={{ padding: '16px', textAlign: 'center', width: '100%', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px dashed rgba(255,255,255,0.08)', fontSize: '13px', color: '#64748b' }}>
            Chưa có agent hoạt động — khởi tạo agent trong Workspace
          </div>
        )}
      </div>
    </Card>
  );
};
