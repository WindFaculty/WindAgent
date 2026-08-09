import React, { useState } from 'react';
import { ScreenplayReadModelDTO, ProductionAssetBindingDTO, AssetRequirementDTO } from '@windagent/production-contracts';
import { CrossNavigationLinks } from './CrossNavigationLinks';
import { AssetPickerModal } from './AssetPickerModal';
import { MissingAssetResolverModal } from './MissingAssetResolverModal';

interface SceneInspectorProps {
  readModel: ScreenplayReadModelDTO;
  selectedSceneId: string | null;
  bindings?: ProductionAssetBindingDTO[];
  requirements?: AssetRequirementDTO[];
  onBindAsset?: (entityType: 'CHARACTER' | 'LOCATION' | 'PROP', entityId: string, assetId: string) => void;
  onUnbindAsset?: (bindingId: string) => void;
  onNavigate?: (url: string) => void;
}

export const SceneInspector: React.FC<SceneInspectorProps> = ({
  readModel,
  selectedSceneId,
  bindings = [
    {
      binding_id: 'bnd_bunny_01',
      project_id: 'vp_01',
      production_revision_id: 'rev_13',
      screenplay_entity_type: 'CHARACTER',
      screenplay_entity_id: 'char_bunny',
      role_key: 'primary',
      asset_id: 'asset_bunny',
      asset_revision_id: 'rev_asset_bunny_v1',
      status: 'ACTIVE',
      created_by: 'user',
      created_at: new Date().toISOString(),
    },
  ],
  requirements = [
    {
      requirement_id: 'req_ball_01',
      project_id: 'vp_01',
      revision_id: 'rev_13',
      screenplay_entity_id: 'prop_ball',
      screenplay_entity_type: 'PROP',
      role_key: 'primary',
      required_kind: 'PROP_3D_OBJECT',
      required_media: 'IMAGE',
      description: "Missing 3D prop asset for 'Red Beach Ball'",
      severity: 'BLOCKING',
      status: 'OPEN',
      candidate_asset_ids: [],
    },
  ],
  onBindAsset,
  onUnbindAsset,
  onNavigate,
}) => {
  const activeScene = readModel.scenes.find((s) => s.scene_id === selectedSceneId) || readModel.scenes[0];
  const downstream = readModel.downstream_bindings.find((b) => b.scene_id === selectedSceneId);

  const [pickerEntity, setPickerEntity] = useState<{ type: 'CHARACTER' | 'LOCATION' | 'PROP'; id: string; name: string } | null>(null);
  const [resolverRequirement, setResolverRequirement] = useState<AssetRequirementDTO | null>(null);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: '#181825',
        borderLeft: '1px solid #313244',
        color: '#CDD6F4',
        fontFamily: 'Inter, system-ui, sans-serif',
        padding: '1rem',
        overflowY: 'auto',
      }}
    >
      <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.85rem', fontWeight: 700, color: '#F9E2AF', letterSpacing: '0.05em' }}>
        SCENE INSPECTOR
      </h3>

      {activeScene ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <div style={{ fontSize: '0.7rem', color: '#A6ADC8', fontWeight: 600 }}>SCENE IDENTIFIER</div>
            <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#89B4FA' }}>{activeScene.scene_id}</div>
          </div>

          <div>
            <div style={{ fontSize: '0.7rem', color: '#A6ADC8', fontWeight: 600 }}>ESTIMATED DURATION</div>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#A6E3A1' }}>
              ⏱ {activeScene.estimated_duration_seconds} seconds
            </div>
          </div>

          {/* Characters Binding Section */}
          <div>
            <div style={{ fontSize: '0.7rem', color: '#A6ADC8', fontWeight: 600, marginBottom: '0.4rem' }}>
              CHARACTERS BINDINGS ({activeScene.character_ids.length})
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {activeScene.character_ids.map((charId) => {
                const binding = bindings.find(
                  (b) => b.screenplay_entity_id === charId && b.screenplay_entity_type === 'CHARACTER' && b.status === 'ACTIVE'
                );
                return (
                  <div
                    key={charId}
                    style={{
                      padding: '0.4rem 0.6rem',
                      borderRadius: '4px',
                      backgroundColor: '#1E1E2E',
                      border: '1px solid #313244',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      fontSize: '0.75rem',
                    }}
                  >
                    <div>
                      <span style={{ color: '#CBA6F7', fontWeight: 600 }}>{charId}</span>
                      {binding ? (
                        <div style={{ fontSize: '0.65rem', color: '#A6E3A1' }}>
                          Bound: {binding.asset_id}
                        </div>
                      ) : (
                        <div style={{ fontSize: '0.65rem', color: '#F38BA8' }}>Missing Asset</div>
                      )}
                    </div>
                    {binding ? (
                      <button
                        onClick={() => onUnbindAsset && onUnbindAsset(binding.binding_id)}
                        style={{
                          padding: '0.2rem 0.4rem',
                          borderRadius: '3px',
                          backgroundColor: '#313244',
                          border: 'none',
                          color: '#F38BA8',
                          fontSize: '0.65rem',
                          cursor: 'pointer',
                        }}
                      >
                        Unbind
                      </button>
                    ) : (
                      <button
                        onClick={() => setPickerEntity({ type: 'CHARACTER', id: charId, name: charId })}
                        style={{
                          padding: '0.2rem 0.4rem',
                          borderRadius: '3px',
                          backgroundColor: '#89B4FA',
                          border: 'none',
                          color: '#11111B',
                          fontSize: '0.65rem',
                          fontWeight: 700,
                          cursor: 'pointer',
                        }}
                      >
                        Bind
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Missing Requirements Alert Section (UI36) */}
          {requirements.length > 0 && (
            <div style={{ backgroundColor: '#2a1e24', border: '1px solid #f38ba840', padding: '0.75rem', borderRadius: '6px' }}>
              <div style={{ fontSize: '0.7rem', fontWeight: 700, color: '#F38BA8', marginBottom: '0.4rem' }}>
                ⚠️ MISSING ASSET REQUIREMENTS ({requirements.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                {requirements.map((req) => (
                  <div
                    key={req.requirement_id}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      fontSize: '0.7rem',
                      color: '#CDD6F4',
                    }}
                  >
                    <span>{req.screenplay_entity_id} ({req.required_kind})</span>
                    <button
                      onClick={() => setResolverRequirement(req)}
                      style={{
                        padding: '0.2rem 0.45rem',
                        borderRadius: '4px',
                        backgroundColor: '#89B4FA',
                        border: 'none',
                        color: '#11111B',
                        fontSize: '0.65rem',
                        fontWeight: 700,
                        cursor: 'pointer',
                      }}
                    >
                      Resolve...
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <div style={{ fontSize: '0.7rem', color: '#A6ADC8', fontWeight: 600, marginBottom: '0.3rem' }}>
              DOWNSTREAM BINDINGS & NAV
            </div>
            <div style={{ backgroundColor: '#1E1E2E', padding: '0.75rem', borderRadius: '6px', fontSize: '0.75rem' }}>
              <div>Shots: {downstream?.bound_shot_ids.join(', ') || 'None'}</div>
              <div>Audio: {downstream?.bound_audio_track_ids.join(', ') || 'None'}</div>
              <div>Assets: {downstream?.bound_asset_ids.join(', ') || 'None'}</div>
              <CrossNavigationLinks
                projectId="vp_01"
                revisionId="rev_13"
                sceneId={activeScene.scene_id}
                assetId={downstream?.bound_asset_ids[0] || 'asset_bunny'}
                onNavigate={onNavigate}
              />
            </div>
          </div>
        </div>
      ) : (
        <div style={{ color: '#6C7086', fontSize: '0.8rem' }}>No scene selected.</div>
      )}

      {/* Asset Picker Modal */}
      {pickerEntity && (
        <AssetPickerModal
          isOpen={!!pickerEntity}
          entityType={pickerEntity.type}
          entityId={pickerEntity.id}
          entityName={pickerEntity.name}
          onClose={() => setPickerEntity(null)}
          onConfirmBind={(assetId) => {
            if (onBindAsset && pickerEntity) {
              onBindAsset(pickerEntity.type, pickerEntity.id, assetId);
            }
            setPickerEntity(null);
          }}
        />
      )}

      {/* Missing Asset Resolver Modal */}
      {resolverRequirement && (
        <MissingAssetResolverModal
          isOpen={!!resolverRequirement}
          requirement={resolverRequirement}
          onClose={() => setResolverRequirement(null)}
          onResolveAndBind={(assetId) => {
            if (onBindAsset && resolverRequirement) {
              onBindAsset(
                resolverRequirement.screenplay_entity_type as 'CHARACTER' | 'LOCATION' | 'PROP',
                resolverRequirement.screenplay_entity_id,
                assetId
              );
            }
            setResolverRequirement(null);
          }}
        />
      )}
    </div>
  );
};
