/**
 * AgentMetrics (Phase 6).
 * Agent runtime telemetry, active tasks, turn speed, and completion count.
 */

import React from 'react';
import { Bot, Clock, CheckCircle2 } from 'lucide-react';
import type { AgentsMonitoringResponse } from '@windagent/api-contracts';
import { Card } from '@windagent/ui';

export interface AgentMetricsProps {
  agents?: AgentsMonitoringResponse;
}

export const AgentMetrics: React.FC<AgentMetricsProps> = ({ agents }) => {
  const list = agents?.agents ?? [];

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
      data-testid="monitoring-agent-metrics"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
        <Bot size={18} color="#4edea3" />
        <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#f8fafc' }}>
          Hiệu Suất Thực Thi Của Agent Swarm
        </h3>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {list.map((a) => (
          <div
            key={a.agent_id}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '12px 16px',
              background: 'rgba(255,255,255,0.02)',
              borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.04)',
            }}
          >
            <div>
              <div style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc' }}>{a.name}</div>
              <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                Vai trò: {a.role} {a.current_task ? `• Đang làm: ${a.current_task}` : ''}
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '12px', color: '#94a3b8' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#4edea3' }}>
                <CheckCircle2 size={13} />
                {a.tasks_completed} tác vụ
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#c0c1ff' }}>
                <Clock size={13} />
                {a.avg_turn_ms} ms/turn
              </span>
              <span
                style={{
                  fontSize: '11px',
                  padding: '2px 8px',
                  borderRadius: '10px',
                  background: a.status === 'running' ? 'rgba(78,222,163,0.15)' : 'rgba(255,255,255,0.08)',
                  color: a.status === 'running' ? '#4edea3' : '#94a3b8',
                }}
              >
                {a.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
