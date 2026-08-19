import React from 'react';
import { Plus, CheckCircle2, PlayCircle, Circle } from 'lucide-react';
import type { SceneItem } from '../hooks/useLiveRecord';

export interface SceneListPanelProps {
  scenes: SceneItem[];
  activeSceneIndex?: number;
  onSelectScene: (index: number) => void;
  onOpenAddScene: () => void;
  totalExpectedDurationFormatted: string;
}

export const SceneListPanel: React.FC<SceneListPanelProps> = ({
  scenes,
  onSelectScene,
  onOpenAddScene,
  totalExpectedDurationFormatted,
}) => {
  return (
    <div
      style={{
        backgroundColor: '#0c1322',
        border: '1px solid rgba(59, 130, 246, 0.2)',
        borderRadius: '16px',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        boxShadow: '0 8px 24px -6px rgba(0, 0, 0, 0.5)',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '12px',
          paddingBottom: '10px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        }}
      >
        <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#f8fafc' }}>
          Danh Sách Cảnh Quay
        </h3>
        <button
          onClick={onOpenAddScene}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '4px 10px',
            borderRadius: '6px',
            backgroundColor: 'rgba(59, 130, 246, 0.15)',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            color: '#60a5fa',
            fontSize: '12px',
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
        >
          <Plus size={13} />
          <span>Thêm cảnh</span>
        </button>
      </div>

      {/* Scene Items List */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          flex: 1,
          overflowY: 'auto',
          paddingRight: '4px',
        }}
      >
        {scenes.map((scene, idx) => {
          const isActive = scene.status === 'active';
          const isCompleted = scene.status === 'completed';

          return (
            <div
              key={scene.id}
              onClick={() => onSelectScene(idx)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '8px 12px',
                borderRadius: '8px',
                backgroundColor: isActive
                  ? 'rgba(59, 130, 246, 0.15)'
                  : 'rgba(15, 23, 42, 0.5)',
                border: `1px solid ${isActive ? 'rgba(59, 130, 246, 0.4)' : 'rgba(255, 255, 255, 0.05)'}`,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                <span
                  style={{
                    fontSize: '12px',
                    fontWeight: 700,
                    color: isActive ? '#60a5fa' : '#64748b',
                    width: '16px',
                  }}
                >
                  {scene.index}
                </span>
                <span
                  style={{
                    fontSize: '12px',
                    fontWeight: isActive ? 600 : 500,
                    color: isActive ? '#f8fafc' : isCompleted ? '#94a3b8' : '#cbd5e1',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {scene.title}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
                <span
                  style={{
                    fontSize: '11px',
                    fontFamily: 'monospace',
                    color: isActive ? '#93c5fd' : '#64748b',
                  }}
                >
                  {scene.duration}
                </span>

                {isCompleted && <CheckCircle2 size={15} color="#22c55e" />}
                {isActive && <PlayCircle size={15} color="#3b82f6" />}
                {!isCompleted && !isActive && <Circle size={15} color="#475569" />}
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer Total Duration */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingTop: '12px',
          marginTop: '8px',
          borderTop: '1px solid rgba(255, 255, 255, 0.08)',
          fontSize: '12px',
        }}
      >
        <span style={{ color: '#94a3b8' }}>Tổng thời lượng dự kiến:</span>
        <span style={{ color: '#34d399', fontWeight: 700, fontFamily: 'monospace' }}>
          {totalExpectedDurationFormatted}
        </span>
      </div>
    </div>
  );
};
