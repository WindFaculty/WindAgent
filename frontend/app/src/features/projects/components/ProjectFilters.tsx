/**
 * ProjectFilters — Search bar, genre pills, and grid/list view switcher.
 */

import React from 'react';
import { Search, Grid, List, Plus, Sparkles, RefreshCw } from 'lucide-react';
import { Button, Input } from '@windagent/ui';

export interface ProjectFiltersProps {
  search: string;
  onSearchChange: (search: string) => void;
  genre: string;
  onGenreChange: (genre: string) => void;
  viewMode: 'grid' | 'list';
  onViewModeChange: (mode: 'grid' | 'list') => void;
  onCreateProject: () => void;
  onOpenTemplates: () => void;
  onRefresh: () => void;
  isLoading?: boolean;
}

const GENRES = [
  { id: 'all', label: 'Tất cả thể loại' },
  { id: 'Cyberpunk / Sci-Fi', label: 'Cyberpunk / Sci-Fi' },
  { id: 'High Fantasy / Adventure', label: 'High Fantasy' },
  { id: 'Drama / Mystery Noir', label: 'Mystery Noir' },
  { id: 'Animation / Epic Saga', label: 'Animation / Anime' },
];

export const ProjectFilters: React.FC<ProjectFiltersProps> = ({
  search,
  onSearchChange,
  genre,
  onGenreChange,
  viewMode,
  onViewModeChange,
  onCreateProject,
  onOpenTemplates,
  onRefresh,
  isLoading,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
      {/* Top Search & Actions Row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: '280px' }}>
          <div style={{ position: 'relative', flex: 1 }}>
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
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Tìm kiếm dự án theo tên hoặc mô tả..."
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
            onClick={onRefresh}
            disabled={isLoading}
            style={{ padding: '8px 12px' }}
            title="Làm mới danh sách"
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          </Button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Grid / List Switcher */}
          <div
            style={{
              display: 'flex',
              background: 'var(--bg-panel, #0f172a)',
              borderRadius: '8px',
              padding: '2px',
              border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.1))',
            }}
          >
            <button
              onClick={() => onViewModeChange('grid')}
              style={{
                padding: '6px 10px',
                background: viewMode === 'grid' ? 'var(--color-primary, #3b82f6)' : 'transparent',
                color: viewMode === 'grid' ? '#ffffff' : 'var(--text-muted, #94a3b8)',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
              title="Xem dạng lưới"
            >
              <Grid size={15} />
            </button>
            <button
              onClick={() => onViewModeChange('list')}
              style={{
                padding: '6px 10px',
                background: viewMode === 'list' ? 'var(--color-primary, #3b82f6)' : 'transparent',
                color: viewMode === 'list' ? '#ffffff' : 'var(--text-muted, #94a3b8)',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
              title="Xem dạng danh sách"
            >
              <List size={15} />
            </button>
          </div>

          <Button
            variant="secondary"
            onClick={onOpenTemplates}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              background: 'rgba(56, 189, 248, 0.12)',
              color: '#38bdf8',
              border: '1px solid rgba(56, 189, 248, 0.3)',
            }}
          >
            <Sparkles size={15} />
            <span>Mẫu AI Starter</span>
          </Button>

          <Button
            variant="primary"
            onClick={onCreateProject}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Plus size={16} />
            <span>Tạo dự án mới</span>
          </Button>
        </div>
      </div>

      {/* Genre Pills */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflowX: 'auto', paddingBottom: '4px' }}>
        {GENRES.map((g) => {
          const active = genre === g.id;
          return (
            <button
              key={g.id}
              onClick={() => onGenreChange(g.id)}
              style={{
                padding: '6px 14px',
                borderRadius: '20px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.2s',
                whiteSpace: 'nowrap',
                border: active
                  ? '1px solid var(--color-primary, #3b82f6)'
                  : '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
                background: active
                  ? 'rgba(59, 130, 246, 0.15)'
                  : 'var(--bg-panel, #0f172a)',
                color: active
                  ? 'var(--color-primary, #3b82f6)'
                  : 'var(--text-muted, #94a3b8)',
              }}
            >
              {g.label}
            </button>
          );
        })}
      </div>
    </div>
  );
};
