/**
 * EpisodeWorkspacePage — The Canonical Story & Screenplay Pipeline Workspace.
 * 100% backend V3 backed, immutable revision authority, realtime WebSocket sync.
 */

import React, { useState } from 'react';
import { ArrowLeft, Wifi, WifiOff, AlertCircle } from 'lucide-react';
import { useRouter } from '../../../app/router';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import { useEpisode } from '../hooks/useEpisode';
import { useEpisodeArtifacts } from '../hooks/useEpisodeArtifacts';
import { useEpisodeCommands } from '../hooks/useEpisodeCommands';
import { useEpisodeRealtime } from '../hooks/useEpisodeRealtime';
import { EpisodePipeline } from '../workspace/EpisodePipeline';
import { IdeaPanel } from '../workspace/IdeaPanel';
import { StoryBiblePanel } from '../workspace/StoryBiblePanel';
import { OutlinePanel } from '../workspace/OutlinePanel';
import { ScreenplayPanel } from '../workspace/ScreenplayPanel';
import { CheckpointReviewPanel } from '../workspace/CheckpointReviewPanel';
import type { CheckpointStage } from '../model/types';
import { Button, Card, Badge } from '@windagent/ui';

export interface EpisodeWorkspacePageProps {
  episodeId?: string;
}

export const EpisodeWorkspacePage: React.FC<EpisodeWorkspacePageProps> = ({ episodeId: propEpisodeId }) => {
  const { currentRoute, navigate } = useRouter();
  const client = useApiClient();
  const episodeId = propEpisodeId || (currentRoute as any)?.params?.episodeId || '';

  const { episode, isLoading, isError, error, refetch, invalidate } = useEpisode(episodeId);
  const {
    latestIdeaSet,
    latestStoryBible,
    latestOutline,
    latestScreenplay,
  } = useEpisodeArtifacts(episodeId);


  const {
    isGenerating,
    selectIdea,
    isSelectingIdea,
    submitDecision,
    isSubmittingDecision,
    lockScreenplay,
    isLocking,
  } = useEpisodeCommands(episodeId);

  const { isConnected } = useEpisodeRealtime(episodeId);

  // P0.7 — the Start buttons drive the REAL durable Story run through
  // /api/v3/studio (preflight gate + start-or-resume), never the legacy
  // instant-COMPLETED stub. Server state decides; the UI only reports.
  const [startError, setStartError] = useState<string | null>(null);
  const handleStartStory = async () => {
    setStartError(null);
    try {
      const report = await client.studio.preflightStart(episodeId);
      const failed = report.checks.filter((c) => c.status === 'FAIL');
      if (!report.ready) {
        setStartError(
          'START_BLOCKED: ' +
            failed.map((c) => `${c.name}${c.detail ? ` — ${c.detail}` : ''}`).join('; '),
        );
        return;
      }
      await client.studio.startRun(episodeId, crypto.randomUUID());
      invalidate();
      refetch();
    } catch (err: any) {
      setStartError(err?.message || 'Không thể bắt đầu Story run.');
    }
  };

  const [activeTab, setActiveTab] = useState<CheckpointStage>('SCREENPLAY');

  // Auto-align active tab when episode loads if not already chosen
  React.useEffect(() => {
    if (episode?.current_checkpoint) {
      setActiveTab(episode.current_checkpoint as CheckpointStage);
    }
  }, [episode?.current_checkpoint]);

  if (isLoading && !episode) {
    return (
      <div style={{ padding: '48px 32px', maxWidth: '1200px', margin: '0 auto', textAlign: 'center', color: '#94a3b8' }}>
        <div style={{ width: '36px', height: '36px', border: '3px solid #1e293b', borderTopColor: '#3b82f6', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 16px' }} />
        <span>Đang tải không gian kịch bản...</span>
      </div>
    );
  }

  if (isError || !episode) {
    return (
      <div style={{ padding: '32px', maxWidth: '1200px', margin: '0 auto' }}>
        <Button variant="ghost" onClick={() => navigate('/episodes')} style={{ marginBottom: '16px' }}>
          <ArrowLeft size={16} style={{ marginRight: '6px' }} />
          Quay lại danh sách tập phim
        </Button>
        <Card style={{ padding: '24px', background: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: '#f87171' }}>
            <AlertCircle size={20} />
            <div>
              <strong>Lỗi:</strong> {error?.message || `Không tìm thấy tập phim với ID "${episodeId}".`}
            </div>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div
      style={{
        padding: '32px',
        maxWidth: '1360px',
        margin: '0 auto',
        minHeight: '100%',
        color: 'var(--text-primary, #f8fafc)',
      }}
      data-testid="canonical-episode-workspace-page"
    >
      {/* Workspace Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Button variant="ghost" onClick={() => navigate(`/projects/${episode.project_id}`)} style={{ padding: '8px 12px' }}>
            <ArrowLeft size={16} />
          </Button>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 800 }}>
                {episode.title}
              </h1>
              <Badge style={{ background: 'rgba(59, 130, 246, 0.15)', color: '#3b82f6', fontSize: '11px' }}>
                Tập {episode.episode_number}
              </Badge>
            </div>
            <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)' }}>
              {(episode as any).project_name || 'Dự án Phim'} | v{episode.version}
            </span>
          </div>
        </div>

        {/* Realtime & Progress Badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 10px',
              borderRadius: '20px',
              fontSize: '12px',
              background: isConnected ? 'rgba(34, 197, 94, 0.12)' : 'rgba(234, 179, 8, 0.12)',
              color: isConnected ? '#4ade80' : '#facc15',
              border: `1px solid ${isConnected ? 'rgba(34, 197, 94, 0.25)' : 'rgba(234, 179, 8, 0.25)'}`,
            }}
          >
            {isConnected ? <Wifi size={13} /> : <WifiOff size={13} />}
            <span>{isConnected ? 'Realtime Connected' : 'Polling Sync'}</span>
          </div>
        </div>
      </div>

      {/* P0.7 — Start Story drives the real durable run (preflight-gated) */}
      {startError && (
        <Card
          style={{
            padding: '16px 20px',
            marginBottom: '18px',
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.35)',
            borderRadius: '12px',
          }}
          role="alert"
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', color: '#fca5a5' }}>
            <AlertCircle size={18} />
            <div>
              <strong>Không thể bắt đầu Story run.</strong>
              <div style={{ fontSize: '13px', marginTop: '4px' }}>{startError}</div>
            </div>
          </div>
        </Card>
      )}

      {/* Pipeline Stepper */}
      <EpisodePipeline
        currentCheckpoint={episode.current_checkpoint || 'IDEA'}
        state={episode.state || 'DRAFT'}
        activeTab={activeTab}
        onSelectTab={(stage) => setActiveTab(stage)}
      />

      {/* Active Stage Panel */}
      <Card style={{ padding: '28px', background: 'var(--bg-panel, #0f172a)', borderRadius: '16px', border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))' }}>
        {activeTab === 'IDEA' && (
          <IdeaPanel
            artifact={latestIdeaSet}
            isGenerating={isGenerating}
            onStartGeneration={() => void handleStartStory()}
            onSelectIdea={(ideaId) => selectIdea({ idea_id: ideaId, expected_version: episode.version })}
            isSelectingIdea={isSelectingIdea}
          />
        )}

        {activeTab === 'STORY_BIBLE' && (
          <StoryBiblePanel
            artifact={latestStoryBible}
            isGenerating={isGenerating}
            onStartGeneration={() => void handleStartStory()}
          />
        )}

        {activeTab === 'OUTLINE' && (
          <OutlinePanel
            artifact={latestOutline}
            isGenerating={isGenerating}
            onStartGeneration={() => void handleStartStory()}
          />
        )}

        {activeTab === 'SCREENPLAY' && (
          <ScreenplayPanel
            artifact={latestScreenplay}
            isGenerating={isGenerating}
            onStartGeneration={() => void handleStartStory()}
          />
        )}

        {(activeTab === 'REVIEW' || activeTab === 'LOCKED' || activeTab === 'READY_FOR_PRODUCTION') && (
          <ScreenplayPanel
            artifact={latestScreenplay}
            isGenerating={isGenerating}
            onStartGeneration={() => void handleStartStory()}
          />
        )}
      </Card>

      {/* Checkpoint Review Action Bar */}
      <CheckpointReviewPanel
        episode={episode}
        isSubmitting={isSubmittingDecision || isLocking}
        screenplayContentHash={(latestScreenplay as any)?.content_hash ?? null}
        onApprove={async (revId, expectedVer) => {
          await submitDecision({ decision: 'APPROVED', revision_id: revId, expected_version: expectedVer });
          invalidate();
          refetch();
        }}
        onRevise={async (revId, feedback, expectedVer) => {
          await submitDecision({ decision: 'REVISE', revision_id: revId, feedback, expected_version: expectedVer });
          invalidate();
          refetch();
        }}
        onLock={async (revId, contentHash, expectedVer) => {
          await lockScreenplay({ revision_id: revId, content_hash: contentHash, expected_version: expectedVer });
          invalidate();
          refetch();
        }}
      />
    </div>
  );
};
