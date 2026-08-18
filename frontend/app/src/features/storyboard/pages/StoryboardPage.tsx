/**
 * Phase 9C — StoryboardPage
 * Canonical storyboard UI.
 * ZERO DEFAULT_SCENES. ZERO setTimeout fake timers.
 * Generation = server-issued generation_id + realtime WebSocket progress.
 */
import React, { useState } from 'react';
import { useStoryboardScenes, useStoryboard, useTriggerGeneration, useSyncStoryboard, useStoryboardRealtime } from '../hooks/useStoryboard';
import type { SceneResource } from '@windagent/api-contracts';

interface StoryboardPageProps {
  episodeId: string;
  apiBaseUrl?: string;
}

const SCENE_STATUS_LABELS: Record<string, string> = {
  DRAFT: 'Nháp',
  GENERATING: 'Đang tạo...',
  CONCEPT_READY: 'Concept sẵn sàng',
  LOCKED: 'Đã khóa',
};

const SCENE_STATUS_COLORS: Record<string, string> = {
  DRAFT: '#6b7280',
  GENERATING: '#f59e0b',
  CONCEPT_READY: '#22c55e',
  LOCKED: '#6366f1',
};

export const StoryboardPage: React.FC<StoryboardPageProps> = ({ episodeId, apiBaseUrl = '' }) => {
  const [selectedScene, setSelectedScene] = useState<string | null>(null);

  const { data: storyboard, isLoading: loadingBoard } = useStoryboard(episodeId);
  const { data: scenes = [], isLoading: loadingScenes, error } = useStoryboardScenes(episodeId);
  const syncMutation = useSyncStoryboard(episodeId);
  const triggerGen = useTriggerGeneration(episodeId);

  // Realtime WebSocket subscription
  useStoryboardRealtime(episodeId, apiBaseUrl);

  const isLoading = loadingBoard || loadingScenes;

  if (isLoading) {
    return (
      <div className="storyboard-page storyboard-page--loading">
        <div className="loading-spinner" />
        <p>Đang tải storyboard...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="storyboard-page storyboard-page--error">
        <h3>Không thể tải storyboard</h3>
        <p>{(error as Error).message}</p>
      </div>
    );
  }

  const handleGenerateArt = async (scene: SceneResource) => {
    // Submit to server — get back generation_id immediately
    await triggerGen.mutateAsync({ sceneId: scene.id });
    // No setTimeout. No hardcoded image URL.
    // Progress tracked via useStoryboardRealtime WebSocket + useGenerationJob polling.
  };

  return (
    <div className="storyboard-page">
      <header className="storyboard-page__header">
        <div className="storyboard-page__title-row">
          <h1>Storyboard</h1>
          {storyboard && (
            <span className="storyboard-page__revision-pin" title="Screenplay revision pinned">
              📌 {storyboard.source_screenplay_revision_id}
            </span>
          )}
        </div>
        <div className="storyboard-page__actions">
          <span className="storyboard-page__scene-count">{scenes.length} phân cảnh</span>
          <button
            className="btn btn--secondary btn--sm"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
          >
            {syncMutation.isPending ? '⏳ Đang đồng bộ...' : '🔄 Sync Screenplay'}
          </button>
        </div>
      </header>

      {scenes.length === 0 ? (
        <div className="storyboard-page__empty">
          <span className="storyboard-page__empty-icon">🎬</span>
          <h3>Chưa có phân cảnh nào</h3>
          <p>Đồng bộ từ screenplay đã khóa để tự động tạo các phân cảnh.</p>
          <button
            className="btn btn--primary"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
          >
            Sync từ Screenplay
          </button>
        </div>
      ) : (
        <div className="storyboard-page__scenes">
          {scenes.map((scene: SceneResource) => (
            <SceneCard
              key={scene.id}
              scene={scene}
              isSelected={selectedScene === scene.id}
              isGenerating={triggerGen.isPending && triggerGen.variables?.sceneId === scene.id}
              onSelect={() => setSelectedScene(scene.id === selectedScene ? null : scene.id)}
              onGenerateArt={() => handleGenerateArt(scene)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

interface SceneCardProps {
  scene: SceneResource;
  isSelected: boolean;
  isGenerating: boolean;
  onSelect: () => void;
  onGenerateArt: () => void;
}

function SceneCard({ scene, isSelected, isGenerating, onSelect, onGenerateArt }: SceneCardProps) {
  const statusColor = SCENE_STATUS_COLORS[scene.status] ?? '#6b7280';
  const statusLabel = SCENE_STATUS_LABELS[scene.status] ?? scene.status;

  return (
    <div
      className={`scene-card${isSelected ? ' scene-card--selected' : ''}`}
      onClick={onSelect}
    >
      <div className="scene-card__number">#{scene.scene_number}</div>

      <div className="scene-card__concept-art">
        {scene.concept_image_url ? (
          <img src={scene.concept_image_url} alt={`Concept art — ${scene.title}`} loading="lazy" />
        ) : (
          <div className="scene-card__art-placeholder">
            {(isGenerating || scene.status === 'GENERATING') ? (
              <div className="scene-card__generating">
                <div className="scene-card__spinner" />
                <span>Đang tạo ảnh...</span>
              </div>
            ) : (
              <>
                <span className="scene-card__art-icon">🎨</span>
                <span className="scene-card__art-hint">Chưa có concept art</span>
              </>
            )}
          </div>
        )}
      </div>

      <div className="scene-card__body">
        <div className="scene-card__header">
          <h3 className="scene-card__title">{scene.title}</h3>
          <span
            className="scene-card__status"
            style={{ color: statusColor, backgroundColor: `${statusColor}22`, border: `1px solid ${statusColor}44` }}
          >
            {statusLabel}
          </span>
        </div>

        <div className="scene-card__meta">
          <span className="scene-card__meta-item">📍 {scene.location || 'Không xác định'}</span>
          <span className="scene-card__meta-item">⏱ {Math.floor(scene.duration_seconds / 60)}m {scene.duration_seconds % 60}s</span>
          {scene.character_ids.length > 0 && (
            <span className="scene-card__meta-item">👥 {scene.character_ids.length} nhân vật</span>
          )}
        </div>

        {scene.script_text && (
          <p className="scene-card__script">{scene.script_text.slice(0, 200)}{scene.script_text.length > 200 ? '...' : ''}</p>
        )}

        {scene.source_screenplay_revision_id && (
          <div className="scene-card__revision-pin">
            📌 <span>{scene.source_screenplay_revision_id}</span>
          </div>
        )}
      </div>

      {isSelected && (
        <div className="scene-card__actions" onClick={(e) => e.stopPropagation()}>
          <button
            className="btn btn--primary btn--sm"
            disabled={isGenerating || scene.status === 'GENERATING'}
            onClick={onGenerateArt}
          >
            {isGenerating || scene.status === 'GENERATING' ? '⏳ Đang tạo...' : '🎨 Tạo Concept Art'}
          </button>
        </div>
      )}
    </div>
  );
}
