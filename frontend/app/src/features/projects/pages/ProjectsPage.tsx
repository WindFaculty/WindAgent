/**
 * ProjectsPage — AI Film Studio cinematic redesign (matches Image 1 mock).
 * Header + dual CTA + toolbar + stats bar + 3-col cinematic grid.
 */

import React, { useState, useMemo } from 'react';
import { Plus, Sparkles, AlertCircle, Upload } from 'lucide-react';

import { useRouter } from '../../../app/router';

import { useProjects } from '../hooks/useProjects';
import { useCreateProject } from '../hooks/useCreateProject';
import { useProjectTemplates } from '../hooks/useProjectTemplates';
import { ProjectCard } from '../components/ProjectCard';
import { ProjectList } from '../components/ProjectList';
import { ProjectFilters } from '../components/ProjectFilters';
import { ProjectStatsBar, computeProjectStats } from '../components/ProjectStatsBar';
import { CreateProjectDialog } from '../components/CreateProjectDialog';
import { ProjectTemplatePicker } from '../components/ProjectTemplatePicker';
import type { ProjectTemplate } from '@windagent/api-contracts';
import { Button, Card } from '@windagent/ui';

export const ProjectsPage: React.FC = () => {
  const { navigate } = useRouter();
  const [search, setSearch] = useState('');
  const [genre, setGenre] = useState('all');
  const [status, setStatus] = useState('all');
  const [sort, setSort] = useState('updated');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isTemplatesOpen, setIsTemplatesOpen] = useState(false);
  const [templateInitialData, setTemplateInitialData] = useState<{
    name?: string;
    description?: string;
    genre?: string;
    initial_episode_title?: string;
  } | undefined>(undefined);

  const { projects, isLoading, isError, error, refetch, invalidate } = useProjects({
    search: search.trim() || undefined,
    genre: genre !== 'all' ? genre : undefined,
  });

  const { createProject } = useCreateProject();
  const { templates } = useProjectTemplates();

  const handleOpenProject = (projectId: string) => {
    navigate(`/projects/${projectId}`);
  };

  const handleSelectTemplate = (tmpl: ProjectTemplate) => {
    setTemplateInitialData({
      name: tmpl.title,
      description: tmpl.description,
      genre: tmpl.genre,
      initial_episode_title: tmpl.initial_episode,
    });
    setIsCreateOpen(true);
  };

  const handleOpenNewProject = () => {
    setTemplateInitialData(undefined);
    setIsCreateOpen(true);
  };

  // Stats derived from real API data (episode states + DB timestamps)
  const stats = useMemo(
    () => computeProjectStats(projects),
    [projects],
  );

  // Genre filter options built from real project metadata
  const availableGenres = useMemo(() => {
    const set = new Set<string>();
    for (const p of projects) {
      const g = p.metadata?.genre as string | undefined;
      if (g) set.add(g);
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b, 'vi'));
  }, [projects]);

  // Filtered + sorted list (status + sort extra on top of search/genre already filtered by hook)
  const displayProjects = useMemo(() => {
    let list = [...projects];
    if (status !== 'all') {
      list = list.filter((p) => p.derived_status === status);
    }
    if (sort === 'name') {
      list.sort((a, b) => a.name.localeCompare(b.name, 'vi'));
    } else if (sort === 'episodes') {
      list.sort((a, b) => (b.episodes_count ?? 0) - (a.episodes_count ?? 0));
    } else {
      // updated — newest first
      list.sort((a, b) => new Date(b.updated_at || 0).getTime() - new Date(a.updated_at || 0).getTime());
    }
    return list;
  }, [projects, status, sort]);

  return (
    <div
      style={{
        minHeight: '100%',
        background: 'var(--bg-darker, #060e20)',
        color: 'var(--text-primary, #f8fafc)',
        padding: '20px 24px 32px 24px',
      }}
      data-testid="canonical-projects-page"
    >
      <div style={{ maxWidth: '1440px', margin: '0 auto' }}>
        {/* Header: Title + CTAs */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: '16px',
            marginBottom: '18px',
            flexWrap: 'wrap',
          }}
        >
          <div>
            <h1
              style={{
                margin: 0,
                fontSize: '26px',
                fontWeight: 850,
                letterSpacing: '-0.6px',
                color: '#f1f5f9',
                lineHeight: 1.2,
              }}
            >
              Projects
            </h1>
            <p style={{ margin: '6px 0 0 0', fontSize: '13px', color: '#94a3b8', fontWeight: 450 }}>
              Quản lý và theo dõi toàn bộ dự án phim AI của bạn
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={() => {
                // placeholder — upcoming import feature
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '7px',
                padding: '9px 14px',
                borderRadius: '10px',
                background: 'transparent',
                border: '1px solid rgba(255,255,255,0.12)',
                color: '#cbd5e1',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              <Upload size={14} />
              Import Project
            </button>
            <button
              onClick={handleOpenNewProject}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '7px',
                padding: '9px 16px',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #2563eb 0%, #7c3aed 100%)',
                border: '1px solid rgba(255,255,255,0.10)',
                color: '#ffffff',
                fontSize: '13px',
                fontWeight: 700,
                cursor: 'pointer',
                boxShadow: '0 8px 24px rgba(37,99,235,0.35), 0 0 0 1px rgba(255,255,255,0.06) inset',
                whiteSpace: 'nowrap',
              }}
            >
              <Plus size={15} />
              Tạo dự án mới
            </button>
          </div>
        </div>

        {/* Toolbar */}
        <ProjectFilters
          search={search}
          onSearchChange={setSearch}
          genre={genre}
          onGenreChange={setGenre}
          genres={availableGenres}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          onCreateProject={handleOpenNewProject}
          onOpenTemplates={() => setIsTemplatesOpen(true)}
          onRefresh={() => {
            invalidate();
            refetch();
          }}
          isLoading={isLoading}
          status={status}
          onStatusChange={setStatus}
          sort={sort}
          onSortChange={setSort}
        />

        {/* Stats bar */}
        <ProjectStatsBar stats={stats} />

        {/* Error */}
        {isError && (
          <Card
            style={{
              padding: '16px 20px',
              marginBottom: '16px',
              background: 'rgba(239, 68, 68, 0.08)',
              borderColor: 'rgba(239, 68, 68, 0.25)',
              borderRadius: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#f87171', fontSize: '13px' }}>
              <AlertCircle size={18} />
              <div>
                <strong>Lỗi tải danh sách dự án:</strong> {error?.message || 'Không thể kết nối đến máy chủ.'}
              </div>
            </div>
          </Card>
        )}

        {/* Loading */}
        {isLoading && projects.length === 0 && (
          <div
            className="projects-grid"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
              gap: '16px',
            }}
          >
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div
                key={i}
                style={{
                  height: '320px',
                  borderRadius: '16px',
                  background: '#131b2e',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                  animation: 'pulse 1.4s infinite',
                }}
              />
            ))}
          </div>
        )}

        {/* Empty */}
        {!isLoading && displayProjects.length === 0 && projects.length === 0 && (
          <Card
            style={{
              padding: '56px 32px',
              textAlign: 'center',
              background: '#131b2e',
              border: '1px dashed rgba(255, 255, 255, 0.12)',
              borderRadius: '16px',
            }}
          >
            <div
              style={{
                width: '56px',
                height: '56px',
                borderRadius: '16px',
                background: 'rgba(59, 130, 246, 0.12)',
                color: '#3b82f6',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 14px auto',
              }}
            >
              <Sparkles size={26} />
            </div>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '17px', fontWeight: 750, color: '#f1f5f9' }}>
              {search ? 'Không tìm thấy dự án phù hợp' : 'Chưa có dự án nào'}
            </h3>
            <p
              style={{
                margin: '0 0 18px 0',
                fontSize: '13px',
                color: '#94a3b8',
                maxWidth: '460px',
                marginLeft: 'auto',
                marginRight: 'auto',
                lineHeight: 1.6,
              }}
            >
              {search
                ? `Không có dự án nào khớp với từ khóa "${search}". Hãy thử tìm kiếm với cụm từ khác.`
                : 'Hãy bắt đầu bằng cách tạo dự án đầu tiên hoặc chọn từ các mẫu kịch bản AI có sẵn.'}
            </p>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <Button variant="outline" onClick={() => setIsTemplatesOpen(true)} style={{ borderRadius: '10px' }}>
                <Sparkles size={14} style={{ marginRight: '6px' }} />
                Duyệt mẫu có sẵn
              </Button>
              <Button
                variant="primary"
                onClick={handleOpenNewProject}
                style={{
                  borderRadius: '10px',
                  background: 'linear-gradient(135deg, #2563eb 0%, #7c3aed 100%)',
                }}
              >
                <Plus size={14} style={{ marginRight: '6px' }} />
                Tạo dự án mới
              </Button>
            </div>
          </Card>
        )}

        {/* Filtered empty */}
        {!isLoading && displayProjects.length === 0 && projects.length > 0 && (
          <Card
            style={{
              padding: '32px',
              textAlign: 'center',
              background: '#131b2e',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: '16px',
            }}
          >
            <p style={{ margin: 0, fontSize: '13px', color: '#94a3b8' }}>
              Không có dự án nào khớp với bộ lọc hiện tại. Thử đổi Trạng thái hoặc Thể loại.
            </p>
          </Card>
        )}

        {/* Grid */}
        {!isLoading && displayProjects.length > 0 && viewMode === 'grid' && (
          <div
            className="projects-grid"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
              gap: '16px',
            }}
          >
            {displayProjects.map((project) => (
              <ProjectCard key={project.id} project={project} onOpen={handleOpenProject} />
            ))}
          </div>
        )}

        {/* List */}
        {!isLoading && displayProjects.length > 0 && viewMode === 'list' && (
          <ProjectList projects={displayProjects} onOpen={handleOpenProject} />
        )}

        {/* Create dialog */}
        <CreateProjectDialog
          isOpen={isCreateOpen}
          onClose={() => setIsCreateOpen(false)}
          onSubmit={async (input) => {
            const res = await createProject(input);
            navigate(`/projects/${res.id}`);
          }}
          initialData={templateInitialData}
        />

        <ProjectTemplatePicker
          isOpen={isTemplatesOpen}
          templates={templates}
          onClose={() => setIsTemplatesOpen(false)}
          onSelectTemplate={handleSelectTemplate}
        />
      </div>

      <style>{`
        .projects-grid { grid-template-columns: repeat(3, minmax(0,1fr)); }
        .stats-grid { grid-template-columns: repeat(4, minmax(0,1fr)); }
        @media (max-width: 1100px) {
          .projects-grid { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
          .stats-grid { grid-template-columns: repeat(2, minmax(0,1fr)) !important; }
        }
        @media (max-width: 640px) {
          .projects-grid { grid-template-columns: 1fr !important; }
          .stats-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </div>
  );
};
