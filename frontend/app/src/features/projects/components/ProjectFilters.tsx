/**
 * ProjectFilters — Toolbar matching AI Film Studio mock: search + 3 selects + view toggle.
 */

import React from 'react';
import { Search, Grid2x2, List, ChevronDown } from 'lucide-react';

export interface ProjectFiltersProps {
  search: string;
  onSearchChange: (search: string) => void;
  genre: string;
  onGenreChange: (genre: string) => void;
  /** Genre options built from real project metadata (dynamic). */
  genres?: string[];
  viewMode: 'grid' | 'list';
  onViewModeChange: (mode: 'grid' | 'list') => void;
  onCreateProject: () => void;
  onOpenTemplates: () => void;
  onRefresh: () => void;
  isLoading?: boolean;
  status?: string;
  onStatusChange?: (status: string) => void;
  sort?: string;
  onSortChange?: (sort: string) => void;
}

const STATUSES = [
  { id: 'all', label: 'Tất cả' },
  { id: 'producing', label: 'Đang sản xuất' },
  { id: 'review', label: 'Trong đánh giá' },
  { id: 'draft', label: 'Bản nháp' },
  { id: 'completed', label: 'Hoàn thành' },
];

const SORTS = [
  { id: 'updated', label: 'Cập nhật mới nhất' },
  { id: 'name', label: 'Tên A → Z' },
  { id: 'episodes', label: 'Số tập nhiều nhất' },
];

export const ProjectFilters: React.FC<ProjectFiltersProps> = ({
  search,
  onSearchChange,
  genre,
  onGenreChange,
  genres,
  viewMode,
  onViewModeChange,
  status = 'all',
  onStatusChange,
  sort = 'updated',
  onSortChange,
}) => {
  const genreOptions = [
    { id: 'all', label: 'Tất cả' },
    ...(genres ?? []).map((g) => ({ id: g, label: g.split('/')[0].trim() })),
  ];

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '10px 12px',
        background: 'rgba(19,27,46,0.96)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '12px',
        marginBottom: '16px',
        flexWrap: 'wrap',
      }}
    >
      {/* Search */}
      <div style={{ position: 'relative', flex: '1 1 260px', minWidth: '200px', maxWidth: '420px' }}>
        <Search
          size={15}
          style={{
            position: 'absolute',
            left: '11px',
            top: '50%',
            transform: 'translateY(-50%)',
            color: '#64748b',
            pointerEvents: 'none',
          }}
        />
        <input
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Tìm kiếm dự án theo tên hoặc mô tả..."
          style={{
            width: '100%',
            padding: '8px 12px 8px 34px',
            borderRadius: '8px',
            background: '#0f172a',
            border: '1px solid rgba(255,255,255,0.08)',
            color: '#e2e8f0',
            fontSize: '13px',
            outline: 'none',
          }}
        />
      </div>

      {/* Dropdowns */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <FilterSelect label="Trạng thái:" value={status} onChange={(v) => onStatusChange?.(v)} options={STATUSES} />
        <FilterSelect label="Thể loại:" value={genre} onChange={onGenreChange} options={genreOptions} />
        <FilterSelect label="Sắp xếp:" value={sort} onChange={(v) => onSortChange?.(v)} options={SORTS} />
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* View toggle */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: '#0f172a',
          borderRadius: '8px',
          padding: '3px',
          border: '1px solid rgba(255,255,255,0.06)',
          gap: '2px',
        }}
      >
        <button
          onClick={() => onViewModeChange('grid')}
          title="Xem dạng lưới"
          style={{
            width: '32px',
            height: '28px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '6px',
            border: 'none',
            cursor: 'pointer',
            background: viewMode === 'grid' ? 'linear-gradient(135deg, #2563eb 0%, #4f46e5 100%)' : 'transparent',
            color: viewMode === 'grid' ? '#ffffff' : '#64748b',
            boxShadow: viewMode === 'grid' ? '0 2px 8px rgba(37,99,235,0.4)' : 'none',
          }}
        >
          <Grid2x2 size={14} />
        </button>
        <button
          onClick={() => onViewModeChange('list')}
          title="Xem dạng danh sách"
          style={{
            width: '32px',
            height: '28px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '6px',
            border: 'none',
            cursor: 'pointer',
            background: viewMode === 'list' ? 'linear-gradient(135deg, #2563eb 0%, #4f46e5 100%)' : 'transparent',
            color: viewMode === 'list' ? '#ffffff' : '#64748b',
            boxShadow: viewMode === 'list' ? '0 2px 8px rgba(37,99,235,0.4)' : 'none',
          }}
        >
          <List size={14} />
        </button>
      </div>
    </div>
  );
};

const FilterSelect: React.FC<{
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { id: string; label: string }[];
}> = ({ label, value, onChange, options }) => {
  return (
    <label
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        padding: '6px 10px',
        background: '#0f172a',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '8px',
        fontSize: '12px',
        color: '#94a3b8',
        fontWeight: 500,
        cursor: 'pointer',
        whiteSpace: 'nowrap',
        position: 'relative',
      }}
    >
      <span style={{ color: '#64748b', fontWeight: 500 }}>{label}</span>
      <span style={{ color: '#e2e8f0', fontWeight: 650, marginRight: '2px' }}>
        {options.find((o) => o.id === value)?.label ?? value}
      </span>
      <ChevronDown size={12} style={{ color: '#64748b' }} />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          position: 'absolute',
          inset: 0,
          opacity: 0,
          cursor: 'pointer',
          width: '100%',
          height: '100%',
        }}
      >
        {options.map((o) => (
          <option key={o.id} value={o.id} style={{ background: '#0f172a' }}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
};
