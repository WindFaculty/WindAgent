/**
 * Canonical EpisodesPage — Catalog of all episodes across projects (Phase 8 Cutover).
 * Zero DEFAULT_EPISODES, zero local mutations, 100% server authority via TanStack Query.
 */

import React, { useState } from 'react';
import { Film, Search, RefreshCw, AlertCircle } from 'lucide-react';
import { useRouter } from '../../../app/router';

import { useEpisodes } from '../hooks/useEpisodes';
import { EpisodeCard } from '../components/EpisodeCard';
import { Button, Input, Card } from '@windagent/ui';

const STATE_FILTERS = [
  { id: 'ALL', label: 'Tất cả trạng thái' },
  { id: 'DRAFT', label: 'Bản nháp' },
  { id: 'IDEA', label: 'Ý tưởng' },
  { id: 'STORY_BIBLE', label: 'Story Bible' },
  { id: 'OUTLINE', label: 'Dàn ý' },
  { id: 'SCREENPLAY', label: 'Kịch bản' },
  { id: 'LOCKED', label: 'Đã khóa (Sản xuất)' },
];

export const EpisodesPage: React.FC = () => {
  const { navigate } = useRouter();
  const [search, setSearch] = useState('');
  const [stateFilter, setStateFilter] = useState('ALL');

  const { episodes, isLoading, isError, error, refetch, invalidate } = useEpisodes({
    search: search.trim() || undefined,
    state: stateFilter !== 'ALL' ? stateFilter : undefined,
  });

  const handleOpenEpisode = (episodeId: string) => {
    navigate(`/studio/episodes/${episodeId}`);
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
      data-testid="canonical-episodes-catalog-page"
    >
      {/* Header */}
      <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <Film size={24} color="var(--color-primary, #3b82f6)" />
            <h1 style={{ margin: 0, fontSize: '28px', fontWeight: 800, letterSpacing: '-0.5px' }}>
              Danh Sách Tập Phim (Episodes)
            </h1>
          </div>
          <p style={{ margin: 0, fontSize: '14px', color: 'var(--text-muted, #94a3b8)' }}>
            Toàn bộ các tập phim trong mọi dự án studio cùng trạng thái kịch bản và tiến độ sản xuất
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Button variant="outline" onClick={() => navigate('/projects')}>
            Xem theo Dự án
          </Button>
        </div>
      </div>

      {/* Filter Row */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: '280px' }}>
            <Search
              size={16}
              style={{
                position: 'absolute',
                left: '12px',
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--text-muted, #94a3b8)',
                pointerEvents: 'none',
              }}
            />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm kiếm tập phim theo tên, dự án hoặc tóm tắt..."
              style={{
                paddingLeft: '36px',
                background: 'var(--bg-panel, #0f172a)',
                borderColor: 'var(--border-subtle, rgba(255, 255, 255, 0.1))',
                width: '100%',
              }}
            />
          </div>

          <Button
            variant="outline"
            onClick={() => {
              invalidate();
              refetch();
            }}
            disabled={isLoading}
            title="Làm mới danh sách"
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          </Button>
        </div>

        {/* State Filter Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflowX: 'auto', paddingBottom: '4px' }}>
          {STATE_FILTERS.map((s) => {
            const active = stateFilter === s.id;
            return (
              <button
                key={s.id}
                onClick={() => setStateFilter(s.id)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '20px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  border: active
                    ? '1px solid var(--color-primary, #3b82f6)'
                    : '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
                  background: active ? 'rgba(59, 130, 246, 0.15)' : 'var(--bg-panel, #0f172a)',
                  color: active ? 'var(--color-primary, #3b82f6)' : 'var(--text-muted, #94a3b8)',
                }}
              >
                {s.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Error state */}
      {isError && (
        <Card style={{ padding: '24px', marginBottom: '24px', background: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: '#f87171' }}>
            <AlertCircle size={20} />
            <div>
              <strong>Lỗi tải danh sách tập phim:</strong> {error?.message || 'Không thể kết nối đến máy chủ.'}
            </div>
          </div>
        </Card>
      )}

      {/* Loading Skeleton */}
      {isLoading && episodes.length === 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              style={{
                height: '240px',
                borderRadius: '14px',
                background: 'var(--bg-panel, #0f172a)',
                animation: 'pulse 1.5s infinite',
                border: '1px solid rgba(255, 255, 255, 0.05)',
              }}
            />
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && episodes.length === 0 && (
        <Card style={{ padding: '64px 32px', textAlign: 'center', background: 'var(--bg-panel, #0f172a)', border: '1px dashed rgba(255, 255, 255, 0.15)', borderRadius: '16px' }}>
          <Film size={32} style={{ color: '#64748b', margin: '0 auto 12px' }} />
          <h3 style={{ margin: '0 0 8px 0', fontSize: '18px', fontWeight: 700 }}>
            {search ? 'Không tìm thấy tập phim phù hợp' : 'Chưa có tập phim nào'}
          </h3>
          <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: 'var(--text-muted, #94a3b8)', maxWidth: '440px', marginLeft: 'auto', marginRight: 'auto' }}>
            Mở một dự án trong danh sách dự án để tạo các tập phim mới.
          </p>
          <Button variant="primary" onClick={() => navigate('/projects')}>
            Duyệt danh sách dự án
          </Button>
        </Card>
      )}

      {/* Episodes Grid */}
      {!isLoading && episodes.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '20px' }}>
          {episodes.map((ep: any) => (
            <EpisodeCard
              key={ep.id}
              episode={ep}
              onOpen={handleOpenEpisode}
            />
          ))}
        </div>
      )}
    </div>
  );
};
