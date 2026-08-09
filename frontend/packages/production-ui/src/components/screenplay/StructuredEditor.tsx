import React from 'react';
import { ScreenplayReadModelDTO, SceneReadDTO, DialogueReadDTO } from '@windagent/production-contracts';

interface StructuredEditorProps {
  readModel: ScreenplayReadModelDTO;
  selectedSceneId: string | null;
  onUpdateSceneField: (sceneId: string, fieldName: keyof SceneReadDTO, value: unknown) => void;
  onUpdateDialogueField: (sceneId: string, dialogueId: string, fieldName: keyof DialogueReadDTO, value: unknown) => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  isReadOnly?: boolean;
}

export const StructuredEditor: React.FC<StructuredEditorProps> = ({
  readModel,
  selectedSceneId,
  onUpdateSceneField,
  onUpdateDialogueField,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  isReadOnly = false,
}) => {
  const activeScene = readModel.scenes.find((s) => s.scene_id === selectedSceneId) || readModel.scenes[0];

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: '#1E1E2E',
        color: '#CDD6F4',
        fontFamily: 'Inter, system-ui, sans-serif',
      }}
    >
      {/* Editor Toolbar with Undo/Redo */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.5rem 1rem',
          backgroundColor: '#181825',
          borderBottom: '1px solid #313244',
        }}
      >
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#89B4FA' }}>
          STRUCTURED EDITOR {isReadOnly ? '(READ-ONLY)' : ''}
        </span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={onUndo}
            disabled={!canUndo || isReadOnly}
            style={{
              padding: '0.25rem 0.6rem',
              borderRadius: '4px',
              border: 'none',
              backgroundColor: canUndo && !isReadOnly ? '#313244' : '#181825',
              color: canUndo && !isReadOnly ? '#CDD6F4' : '#585B70',
              fontSize: '0.75rem',
              cursor: canUndo && !isReadOnly ? 'pointer' : 'default',
            }}
          >
            ↩ Undo
          </button>
          <button
            onClick={onRedo}
            disabled={!canRedo || isReadOnly}
            style={{
              padding: '0.25rem 0.6rem',
              borderRadius: '4px',
              border: 'none',
              backgroundColor: canRedo && !isReadOnly ? '#313244' : '#181825',
              color: canRedo && !isReadOnly ? '#CDD6F4' : '#585B70',
              fontSize: '0.75rem',
              cursor: canRedo && !isReadOnly ? 'pointer' : 'default',
            }}
          >
            ↪ Redo
          </button>
        </div>
      </div>

      {/* Editor Body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '1.25rem 1.5rem' }}>
        {activeScene ? (
          <div style={{ maxWidth: '800px', margin: '0 auto' }}>
            {/* Scene Header Card */}
            <div
              style={{
                backgroundColor: '#181825',
                padding: '1rem 1.25rem',
                borderRadius: '8px',
                border: '1px solid #313244',
                marginBottom: '1.5rem',
              }}
            >
              <div style={{ display: 'flex', gap: '1rem', marginBottom: '0.75rem' }}>
                <div style={{ flex: 2 }}>
                  <label style={{ fontSize: '0.7rem', color: '#A6ADC8', fontWeight: 600 }}>SCENE HEADING</label>
                  <input
                    type="text"
                    value={activeScene.title}
                    disabled={isReadOnly}
                    onChange={(e) => onUpdateSceneField(activeScene.scene_id, 'title', e.target.value)}
                    style={{
                      width: '100%',
                      padding: '0.45rem',
                      borderRadius: '6px',
                      border: '1px solid #45475A',
                      backgroundColor: '#1E1E2E',
                      color: '#F5E0DC',
                      fontWeight: 700,
                      fontSize: '0.9rem',
                    }}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.7rem', color: '#A6ADC8', fontWeight: 600 }}>TIME OF DAY</label>
                  <select
                    value={activeScene.time_of_day}
                    disabled={isReadOnly}
                    onChange={(e) => onUpdateSceneField(activeScene.scene_id, 'time_of_day', e.target.value)}
                    style={{
                      width: '100%',
                      padding: '0.45rem',
                      borderRadius: '6px',
                      border: '1px solid #45475A',
                      backgroundColor: '#1E1E2E',
                      color: '#CDD6F4',
                      fontSize: '0.85rem',
                    }}
                  >
                    <option value="DAY">DAY</option>
                    <option value="NIGHT">NIGHT</option>
                    <option value="DAWN">DAWN</option>
                    <option value="DUSK">DUSK</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={{ fontSize: '0.7rem', color: '#A6ADC8', fontWeight: 600 }}>ACTION DESCRIPTION</label>
                <textarea
                  rows={3}
                  value={activeScene.action_description}
                  disabled={isReadOnly}
                  onChange={(e) => onUpdateSceneField(activeScene.scene_id, 'action_description', e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.5rem',
                    borderRadius: '6px',
                    border: '1px solid #45475A',
                    backgroundColor: '#1E1E2E',
                    color: '#CDD6F4',
                    fontSize: '0.85rem',
                    fontFamily: 'Courier New, monospace',
                  }}
                />
              </div>
            </div>

            {/* Dialogue Section */}
            <div>
              <h4 style={{ margin: '0 0 0.75rem 0', color: '#FAB387', fontSize: '0.85rem', fontWeight: 700 }}>
                DIALOGUE LINES ({activeScene.dialogue_lines.length})
              </h4>
              {activeScene.dialogue_lines.map((dlg) => (
                <div
                  key={dlg.dialogue_id}
                  style={{
                    backgroundColor: '#181825',
                    padding: '0.75rem 1rem',
                    borderRadius: '6px',
                    border: '1px solid #313244',
                    marginBottom: '0.75rem',
                  }}
                >
                  <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '0.4rem' }}>
                    <input
                      type="text"
                      value={dlg.character_name}
                      disabled={isReadOnly}
                      onChange={(e) =>
                        onUpdateDialogueField(activeScene.scene_id, dlg.dialogue_id, 'character_name', e.target.value)
                      }
                      style={{
                        padding: '0.3rem 0.5rem',
                        borderRadius: '4px',
                        border: '1px solid #45475A',
                        backgroundColor: '#1E1E2E',
                        color: '#89B4FA',
                        fontWeight: 700,
                        fontSize: '0.8rem',
                        width: '140px',
                      }}
                    />
                    <input
                      type="text"
                      placeholder="Delivery (e.g. whispered)"
                      value={dlg.delivery || ''}
                      disabled={isReadOnly}
                      onChange={(e) =>
                        onUpdateDialogueField(activeScene.scene_id, dlg.dialogue_id, 'delivery', e.target.value)
                      }
                      style={{
                        padding: '0.3rem 0.5rem',
                        borderRadius: '4px',
                        border: '1px solid #45475A',
                        backgroundColor: '#1E1E2E',
                        color: '#A6ADC8',
                        fontStyle: 'italic',
                        fontSize: '0.75rem',
                        flex: 1,
                      }}
                    />
                  </div>
                  <textarea
                    rows={2}
                    value={dlg.text}
                    disabled={isReadOnly}
                    onChange={(e) =>
                      onUpdateDialogueField(activeScene.scene_id, dlg.dialogue_id, 'text', e.target.value)
                    }
                    style={{
                      width: '100%',
                      padding: '0.4rem 0.5rem',
                      borderRadius: '4px',
                      border: '1px solid #45475A',
                      backgroundColor: '#1E1E2E',
                      color: '#F5E0DC',
                      fontSize: '0.85rem',
                    }}
                  />
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ color: '#6C7086', textAlign: 'center', marginTop: '3rem' }}>Select a scene to edit.</div>
        )}
      </div>
    </div>
  );
};
