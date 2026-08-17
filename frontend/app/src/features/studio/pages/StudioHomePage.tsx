/**
 * StudioHomePage — Unified Studio Landing Surface (Phase 7 Convergence).
 * Displays recent projects, pipeline summary, quick actions, and capabilities.
 * 100% route-driven and TanStack Query backed.
 */


import React, { useState } from 'react';
import {
  Film,
  Sparkles,
  Folder,
  Plus,
  ArrowRight,
  Activity,
} from 'lucide-react';

import { useRouter } from '../../../app/router';
import { useProjects } from '../../projects/hooks/useProjects';
import { useCreateProject } from '../../projects/hooks/useCreateProject';
import { useProjectTemplates } from '../../projects/hooks/useProjectTemplates';
import { useCapabilities } from '../../projects/hooks/useCapabilities';
import { CreateProjectDialog } from '../../projects/components/CreateProjectDialog';
import { ProjectTemplatePicker } from '../../projects/components/ProjectTemplatePicker';
import { ProjectCard } from '../../projects/components/ProjectCard';
import type { ProjectTemplate } from '@windagent/api-contracts';
import { Button, Card, Badge } from '@windagent/ui';

export const StudioHomePage: React.FC = () => {
  const { navigate } = useRouter();
  const { projects, isLoading: isProjectsLoading } = useProjects({ limit: 4 });
  const { isReady, status: capabilityStatus } = useCapabilities();
  const { templates } = useProjectTemplates();
  const { createProject } = useCreateProject();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isTemplatesOpen, setIsTemplatesOpen] = useState(false);
  const [templateData, setTemplateData] = useState<any>(undefined);

  const handleOpenProject = (projectId: string) => {
    navigate(`/projects/${projectId}`);
  };

  const handleSelectTemplate = (tmpl: ProjectTemplate) => {
    setTemplateData({
      name: tmpl.title,
      description: tmpl.description,
      genre: tmpl.genre,
      initial_episode_title: tmpl.initial_episode,
    });
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
      data-testid="canonical-studio-home-page"
    >
      {/* Hero Welcome Banner */}
      <div
        style={{
          borderRadius: '20px',
          padding: '36px',
          background: 'linear-gradient(135deg, rgba(30, 58, 138, 0.4) 0%, rgba(15, 23, 42, 0.9) 100%)',
          border: '1px solid rgba(59, 130, 246, 0.2)',
          marginBottom: '32px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '24px',
          flexWrap: 'wrap',
          boxShadow: '0 20px 40px -15px rgba(0, 0, 0, 0.4)',
        }}
      >
        <div style={{ maxWidth: '640px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <Badge
              style={{
                background: isReady ? 'rgba(34, 197, 94, 0.15)' : 'rgba(234, 179, 8, 0.15)',
                color: isReady ? '#4ade80' : '#facc15',
                border: `1px solid ${isReady ? '#4ade80' : '#facc15'}`,
                fontSize: '11px',
                fontWeight: 600,
              }}
            >
              STUDIO V3 CANONICAL
            </Badge>
            <span style={{ fontSize: '13px', color: '#94a3b8' }}>
              Trạng thái hệ thống: {capabilityStatus}
            </span>
          </div>

          <h1 style={{ margin: '0 0 12px 0', fontSize: '32px', fontWeight: 800, letterSpacing: '-0.5px' }}>
            Xưởng Phim & Sản Xuất AI Tự Động
          </h1>
          <p style={{ margin: 0, fontSize: '15px', color: '#cbd5e1', lineHeight: 1.6 }}>
            Khởi tạo các dự án điện ảnh, điều phối dàn tác giả AI chuyên sâu và theo dõi tiến trình
            sản xuất kịch bản, storyboard và video một cách liền mạch.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Button
            variant="outline"
            onClick={() => setIsTemplatesOpen(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '10px 18px',
              borderColor: 'rgba(255, 255, 255, 0.2)',
            }}
          >
            <Sparkles size={16} color="#38bdf8" />
            <span>Mẫu AI Starter</span>
          </Button>

          <Button
            variant="primary"
            onClick={() => {
              setTemplateData(undefined);
              setIsCreateOpen(true);
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '10px 20px',
              fontWeight: 600,
            }}
          >
            <Plus size={16} />
            <span>Tạo dự án mới</span>
          </Button>
        </div>
      </div>

      {/* Quick Access Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '16px',
          marginBottom: '36px',
        }}
      >
        <Card
          interactive
          onClick={() => navigate('/projects')}
          style={{
            padding: '20px',
            borderRadius: '14px',
            background: 'var(--bg-panel, #0f172a)',
            border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            cursor: 'pointer',
          }}
        >
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '10px',
              background: 'rgba(59, 130, 246, 0.15)',
              color: '#3b82f6',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Folder size={22} />
          </div>
          <div>
            <h3 style={{ margin: '0 0 4px 0', fontSize: '15px', fontWeight: 700 }}>Dự Án Phim</h3>
            <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)' }}>
              Xem toàn bộ dự án
            </span>
          </div>
        </Card>

        <Card
          interactive
          onClick={() => navigate('/production/script')}
          style={{
            padding: '20px',
            borderRadius: '14px',
            background: 'var(--bg-panel, #0f172a)',
            border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            cursor: 'pointer',
          }}
        >
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '10px',
              background: 'rgba(168, 85, 247, 0.15)',
              color: '#c084fc',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Film size={22} />
          </div>
          <div>
            <h3 style={{ margin: '0 0 4px 0', fontSize: '15px', fontWeight: 700 }}>Production Workspace</h3>
            <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)' }}>
              Biên kịch & duyệt phân đoạn
            </span>
          </div>
        </Card>

        <Card
          interactive
          onClick={() => navigate('/monitoring')}
          style={{
            padding: '20px',
            borderRadius: '14px',
            background: 'var(--bg-panel, #0f172a)',
            border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            cursor: 'pointer',
          }}
        >
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '10px',
              background: 'rgba(34, 197, 94, 0.15)',
              color: '#4ade80',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Activity size={22} />
          </div>
          <div>
            <h3 style={{ margin: '0 0 4px 0', fontSize: '15px', fontWeight: 700 }}>Hạ Tầng & Workers</h3>
            <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)' }}>
              Giám sát tài nguyên máy chủ
            </span>
          </div>
        </Card>
      </div>

      {/* Recent Projects Section */}
      <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700 }}>Dự Án Gần Đây</h2>
          <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)' }}>
            Các kịch bản phim đang thực hiện trong studio
          </span>
        </div>

        <Button variant="ghost" onClick={() => navigate('/projects')} style={{ color: 'var(--color-primary, #3b82f6)' }}>
          <span>Xem tất cả</span>
          <ArrowRight size={14} style={{ marginLeft: '4px' }} />
        </Button>
      </div>

      {projects.length === 0 && !isProjectsLoading ? (
        <Card style={{ padding: '36px', textAlign: 'center', background: 'var(--bg-panel, #0f172a)' }}>
          <Folder size={28} style={{ color: '#64748b', margin: '0 auto 8px' }} />
          <p style={{ margin: 0, fontSize: '14px', color: '#94a3b8' }}>Chưa có dự án nào gần đây.</p>
        </Card>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: '20px',
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

      {/* Create Project Dialog */}
      <CreateProjectDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={async (input) => {
          const res = await createProject(input);
          navigate(`/projects/${res.id}`);
        }}
        initialData={templateData}
      />

      {/* Templates Picker Dialog */}
      <ProjectTemplatePicker
        isOpen={isTemplatesOpen}
        templates={templates}
        onClose={() => setIsTemplatesOpen(false)}
        onSelectTemplate={handleSelectTemplate}
      />
    </div>
  );
};
