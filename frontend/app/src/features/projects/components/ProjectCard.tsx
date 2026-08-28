/**
 * ProjectCard — Cinematic AI Film Studio card.
 * All displayed data is real: status/progress derive from the project's
 * DB episode states; counts come from the API (no mock values).
 */

import React from 'react';
import { Film, MoreHorizontal, Play, Layers, Crown, Theater, Leaf, Landmark, BarChart3 } from 'lucide-react';

import type { ProjectResource } from '@windagent/api-contracts';
import {
  getCoverDesign,
  STATUS_LABEL,
  STATUS_CONFIG,
} from '../model/types';
import type { ProjectListItem } from '../hooks/useProjects';

export interface ProjectCardProps {
  project: ProjectListItem;
  onOpen: (projectId: string) => void;
}

function formatRelativeTime(dateStr?: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);
    if (diffSec < 60) return 'Vừa xong';
    if (diffMin < 60) return `${diffMin}m trước`;
    if (diffHour < 24) return `${diffHour}h trước`;
    if (diffDay < 7) return `${diffDay}d trước`;
    if (diffDay < 30) return `${diffDay} ngày trước`;
    return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch {
    return dateStr;
  }
}

function GenreIcon({ genre }: { genre: string }) {
  const g = genre.toLowerCase();
  if (g.includes('sci-fi') || g.includes('cyberpunk')) return <BarChart3 size={14} />;
  if (g.includes('fantasy') || g.includes('adventure')) return <Crown size={14} />;
  if (g.includes('mystery') || g.includes('drama') || g.includes('noir')) return <Theater size={14} />;
  if (g.includes('family') || g.includes('animation')) return <Leaf size={14} />;
  if (g.includes('history')) return <Landmark size={14} />;
  if (g.includes('thriller')) return <Theater size={14} />;
  return <Layers size={14} />;
}

