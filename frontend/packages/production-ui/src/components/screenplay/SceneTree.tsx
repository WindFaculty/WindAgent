import React from 'react';
import { SceneReadDTO } from '@windagent/production-contracts';

interface SceneTreeProps {
  scenes: SceneReadDTO[];
  selectedSceneId: string | null;
  onSelectScene: (sceneId: string) => void;
  onAddScene: () => void;
  onReorderScene: (sceneId: string, direction: 'UP' | 'DOWN') => void;
  isReadOnly?: boolean;
}

export const SceneTree: React.FC<SceneTreeProps> = ({
  scenes,
  selectedSceneId,
  onSelectScene,
  onAddScene,
  onReorderScene,
  isReadOnly = false,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: '#181825',
        borderRight: '1px solid #313244',
        color: '#CDD6F4',
        fontFamily: 'Inter, system-ui, sans-serif',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.75rem 1rem',
          borderBottom: '1px solid #313244',
        }}
      >
        <span style={{ fontWeight: 700, fontSize: '0.85rem', color: '#CBA6F7', letterSpacing: '0.05em' }}>
          STORY TREE ({scenes.length})
        </span>
        {!isReadOnly && (
          <button
            onClick={onAddScene}
            style={{
              padding: '0.25rem 0.5rem',
              borderRadius: '4px',
              border: 'none',
              backgroundColor: '#A6E3A1',
              color: '#11111B',
              fontWeight: 700,
              fontSize: '0.75rem',
              cursor: 'pointer',
            }}
          >
            + Scene
          </button>
        )}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0.5rem' }}>
        {scenes.map((sc, index) => {
          const isSelected = sc.scene_id === selectedSceneId;
          return (
            <div
              key={sc.scene_id}
              onClick={() => onSelectScene(sc.scene_id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.5rem 0.75rem',
                marginBottom: '0.35rem',
                borderRadius: '6px',
                backgroundColor: isSelected ? '#313244' : '#1E1E2E',
                borderLeft: isSelected ? '4px solid #89B4FA' : '4px solid transparent',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <div style={{ overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis', flex: 1 }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: isSelected ? '#89B4FA' : '#F5E0DC' }}>
                  {sc.order}. {sc.title}
                </div>
                <div style={{ fontSize: '0.7rem', color: '#A6ADC8', marginTop: '0.1rem' }}>
                  ⏱ {sc.estimated_duration_seconds}s • {sc.character_ids.length} chars
                </div>
              </div>

              {!isReadOnly && isSelected && (
                <div style={{ display: 'flex', gap: '0.2rem', marginLeft: '0.5rem' }}>
                  <button
                    disabled={index === 0}
                    onClick={(e) => {
                      e.stopPropagation();
                      onReorderScene(sc.scene_id, 'UP');
                    }}
                    style={{
                      border: 'none',
                      backgroundColor: '#45475A',
                      color: '#CDD6F4',
                      borderRadius: '3px',
                      padding: '0.1rem 0.3rem',
                      fontSize: '0.65rem',
                      cursor: index === 0 ? 'not-allowed' : 'pointer',
                    }}
                  >
                    ▲
                  </button>
                  <button
                    disabled={index === scenes.length - 1}
                    onClick={(e) => {
                      e.stopPropagation();
                      onReorderScene(sc.scene_id, 'DOWN');
                    }}
                    style={{
                      border: 'none',
                      backgroundColor: '#45475A',
                      color: '#CDD6F4',
                      borderRadius: '3px',
                      padding: '0.1rem 0.3rem',
                      fontSize: '0.65rem',
                      cursor: index === scenes.length - 1 ? 'not-allowed' : 'pointer',
                    }}
                  >
                    ▼
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
