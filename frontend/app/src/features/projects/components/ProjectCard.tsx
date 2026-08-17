/**
 * ProjectCard — Modern cinematic card presentation for Studio projects.
 */

import React from 'react';
import { Film, Clock, ArrowRight, Layers } from 'lucide-react';
import { Card, Badge } from '@windagent/ui';

import type { ProjectResource } from '@windagent/api-contracts';
import { getCoverDesign } from '../model/types';

export interface ProjectCardProps {
  project: ProjectResource;
  onOpen: (projectId: string) => void;
}

function formatRelativeTime(dateStr?: string | null): string {
  if (!dateStr) return 'Vừa xong';
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
    return d.toLocaleDateString('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

export const ProjectCard: React.FC<ProjectCardProps> = ({ project, onOpen }) => {
  const cover = getCoverDesign(project.id, project.name);
  const genre = (project.metadata?.genre as string) || cover.genre;
  const epCount = project.episodes_count ?? 0;

  return (
    <Card
      interactive
      onClick={() => onOpen(project.id)}
      style={{
        display: 'flex',
        flexDirection: 'column',
        borderRadius: '16px',
        overflow: 'hidden',
        background: 'var(--bg-panel, #0f172a)',
        border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.3)',
        transition: 'transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s',
        cursor: 'pointer',
      }}
      data-testid={`project-card-${project.id}`}
    >
      {/* Cover Header Banner */}
      <div
        style={{
          height: '140px',
          background: `linear-gradient(135deg, ${cover.from} 0%, ${cover.via} 50%, ${cover.to} 100%)`,
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          position: 'relative',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Badge
            style={{
              background: cover.badgeBg,
              border: `1px solid ${cover.badgeBorder}`,
              color: '#ffffff',
              fontSize: '11px',
              fontWeight: 600,
              backdropFilter: 'blur(8px)',
            }}
          >
            {genre}
          </Badge>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              background: 'rgba(0, 0, 0, 0.45)',
              backdropFilter: 'blur(8px)',
              padding: '4px 8px',
              borderRadius: '20px',
              color: '#ffffff',
              fontSize: '12px',
              fontWeight: 600,
            }}
          >
            <Film size={13} />
            <span>{epCount} {epCount === 1 ? 'tập' : 'tập'}</span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              background: 'rgba(0, 0, 0, 0.35)',
              backdropFilter: 'blur(4px)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#ffffff',
            }}
          >
            <Layers size={16} />
          </div>
          <span style={{ fontSize: '12px', color: 'rgba(255, 255, 255, 0.85)', fontWeight: 500 }}>
            v{project.version}
          </span>
        </div>
      </div>

      {/* Content Section */}
      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', flex: 1 }}>
        <h3
          style={{
            margin: '0 0 8px 0',
            fontSize: '18px',
            fontWeight: 700,
            color: 'var(--text-primary, #f8fafc)',
            lineHeight: 1.3,
          }}
        >
          {project.name}
        </h3>

        <p
          style={{
            margin: '0 0 16px 0',
            fontSize: '13px',
            color: 'var(--text-muted, #94a3b8)',
            lineHeight: 1.5,
            flex: 1,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {project.description || 'Chưa có mô tả chi tiết cho dự án.'}
        </p>

        {/* Footer Meta */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingTop: '12px',
            borderTop: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.06))',
            fontSize: '12px',
            color: 'var(--text-muted, #64748b)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Clock size={13} />
            <span>{formatRelativeTime(project.updated_at)}</span>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              color: cover.accent,
              fontWeight: 600,
            }}
          >
            <span>Mở dự án</span>
            <ArrowRight size={14} />
          </div>
        </div>
      </div>
    </Card>
  );
};