export const ProjectCard: React.FC<ProjectCardProps> = ({ project, onOpen }) => {
  const cover = getCoverDesign(project.id, project.name);
  const genre = (project.metadata?.genre as string) || null;
  const epCount = project.episodes_count ?? 0;
  const status = project.derived_status;
  const progress = project.progress_percent;
  const sCfg = STATUS_CONFIG[status];
  const sLabel = STATUS_LABEL[status];

  const isCompleted = status === 'completed';

  return (
    <div
      onClick={() => onOpen(project.id)}
      data-testid={`project-card-${project.id}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        borderRadius: '16px',
        overflow: 'hidden',
        background: '#131b2e',
        border: '1px solid rgba(255,255,255,0.08)',
        boxShadow: '0 12px 32px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.04) inset',
        cursor: 'pointer',
        transition: 'transform 0.25s cubic-bezier(0.16,1,0.3,1), border-color 0.2s, box-shadow 0.25s',
        height: '100%',
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-4px)';
        (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(77,142,255,0.35)';
        (e.currentTarget as HTMLDivElement).style.boxShadow = '0 18px 40px rgba(0,0,0,0.55), 0 0 20px rgba(77,142,255,0.15)';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.transform = 'translateY(0)';
        (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(255,255,255,0.08)';
        (e.currentTarget as HTMLDivElement).style.boxShadow = '0 12px 32px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.04) inset';
      }}
    >
      {/* Cover Banner */}
      <div
        style={{
          height: '148px',
          position: 'relative',
          overflow: 'hidden',
          background: `linear-gradient(135deg, ${cover.from} 0%, ${cover.via} 55%, ${cover.to} 100%)`,
          flexShrink: 0,
        }}
      >
        {/* gradient overlay */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'linear-gradient(to top, rgba(6,14,32,0.72) 0%, rgba(6,14,32,0.12) 45%, rgba(0,0,0,0) 100%)',
          }}
        />

        {/* Status pill top-right */}
        <div
          style={{
            position: 'absolute',
            top: '10px',
            right: '12px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '5px 10px',
            borderRadius: '9999px',
            background: isCompleted ? 'rgba(16,185,129,0.22)' : sCfg.bg,
            border: `1px solid ${sCfg.border}`,
            backdropFilter: 'blur(10px)',
            color: sCfg.color,
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.02em',
            boxShadow: '0 4px 12px rgba(0,0,0,0.35)',
          }}
        >
          <span
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: sCfg.dot,
              boxShadow: `0 0 8px ${sCfg.dot}`,
              display: 'inline-block',
              flexShrink: 0,
            }}
          />
          <span>{sLabel}</span>
          {isCompleted && <span style={{ fontSize: '10px', lineHeight: 1 }}>✓</span>}
        </div>
      </div>

      {/* Content */}
      <div style={{ padding: '14px 14px 12px 14px', display: 'flex', flexDirection: 'column', flex: 1, gap: '10px', background: '#131b2e' }}>
        {/* Title row with icon + menu + play */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', flex: 1, minWidth: 0 }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.08)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-muted, #cbd5e1)',
                flexShrink: 0,
              }}
            >
              {genre ? <GenreIcon genre={genre} /> : <Film size={14} />}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <h3
                style={{
                  margin: 0,
                  fontSize: '15px',
                  fontWeight: 750,
                  color: '#f1f5f9',
                  lineHeight: 1.35,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
                title={project.name}
              >
                {project.name}
              </h3>
              <p
                style={{
                  margin: '3px 0 0 0',
                  fontSize: '11.5px',
                  color: '#94a3b8',
                  lineHeight: 1.5,
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                  minHeight: '34px',
                }}
                title={project.description || undefined}
              >
                {project.description || 'Chưa có mô tả chi tiết cho dự án này.'}
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0, paddingTop: '2px' }}>
            <button
              onClick={(e) => {
                e.stopPropagation();
              }}
              style={{
                width: '28px',
                height: '28px',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.08)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#94a3b8',
                cursor: 'pointer',
              }}
              aria-label="More"
            >
              <MoreHorizontal size={14} />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onOpen(project.id);
              }}
              style={{
                width: '28px',
                height: '28px',
                borderRadius: '8px',
                background: 'rgba(77,142,255,0.18)',
                border: '1px solid rgba(77,142,255,0.35)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#93c5fd',
                cursor: 'pointer',
              }}
              aria-label="Play / Open"
            >
              <Play size={12} fill="currentColor" style={{ marginLeft: '1px' }} />
            </button>
          </div>
        </div>

        {/* Genre pill + real progress percent */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
          {genre ? (
            <span
              style={{
                display: 'inline-flex',
                padding: '2px 8px',
                borderRadius: '9999px',
                fontSize: '10.5px',
                fontWeight: 650,
                letterSpacing: '0.02em',
                background: cover.badgeBg,
                border: `1px solid ${cover.badgeBorder}`,
                color: cover.accent,
              }}
            >
              {genre.split('/')[0].trim()}
            </span>
          ) : (
            <span
              style={{
                display: 'inline-flex',
                padding: '2px 8px',
                borderRadius: '9999px',
                fontSize: '10.5px',
                fontWeight: 650,
                letterSpacing: '0.02em',
                background: 'rgba(148,163,184,0.12)',
                border: '1px solid rgba(148,163,184,0.25)',
                color: '#94a3b8',
              }}
            >
              Chưa phân loại
            </span>
          )}
          <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 700 }}>{progress}%</span>
        </div>

        {/* Progress bar */}
        <div
          style={{
            height: '4px',
            borderRadius: '9999px',
            background: 'rgba(255,255,255,0.08)',
            overflow: 'hidden',
            position: 'relative',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${progress}%`,
              background: isCompleted
                ? 'linear-gradient(90deg, #10b981 0%, #34d399 100%)'
                : 'linear-gradient(90deg, #4d8eff 0%, #818cf8 100%)',
              borderRadius: '9999px',
              transition: 'width 0.6s ease',
              boxShadow: isCompleted ? '0 0 8px rgba(16,185,129,0.5)' : '0 0 8px rgba(77,142,255,0.45)',
            }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '-2px' }}>
          <span style={{ fontSize: '10px', color: '#64748b', fontWeight: 500 }}>Cập nhật {formatRelativeTime(project.updated_at)}</span>
        </div>

        {/* Footer stats — real data only */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            paddingTop: '10px',
            borderTop: '1px solid rgba(255,255,255,0.06)',
            marginTop: '2px',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#94a3b8', fontWeight: 500 }}>
            <Film size={12} style={{ opacity: 0.9 }} />
            {epCount} Tập
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#94a3b8', fontWeight: 500 }}>
            <Layers size={12} style={{ opacity: 0.9 }} />
            v{project.version}
          </span>
        </div>
      </div>
    </div>
  );
};

// Re-export for consumers that still type against the base resource.
export type { ProjectResource };
