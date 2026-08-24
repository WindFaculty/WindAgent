/**
 * DirectorPanel — Phase E cutover (ban_ke_hoach_v1.md Section 11-12).
 *
 * Renders the Gemini Live director loop: connection state, current cue,
 * latest model turn and the gated last tool result. Values come from
 * `LiveDirectorSession`/client via the page — this component is display-only.
 */

import React from 'react';
import { Bot, CircleDot, Wrench } from 'lucide-react';
import type { LiveDirectorConnectionState } from '../live-director/types';

const STATE_COLORS: Record<LiveDirectorConnectionState, { dot: string; label: string }> = {
  DISCONNECTED: { dot: '#64748b', label: 'Ngắt kết nối' },
  CONNECTING: { dot: '#eab308', label: 'Đang kết nối' },
  CONNECTED: { dot: '#22c55e', label: 'Gemini Live' },
  RESUMING: { dot: '#3b82f6', label: 'Đang resume' },
  DEGRADED: { dot: '#f97316', label: 'Suy giảm' },
};

export interface DirectorPanelProps {
  readonly connectionState?: LiveDirectorConnectionState;
  readonly currentSceneId?: string;
  readonly currentCueId?: string;
  readonly expectedStateId?: string;
  readonly latestModelTurn?: string | null;
  readonly lastToolResult?: unknown;
  readonly allowedTools?: readonly string[];
}

export const DirectorPanel: React.FC<DirectorPanelProps> = ({
  connectionState = 'DISCONNECTED',
  currentSceneId = '—',
  currentCueId = '—',
  expectedStateId,
  latestModelTurn,
  lastToolResult,
  allowedTools = [],
}) => {
  const colors = STATE_COLORS[connectionState] ?? STATE_COLORS.DISCONNECTED;

  return (
    <div
      style={{
        backgroundColor: 'rgba(15, 23, 42, 0.8)',
        border: '1px solid rgba(59, 130, 246, 0.25)',
        borderRadius: '14px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        minHeight: '220px',
      }}
      data-testid="director-panel"
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#93c5fd', fontWeight: 700, fontSize: '13px' }}>
          <Bot size={15} /> Gemini Live Director
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 10px',
            borderRadius: '9999px',
            border: `1px solid ${colors.dot}55`,
            fontSize: '11px',
            fontWeight: 700,
            color: colors.dot,
          }}
        >
          <CircleDot size={11} />
          {colors.label}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '12px' }}>
        <div>
          <div style={{ color: '#64748b', fontSize: '10px', textTransform: 'uppercase' }}>Scene</div>
          <div style={{ color: '#e2e8f0', fontWeight: 600 }}>{currentSceneId}</div>
        </div>
        <div>
          <div style={{ color: '#64748b', fontSize: '10px', textTransform: 'uppercase' }}>Cue hiện tại</div>
          <div style={{ color: '#e2e8f0', fontWeight: 600 }}>{currentCueId}</div>
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <div style={{ color: '#64748b', fontSize: '10px', textTransform: 'uppercase' }}>Trạng thái kỳ vọng</div>
          <div style={{ color: expectedStateId ? '#4ade80' : '#64748b', fontWeight: 600 }}>
            {expectedStateId ?? '(không ràng buộc)'}
          </div>
        </div>
      </div>

      <div style={{ flex: 1 }}>
        <div style={{ color: '#64748b', fontSize: '10px', textTransform: 'uppercase', marginBottom: '4px' }}>
          Model turn gần nhất
        </div>
        <div
          style={{
            backgroundColor: 'rgba(2, 6, 23, 0.6)',
            borderRadius: '8px',
            padding: '10px',
            minHeight: '52px',
            maxHeight: '96px',
            overflowY: 'auto',
            fontSize: '12px',
            lineHeight: 1.5,
            color: latestModelTurn ? '#cbd5e1' : '#475569',
            fontStyle: latestModelTurn ? 'normal' : 'italic',
          }}
        >
          {latestModelTurn || '— chờ quan sát đầu tiên từ Gemini —'}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
        <Wrench size={11} color="#64748b" />
        {(allowedTools.length > 0 ? allowedTools : ['(chưa nạp plan)']).map((tool) => (
          <span
            key={tool}
            style={{
              padding: '2px 8px',
              borderRadius: '9999px',
              backgroundColor: 'rgba(59, 130, 246, 0.12)',
              border: '1px solid rgba(59, 130, 246, 0.3)',
              color: '#93c5fd',
              fontSize: '10px',
              fontFamily: 'monospace',
            }}
          >
            {tool}
          </span>
        ))}
      </div>

      {lastToolResult !== undefined && (
        <div style={{ fontSize: '11px', color: '#94a3b8', fontFamily: 'monospace' }}>
          tool_result: {JSON.stringify(lastToolResult).slice(0, 160)}
        </div>
      )}
    </div>
  );
};

export default DirectorPanel;
