/**
 * ProjectDetailPage — Overview of a single project, its metadata, and its episode list.
 */

import React, { useState } from 'react';
import { ArrowLeft, Film, Plus, Clock, Layers, ChevronRight, AlertCircle } from 'lucide-react';
import { useRouter } from '../../../app/router';
import { useProject } from '../hooks/useProject';
import { useCreateEpisode } from '../hooks/useCreateEpisode';
import { CreateEpisodeDialog } from '../components/CreateEpisodeDialog';
import { getCoverDesign } from '../model/types';
import { Button, Card, Badge } from '@windagent/ui';


import type { EpisodeResource } from '@windagent/api-contracts';

export interface ProjectDetailPageProps {
  projectId?: string;
}

export const ProjectDetailPage: React.FC<ProjectDetailPageProps> = ({ projectId: propProjectId }) => {
  const { currentRoute, navigate } = useRouter();
  const projectId = propProjectId || (currentRoute as any)?.params?.projectId || '';


  const { project, episodes, isLoading, isError, error, refetch, invalidate } = useProject(projectId);
  const { createEpisode } = useCreateEpisode();
  const [isCreateEpisodeOpen, setIsCreateEpisodeOpen] = useState(false);

  const cover = project ? getCoverDesign(project.id, project.name) : null;
  const genre = (project?.metadata?.genre as string) || cover?.genre || 'Sci-Fi';

  const handleOpenEpisode = (episodeId: string) => {
    // Navigate to episode workspace (or production script)
    navigate(`/production/script?episodeId=${episodeId}&projectId=${projectId}`);
  };

  if (isLoading && !project) {
    return (
      <div style={{ padding: '48px 32px', maxWidth: '1200px', margin: '0 auto', textAlign: 'center', color: '#94a3b8' }}>
        <div style={{ width: '36px', height: '36px', border: '3px solid #1e293b', borderTopColor: '#3b82f6', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 16px' }} />
        <span>Đang tải thông tin dự án...</span>
      </div>
    );
  }

  if (isError || !project) {
    return (
      <div style={{ padding: '32px', maxWidth: '1200px', margin: '0 auto' }}>
        <Button variant="ghost" onClick={() => navigate('/projects')} style={{ marginBottom: '16px' }}>
          <ArrowLeft size={16} style={{ marginRight: '6px' }} />
          Quay lại danh sách dự án
        </Button>
        <Card style={{ padding: '24px', background: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: '#f87171' }}>
            <AlertCircle size={20} />
            <div>
              <strong>Lỗi:</strong> {error?.message || `Không tìm thấy dự án với ID "${projectId}".`}
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
        maxWidth: '1200px',
        margin: '0 auto',
        minHeight: '100%',
        color: 'var(--text-primary, #f8fafc)',
      }}
      data-testid="canonical-project-detail-page"
    >
      {/* Top Navigation */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <Button variant="ghost" onClick={() => navigate('/projects')} style={{ color: 'var(--text-muted, #94a3b8)' }}>
          <ArrowLeft size={16} style={{ marginRight: '6px' }} />
          Danh sách dự án
        </Button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Button variant="primary" onClick={() => setIsCreateEpisodeOpen(true)}>
            <Plus size={15} style={{ marginRight: '6px' }} />
            Thêm tập mới
          </Button>
        </div>
      </div>

      {/* Project Banner Card */}
      <Card
        style={{
          borderRadius: '16px',
          overflow: 'hidden',
          background: 'var(--bg-panel, #0f172a)',
          border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
          marginBottom: '32px',
        }}
      >
        <div
          style={{
            height: '160px',
            background: cover ? `linear-gradient(135deg, ${cover.from} 0%, ${cover.via} 50%, ${cover.to} 100%)` : '#1e293b',
            padding: '24px',
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'space-between',
          }}
        >
          <Badge
            style={{
              background: cover?.badgeBg || 'rgba(0,0,0,0.5)',
              border: `1px solid ${cover?.badgeBorder || 'transparent'}`,
              color: '#ffffff',
              fontSize: '12px',
              fontWeight: 600,
              backdropFilter: 'blur(8px)',
            }}
          >
            {genre}
          </Badge>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ffffff', fontSize: '13px', background: 'rgba(0,0,0,0.4)', padding: '4px 10px', borderRadius: '16px', backdropFilter: 'blur(4px)' }}>
            <Layers size={14} />
            <span>Phiên bản v{project.version}</span>
          </div>
        </div>

        <div style={{ padding: '24px' }}>
          <h1 style={{ margin: '0 0 10px 0', fontSize: '26px', fontWeight: 800 }}>
            {project.name}
          </h1>
          <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: 'var(--text-muted, #94a3b8)', lineHeight: 1.6, maxWidth: '800px' }}>
            {project.description || 'Chưa có mô tả chi tiết cho dự án.'}
          </p>

          <div style={{ display: 'flex', alignItems: 'center', gap: '24px', fontSize: '13px', color: 'var(--text-muted, #64748b)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Film size={14} />
              <span>{episodes.length} tập phim</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Clock size={14} />
              <span>Tạo ngày: {new Date(project.created_at).toLocaleDateString('vi-VN')}</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Episodes Section */}
      <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700 }}>Danh sách tập phim ({episodes.length})</h2>
          <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)' }}>
            Các tập phim trong dự án cùng trạng thái kịch bản và tiến trình sản xuất
          </span>
        </div>
      </div>

      {episodes.length === 0 ? (
        <Card style={{ padding: '48px 24px', textAlign: 'center', background: 'var(--bg-panel, #0f172a)', border: '1px dashed rgba(255,255,255,0.1)' }}>
          <Film size={32} style={{ color: '#64748b', margin: '0 auto 12px' }} />
          <h3 style={{ margin: '0 0 6px 0', fontSize: '16px', fontWeight: 600 }}>Dự án chưa có tập phim nào</h3>
          <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#94a3b8' }}>
            Hãy thêm tập đầu tiên để bắt đầu xây dựng cốt truyện và kịch bản phim.
          </p>
          <Button variant="primary" onClick={() => setIsCreateEpisodeOpen(true)}>
            <Plus size={14} style={{ marginRight: '6px' }} />
            Tạo tập đầu tiên
          </Button>
        </Card>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {episodes.map((ep: EpisodeResource) => (
            <Card
              key={ep.id}

              interactive
              onClick={() => handleOpenEpisode(ep.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '16px 20px',
                borderRadius: '12px',
                background: 'var(--bg-panel, #0f172a)',
                border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
                cursor: 'pointer',
              }}
              data-testid={`episode-row-${ep.id}`}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div
                  style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '8px',
                    background: 'rgba(59, 130, 246, 0.12)',
                    color: '#3b82f6',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 700,
                    fontSize: '14px',
                  }}
                >
                  {ep.episode_number}
                </div>

                <div>
                  <h3 style={{ margin: '0 0 4px 0', fontSize: '15px', fontWeight: 700 }}>
                    {ep.title}
                  </h3>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted, #64748b)' }}>
                    Cập nhật: {new Date(ep.updated_at).toLocaleDateString('vi-VN')}
                  </span>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <Badge
                  style={{
                    background:
                      ep.state === 'LOCKED'
                        ? 'rgba(34, 197, 94, 0.15)'
                        : ep.state === 'SCREENPLAY'
                        ? 'rgba(168, 85, 247, 0.15)'
                        : 'rgba(59, 130, 246, 0.15)',
                    color:
                      ep.state === 'LOCKED'
                        ? '#4ade80'
                        : ep.state === 'SCREENPLAY'
                        ? '#c084fc'
                        : '#60a5fa',
                    border: '1px solid currentColor',
                    fontSize: '11px',
                    fontWeight: 600,
                  }}
                >
                  {ep.state || 'DRAFT'}
                </Badge>

                <div style={{ color: 'var(--color-primary, #3b82f6)', display: 'flex', alignItems: 'center' }}>
                  <ChevronRight size={16} />
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Episode Dialog */}
      <CreateEpisodeDialog
        isOpen={isCreateEpisodeOpen}
        projectId={project.id}
        projectName={project.name}
        nextEpisodeNumber={episodes.length + 1}
        onClose={() => setIsCreateEpisodeOpen(false)}
        onSubmit={async (input) => {
          await createEpisode(input);
          invalidate();
          refetch();
        }}
      />
    </div>
  );
};
