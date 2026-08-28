/**
 * ProjectList — Table/list presentation for Studio projects.
 */

import React from 'react';
import { Film, Clock, ArrowRight, Layers } from 'lucide-react';
import { Badge, Card } from '@windagent/ui';
import type { ProjectResource } from '@windagent/api-contracts';
import { getCoverDesign } from '../model/types';

export interface ProjectListProps {
  projects: ProjectResource[];
  onOpen: (projectId: string) => void;
}

export const ProjectList: React.FC<ProjectListProps> = ({ projects, onOpen }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {projects.map((project) => {
        const cover = getCoverDesign(project.id, project.name);
        const genre = (project.metadata?.genre as string) || null;
        const epCount = project.episodes_count ?? 0;

        return (
          <Card
            key={project.id}
            interactive
            onClick={() => onOpen(project.id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '14px 20px',
              borderRadius: '12px',
              background: 'var(--bg-panel, #0f172a)',
              border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
              transition: 'background 0.2s, border-color 0.2s',
              cursor: 'pointer',
            }}
            data-testid={`project-list-row-${project.id}`}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flex: 1, minWidth: 0 }}>
              <div
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '10px',
                  background: `linear-gradient(135deg, ${cover.from} 0%, ${cover.to} 100%)`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#ffffff',
                  flexShrink: 0,
                }}
              >
                <Layers size={18} />
              </div>

              <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                  <span
                    style={{
                      fontSize: '15px',
                      fontWeight: 700,
                      color: 'var(--text-primary, #f8fafc)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {project.name}
                  </span>
                  <Badge
                    style={{
                      background: genre ? cover.badgeBg : 'rgba(148,163,184,0.12)',
                      border: `1px solid ${genre ? cover.badgeBorder : 'rgba(148,163,184,0.25)'}`,
                      color: genre ? cover.accent : '#94a3b8',
                      fontSize: '11px',
                    }}
                  >
                    {genre ? genre.split('/')[0].trim() : 'Chưa phân loại'}
                  </Badge>
                </div>
                <p
                  style={{
                    margin: 0,
                    fontSize: '13px',
                    color: 'var(--text-muted, #94a3b8)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {project.description || 'Chưa có mô tả'}
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '24px', flexShrink: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted, #94a3b8)', fontSize: '13px' }}>
                <Film size={14} />
                <span>{epCount} tập</span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted, #64748b)', fontSize: '12px' }}>
                <Clock size={13} />
                <span>v{project.version}</span>
              </div>

              <div style={{ color: cover.accent, display: 'flex', alignItems: 'center' }}>
                <ArrowRight size={16} />
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
};
