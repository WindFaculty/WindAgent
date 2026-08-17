/**
 * Canonical ProjectsPage — Complete project catalog with search, filter, and template picker.
 */

import React, { useState } from 'react';
import { Folder, Plus, Sparkles, AlertCircle } from 'lucide-react';

import { useRouter } from '../../../app/router';

import { useProjects } from '../hooks/useProjects';
import { useCreateProject } from '../hooks/useCreateProject';
import { useProjectTemplates } from '../hooks/useProjectTemplates';
import { ProjectCard } from '../components/ProjectCard';
import { ProjectList } from '../components/ProjectList';
import { ProjectFilters } from '../components/ProjectFilters';
import { CreateProjectDialog } from '../components/CreateProjectDialog';
import { ProjectTemplatePicker } from '../components/ProjectTemplatePicker';
import type { ProjectTemplate } from '@windagent/api-contracts';
import { Button, Card } from '@windagent/ui';

export const ProjectsPage: React.FC = () => {
  const { navigate } = useRouter();
  const [search, setSearch] = useState('');
  const [genre, setGenre] = useState('all');
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

  return (
    <div
      style={{
        padding: '32px',
        maxWidth: '1440px',
        margin: '0 auto',
        minHeight: '100%',
        color: 'var(--text-primary, #f8fafc)',
      }}
      data-testid="canonical-projects-page"
    >
      {/* Header */}
      <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <Folder size={24} color="var(--color-primary, #3b82f6)" />
            <h1 style={{ margin: 0, fontSize: '28px', fontWeight: 800, letterSpacing: '-0.5px' }}>
              Dự Án Sản Xuất Phim
            </h1>
          </div>
          <p style={{ margin: 0, fontSize: '14px', color: 'var(--text-muted, #94a3b8)' }}>
            Quản lý kịch bản, các tập phim và tiến trình đa agent trong studio sản xuất
          </p>
        </div>
      </div>

      {/* Filter Bar */}
      <ProjectFilters
        search={search}
        onSearchChange={setSearch}
        genre={genre}
        onGenreChange={setGenre}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        onCreateProject={handleOpenNewProject}
        onOpenTemplates={() => setIsTemplatesOpen(true)}
        onRefresh={() => {
          invalidate();
          refetch();
        }}
        isLoading={isLoading}
      />

      {/* Error state */}
      {isError && (
        <Card style={{ padding: '24px', marginBottom: '24px', background: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: '#f87171' }}>
            <AlertCircle size={20} />
            <div>
              <strong>Lỗi tải danh sách dự án:</strong> {error?.message || 'Không thể kết nối đến máy chủ.'}
            </div>
          </div>
        </Card>
      )}

      {/* Loading Skeleton */}
      {isLoading && projects.length === 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: '20px',
          }}
        >
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              style={{
                height: '300px',
                borderRadius: '16px',
                background: 'var(--bg-panel, #0f172a)',
                animation: 'pulse 1.5s infinite',
                border: '1px solid rgba(255, 255, 255, 0.05)',
              }}
            />
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && projects.length === 0 && (
        <Card
          style={{
            padding: '64px 32px',
            textAlign: 'center',
            background: 'var(--bg-panel, #0f172a)',
            border: '1px dashed rgba(255, 255, 255, 0.15)',
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
              margin: '0 auto 16px auto',
            }}
          >
            <Folder size={28} />
          </div>
          <h3 style={{ margin: '0 0 8px 0', fontSize: '18px', fontWeight: 700 }}>
            {search ? 'Không tìm thấy dự án phù hợp' : 'Chưa có dự án nào'}
          </h3>
          <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: 'var(--text-muted, #94a3b8)', maxWidth: '440px', marginLeft: 'auto', marginRight: 'auto' }}>
            {search
              ? `Không có dự án nào khớp với từ khóa "${search}". Hãy thử tìm kiếm với cụm từ khác.`
              : 'Hãy bắt đầu bằng cách tạo dự án đầu tiên hoặc chọn từ các mẫu kịch bản AI có sẵn.'}
          </p>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px' }}>
            <Button variant="outline" onClick={() => setIsTemplatesOpen(true)}>
              <Sparkles size={15} style={{ marginRight: '6px' }} />
              Duyệt mẫu có sẵn
            </Button>
            <Button variant="primary" onClick={handleOpenNewProject}>
              <Plus size={15} style={{ marginRight: '6px' }} />
              Tạo dự án mới
            </Button>
          </div>
        </Card>
      )}

      {/* Grid View */}
      {!isLoading && projects.length > 0 && viewMode === 'grid' && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
            gap: '24px',
          }}
        >
          {projects.map((project: any) => (
            <ProjectCard
              key={project.id}

              project={project}
              onOpen={handleOpenProject}
            />
          ))}
        </div>
      )}

      {/* List View */}
      {!isLoading && projects.length > 0 && viewMode === 'list' && (
        <ProjectList
          projects={projects}
          onOpen={handleOpenProject}
        />
      )}

      {/* Create Project Modal */}
      <CreateProjectDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={async (input) => {
          const res = await createProject(input);
          navigate(`/projects/${res.id}`);
        }}
        initialData={templateInitialData}
      />

      {/* Templates Picker Modal */}
      <ProjectTemplatePicker
        isOpen={isTemplatesOpen}
        templates={templates}
        onClose={() => setIsTemplatesOpen(false)}
        onSelectTemplate={handleSelectTemplate}
      />
    </div>
  );
};
