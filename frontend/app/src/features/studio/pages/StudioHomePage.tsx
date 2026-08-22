/**
 * StudioHomePage — Unified Series-Domain Studio Landing Surface (P0.7 Convergence).
 * Displays live truthful metrics: Active Series, In Progress, Pending Approval, Ready for Production.
 * 100% route-driven and TanStack Query backed by canonical Studio V3 authority.
 */

import React, { useState } from 'react';
import {
  Film,
  Sparkles,
  Folder,
  Plus,
  ArrowRight,
  Activity,
  CheckCircle2,
  Clock,
  ShieldCheck,
  Server,
} from 'lucide-react';

import { useRouter } from '../../../app/router';
import { useStudioSeries } from '../hooks/useStudioSeries';
import { useCapabilities } from '../../projects/hooks/useCapabilities';
import { useProjectTemplates } from '../../projects/hooks/useProjectTemplates';
import { CreateSeriesDialog } from '../components/CreateSeriesDialog';
import { ProjectTemplatePicker } from '../../projects/components/ProjectTemplatePicker';
import type { ProjectTemplate, StudioSeriesResource } from '@windagent/api-contracts';
import { Button, Card, Badge } from '@windagent/ui';

export const StudioHomePage: React.FC = () => {
  const { navigate } = useRouter();
  const {
    series,
    metrics,
    isLoading: isSeriesLoading,
    createSeries,
    refetch,
    invalidate,
  } = useStudioSeries();

  const { isReady, status: capabilityStatus } = useCapabilities();
  const { templates } = useProjectTemplates();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isTemplatesOpen, setIsTemplatesOpen] = useState(false);
  const [templateData, setTemplateData] = useState<any>(undefined);

  const handleOpenSeries = (seriesId: string) => {
    navigate(`/projects/${seriesId}`);
  };

  const handleSelectTemplate = (tmpl: ProjectTemplate) => {
    setTemplateData({
      title: tmpl.title,
      description: tmpl.description,
      genre: tmpl.genre,
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
            Khởi tạo Series phim, điều phối dàn tác giả AI chuyên sâu và theo dõi tiến trình
            sản xuất kịch bản, ý tưởng, story bible, dàn ý và screenplay bất biến.
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
            <span>Tạo Series Mới</span>
          </Button>
        </div>
      </div>

      {/* P0.7 — Live Truthful Metrics Authority (No Fake Numbers) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
          marginBottom: '36px',
        }}
        data-testid="studio-home-metrics"
      >
        <Card
          style={{
            padding: '20px',
            borderRadius: '16px',
            background: 'var(--bg-panel, #0f172a)',
            border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
          }}
        >
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'rgba(59, 130, 246, 0.15)',
              color: '#3b82f6',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Folder size={24} />
          </div>
          <div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: '#f8fafc' }}>
              {isSeriesLoading ? '...' : metrics.activeSeries}
            </div>
            <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)', fontWeight: 600 }}>
              Active Series
            </span>
          </div>
        </Card>

        <Card
          style={{
            padding: '20px',
            borderRadius: '16px',
            background: 'var(--bg-panel, #0f172a)',
            border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
          }}
        >
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'rgba(168, 85, 247, 0.15)',
              color: '#c084fc',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Clock size={24} />
          </div>
          <div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: '#f8fafc' }}>
              {isSeriesLoading ? '...' : metrics.episodesInProgress}
            </div>
            <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)', fontWeight: 600 }}>
              Tập Đang Sản Xuất
            </span>
          </div>
        </Card>

        <Card
          style={{
            padding: '20px',
            borderRadius: '16px',
            background: 'var(--bg-panel, #0f172a)',
            border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
          }}
        >
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'rgba(234, 179, 8, 0.15)',
              color: '#facc15',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <ShieldCheck size={24} />
          </div>
          <div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: '#f8fafc' }}>
              {isSeriesLoading ? '...' : metrics.pendingApproval}
            </div>
            <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)', fontWeight: 600 }}>
              Chờ Phê Duyệt
            </span>
          </div>
        </Card>

        <Card
          style={{
            padding: '20px',
            borderRadius: '16px',
            background: 'var(--bg-panel, #0f172a)',
            border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
          }}
        >
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'rgba(34, 197, 94, 0.15)',
              color: '#4ade80',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <CheckCircle2 size={24} />
          </div>
          <div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: '#f8fafc' }}>
              {isSeriesLoading ? '...' : metrics.readyForProduction}
            </div>
            <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)', fontWeight: 600 }}>
              Sẵn Sàng Sản Xuất
            </span>
          </div>
        </Card>
      </div>

      {/* Quick Navigation Cards */}
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
          onClick={() => navigate('/episodes')}
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
            <Film size={22} />
          </div>
          <div>
            <h3 style={{ margin: '0 0 4px 0', fontSize: '15px', fontWeight: 700 }}>Danh Sách Tập Phim</h3>
            <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)' }}>
              Xem toàn bộ các tập phim
            </span>
          </div>
        </Card>

        <Card
          interactive
          onClick={() => navigate('/router')}
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
            <Server size={22} />
          </div>
          <div>
            <h3 style={{ margin: '0 0 4px 0', fontSize: '15px', fontWeight: 700 }}>Cấu Hình Providers & Routing</h3>
            <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)' }}>
              OpenRouter, Gemini, Models & Rules
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

      {/* Active Series Section */}
      <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700 }}>Active Series ({series.length})</h2>
          <span style={{ fontSize: '13px', color: 'var(--text-muted, #94a3b8)' }}>
            Các vũ trụ và kịch bản phim đang thực hiện trong studio
          </span>
        </div>

        <Button variant="ghost" onClick={() => navigate('/projects')} style={{ color: 'var(--color-primary, #3b82f6)' }}>
          <span>Xem tất cả</span>
          <ArrowRight size={14} style={{ marginLeft: '4px' }} />
        </Button>
      </div>

      {series.length === 0 && !isSeriesLoading ? (
        <Card style={{ padding: '48px 32px', textAlign: 'center', background: 'var(--bg-panel, #0f172a)', borderRadius: '16px', border: '1px dashed rgba(255, 255, 255, 0.15)' }}>
          <Folder size={32} style={{ color: '#64748b', margin: '0 auto 12px' }} />
          <h3 style={{ margin: '0 0 8px 0', fontSize: '18px', fontWeight: 700 }}>Chưa có Series phim nào</h3>
          <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: '#94a3b8', maxWidth: '420px', marginLeft: 'auto', marginRight: 'auto' }}>
            Hãy bắt đầu bằng cách tạo Series phim đầu tiên hoặc chọn từ mẫu kịch bản AI có sẵn.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px' }}>
            <Button variant="outline" onClick={() => setIsTemplatesOpen(true)}>
              <Sparkles size={15} style={{ marginRight: '6px' }} />
              Duyệt mẫu có sẵn
            </Button>
            <Button variant="primary" onClick={() => setIsCreateOpen(true)}>
              <Plus size={15} style={{ marginRight: '6px' }} />
              Tạo Series Mới
            </Button>
          </div>
        </Card>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: '20px',
          }}
        >
          {series.map((s: StudioSeriesResource) => {
            const genre = (s.metadata?.genre as string) || 'Sci-Fi';
            const tone = (s.metadata?.tone as string) || 'Cinematic';
            const language = (s.metadata?.language as string) || 'vi';

            return (
              <Card
                key={s.id}
                interactive
                onClick={() => handleOpenSeries(s.id)}
                style={{
                  padding: '24px',
                  borderRadius: '16px',
                  background: 'var(--bg-panel, #0f172a)',
                  border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  minHeight: '200px',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px', flexWrap: 'wrap', gap: '6px' }}>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <Badge style={{ background: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa', fontSize: '11px' }}>
                        {genre}
                      </Badge>
                      <Badge style={{ background: 'rgba(255, 255, 255, 0.08)', color: '#94a3b8', fontSize: '11px' }}>
                        {tone}
                      </Badge>
                    </div>

                    <Badge style={{ background: 'rgba(34, 197, 94, 0.12)', color: '#4ade80', fontSize: '11px' }}>
                      {s.episode_count} Tập
                    </Badge>
                  </div>

                  <h3 style={{ margin: '0 0 8px 0', fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>
                    {s.title}
                  </h3>
                  <p style={{ margin: 0, fontSize: '13px', color: '#cbd5e1', lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {s.description || 'Chưa có mô tả chi tiết cho Series này.'}
                  </p>
                </div>

                <div style={{ marginTop: '20px', paddingTop: '14px', borderTop: '1px solid rgba(255, 255, 255, 0.06)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '12px', color: '#64748b' }}>
                    {language.toUpperCase()} | {new Date(s.created_at).toLocaleDateString('vi-VN')}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--color-primary, #3b82f6)', fontSize: '13px', fontWeight: 600 }}>
                    <span>Mở Series</span>
                    <ArrowRight size={14} />
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Create Series Dialog */}
      <CreateSeriesDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={async (input) => {
          const res = await createSeries(input);
          invalidate();
          refetch();
          if (res?.series_id) {
            navigate(`/projects/${res.series_id}`);
          }
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
