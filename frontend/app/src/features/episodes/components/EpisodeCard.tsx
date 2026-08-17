/**
 * EpisodeCard — Catalog card presentation for episodes across projects.
 */

import React from 'react';
import { ArrowRight, Lock } from 'lucide-react';
import { Card, Badge } from '@windagent/ui';

import type { EpisodeResource } from '@windagent/api-contracts';
import { getStageProgress } from '../model/types';

export interface EpisodeCardProps {
  episode: EpisodeResource;
  onOpen: (episodeId: string) => void;
}

export const EpisodeCard: React.FC<EpisodeCardProps> = ({ episode, onOpen }) => {
  const progress = episode.progress_percent ?? getStageProgress(episode.state || 'DRAFT');
  const isLocked = episode.state === 'LOCKED' || episode.state === 'READY_FOR_PRODUCTION';

  let statusBg = 'rgba(59, 130, 246, 0.15)';
  let statusColor = '#38bdf8';
  if (isLocked) {
    statusBg = 'rgba(34, 197, 94, 0.15)';
    statusColor = '#4ade80';
  } else if (episode.state === 'SCREENPLAY') {
    statusBg = 'rgba(168, 85, 247, 0.15)';
    statusColor = '#c084fc';
  }

  return (
    <Card
      interactive
      onClick={() => onOpen(episode.id)}
      style={{
        padding: '20px',
        borderRadius: '14px',
        background: 'var(--bg-panel, #0f172a)',
        border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        cursor: 'pointer',
        transition: 'transform 0.2s, border-color 0.2s',
      }}
      data-testid={`episode-card-${episode.id}`}
    >
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                background: 'rgba(59, 130, 246, 0.12)',
                color: '#3b82f6',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 700,
                fontSize: '13px',
              }}
            >
              {episode.episode_number}
            </div>
            <span style={{ fontSize: '12px', color: 'var(--text-muted, #94a3b8)', fontWeight: 500 }}>
              {(episode as any).project_name || 'Dự án Phim'}
            </span>
          </div>

          <Badge style={{ background: statusBg, color: statusColor, fontSize: '11px', fontWeight: 600 }}>
            {isLocked ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Lock size={11} /> LOCKED
              </span>
            ) : (
              episode.current_checkpoint || episode.state || 'DRAFT'
            )}
          </Badge>
        </div>

        <h3 style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: 700, color: 'var(--text-primary, #f8fafc)' }}>
          {episode.title}
        </h3>

        <p
          style={{
            margin: '0 0 16px 0',
            fontSize: '13px',
            color: 'var(--text-muted, #94a3b8)',
            lineHeight: 1.5,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {episode.description || 'Chưa có tóm tắt cốt truyện.'}
        </p>
      </div>

      {/* Progress Bar & Footer */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px', fontSize: '12px', color: 'var(--text-muted, #94a3b8)' }}>
          <span>Tiến độ pipeline</span>
          <span style={{ fontWeight: 600, color: statusColor }}>{progress}%</span>
        </div>

        <div style={{ width: '100%', height: '6px', borderRadius: '3px', background: 'rgba(255, 255, 255, 0.06)', overflow: 'hidden', marginBottom: '14px' }}>
          <div
            style={{
              width: `${progress}%`,
              height: '100%',
              background: isLocked ? '#22c55e' : 'var(--color-primary, #3b82f6)',
              borderRadius: '3px',
              transition: 'width 0.3s ease',
            }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '10px', borderTop: '1px solid rgba(255, 255, 255, 0.06)', fontSize: '12px', color: 'var(--text-muted, #64748b)' }}>
          <span>v{episode.version}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--color-primary, #3b82f6)', fontWeight: 600 }}>
            <span>Mở kịch bản</span>
            <ArrowRight size={13} />
          </div>
        </div>
      </div>
    </Card>
  );
};
