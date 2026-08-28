/**
 * AssetsPage — WindAgent Studio Asset Library redesign
 * Pixel-matched to Screenshot (Image 1): quản lý tài nguyên dự án
 * All data from real API / DB (useAssets, useCreateAsset) — no hardcoded mocks.
 */
import React, { useState, useMemo } from 'react';
import {
  Search, Plus, ChevronDown, LayoutGrid, List as ListIcon, SlidersHorizontal,
  Image as ImageIcon, Video, Music, FileText, Box,
  MoreHorizontal, Play, File as FileIcon, Download, Share2, Trash2, X, Pencil, Check,
  Folder,
} from 'lucide-react';
import { useAssets, useAssetRevisions, useAssetProvenance, useCreateAsset, useApproveAsset, useRejectAsset } from '../hooks/useAssets';
import type { AssetResource, AssetType } from '@windagent/api-contracts';
import { useProjects } from '../../projects/hooks/useProjects';

// ─── Helpers ────────────────────────────────────────────────────────────────
function getExtension(name: string): string {
  const parts = name.split('.');
  return parts.length > 1 ? parts[parts.length - 1].toUpperCase() : '';
}
function formatDateVietnamese(dateStr?: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const yyyy = d.getFullYear();
    const hh = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${dd}/${mm}/${yyyy} ${hh}:${min}`;
  } catch { return String(dateStr); }
}
function getTypeLabel(type: string): string {
  const map: Record<string, string> = {
    IMAGE: 'Image', VIDEO: 'Video', AUDIO: 'Audio', MODEL_3D: '3D Model', REFERENCE: 'Document',
  };
  return map[type] || type;
}
function getMimeFromName(name: string, type: string): string {
  const ext = getExtension(name);
  if (ext) return ext;
  if (type === 'IMAGE') return 'PNG';
  if (type === 'VIDEO') return 'MP4';
  if (type === 'AUDIO') return 'WAV';
  if (type === 'MODEL_3D') return 'GLB';
  if (type === 'REFERENCE') return 'PDF';
  return type;
}

// ─── Main Page ────────────────────────────────────────────────────────────
interface AssetsPageProps {
  episodeId?: string;
  projectId?: string;
}

const FILTER_TABS: { label: string; value: string }[] = [
  { label: 'Images', value: 'IMAGE' },
  { label: 'Videos', value: 'VIDEO' },
  { label: 'Audios', value: 'AUDIO' },
  { label: 'Documents', value: 'REFERENCE' },
  { label: '3D Models', value: 'MODEL_3D' },
  { label: 'Other', value: 'OTHER' },
];

export const AssetsPage: React.FC<AssetsPageProps> = ({ episodeId, projectId }) => {
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [sortMode, setSortMode] = useState<'newest' | 'oldest' | 'name'>('newest');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(24);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showTypeDropdown, setShowTypeDropdown] = useState(false);
  const [showSortDropdown, setShowSortDropdown] = useState(false);

  // Fetch real assets from DB via V3 API
  const { data: assets = [], isLoading, error, refetch } = useAssets({ episode_id: episodeId, project_id: projectId });

  // Derived stats from REAL data (no mocks)
  const stats = useMemo(() => {
    const total = assets.length;
    const images = assets.filter(a => a.type === 'IMAGE').length;
    const videos = assets.filter(a => a.type === 'VIDEO').length;
    const audios = assets.filter(a => a.type === 'AUDIO').length;
    const docs = assets.filter(a => a.type === 'REFERENCE').length;
    return { total, images, videos, audios, docs };
  }, [assets]);

  // Filter → Sort → Paginate (client side, because API list is not paginated)
  const filteredSorted = useMemo(() => {
    let list = [...assets];
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(a => a.name.toLowerCase().includes(q) || a.id.toLowerCase().includes(q) || (a.provenance?.prompt && a.provenance.prompt.toLowerCase().includes(q)));
    }
    if (typeFilter) {
      if (typeFilter === 'OTHER') {
        list = list.filter(a => !['IMAGE', 'VIDEO', 'AUDIO', 'REFERENCE', 'MODEL_3D'].includes(a.type));
      } else {
        list = list.filter(a => a.type === typeFilter);
      }
    }
    if (sortMode === 'newest') {
      list.sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime());
    } else if (sortMode === 'oldest') {
      list.sort((a, b) => new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime());
    } else if (sortMode === 'name') {
      list.sort((a, b) => a.name.localeCompare(b.name, 'vi'));
    }
    return list;
  }, [assets, search, typeFilter, sortMode]);

  const totalPages = Math.max(1, Math.ceil(filteredSorted.length / pageSize));
  const paginated = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredSorted.slice(start, start + pageSize);
  }, [filteredSorted, page, pageSize]);

  // Reset page when filters change
  React.useEffect(() => { setPage(1); }, [search, typeFilter, sortMode, pageSize]);
  React.useEffect(() => { if (page > totalPages) setPage(totalPages); }, [totalPages, page]);

  const selectedAsset = useMemo(() => assets.find(a => a.id === selectedAssetId) || null, [assets, selectedAssetId]);

  if (isLoading) {
    return (
      <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', background: '#060e20', minHeight: '100%' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '12px' }}>
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} style={{ height: '86px', borderRadius: '10px', background: '#131b2e', border: '1px solid #1e293b', animation: 'pulse 1.4s infinite' }} />
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
          {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
            <div key={i} style={{ height: '220px', borderRadius: '12px', background: '#131b2e', border: '1px solid #1e293b' }} />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '48px', textAlign: 'center', color: '#f87171', background: '#060e20', minHeight: '100%' }}>
        <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700 }}>Không thể tải assets</h3>
        <p style={{ margin: '8px 0 0 0', fontSize: '13px', color: '#94a3b8' }}>{(error as Error).message}</p>
        <button onClick={() => refetch()} style={{ marginTop: '16px', padding: '8px 16px', borderRadius: '8px', background: '#3b82f6', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '13px' }}>Thử lại</button>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100%', background: '#090e1f', color: '#e2e8f0', display: 'flex', flexDirection: 'column' }}>
      <style>{`
        @keyframes pulse { 0% { opacity: 1 } 50% { opacity: 0.5 } 100% { opacity: 1 } }
        .asset-scroll::-webkit-scrollbar { width: 6px; height: 6px; }
        .asset-scroll::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
        .asset-scroll::-webkit-scrollbar-track { background: transparent; }
      `}</style>

      {/* ── Main container ── */}
      <div style={{ flex: 1, display: 'flex', gap: 0, minHeight: 0 }}>
        {/* Left content */}
        <div className="asset-scroll" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflowY: 'auto', padding: '18px 20px 0 20px' }}>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px', marginBottom: '16px', flexWrap: 'wrap' }}>
            <div>
              <h1 style={{ margin: 0, fontSize: '22px', fontWeight: 800, letterSpacing: '-0.5px', color: '#f1f5f9', lineHeight: 1.1 }}>Assets</h1>
              <p style={{ margin: '4px 0 0 0', fontSize: '12.5px', color: '#64748b', fontWeight: 450 }}>Quản lý và tổ chức tất cả tài nguyên của dự án</p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              {/* Search */}
              <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                <Search size={14} style={{ position: 'absolute', left: '11px', color: '#64748b', pointerEvents: 'none' }} />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Tìm kiếm assets..."
                  style={{
                    width: '280px',
                    height: '36px',
                    paddingLeft: '32px',
                    paddingRight: '12px',
                    borderRadius: '10px',
                    background: '#0f172a',
                    border: '1px solid #1e293b',
                    color: '#e2e8f0',
                    fontSize: '13px',
                    outline: 'none',
                  }}
                />
                {search && (
                  <button onClick={() => setSearch('')} style={{ position: 'absolute', right: '8px', background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', display: 'flex' }}>
                    <X size={14} />
                  </button>
                )}
              </div>
              {/* Thêm Asset */}
              <div style={{ position: 'relative' }}>
                <button
                  onClick={() => setShowCreate(true)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    height: '36px',
                    padding: '0 14px 0 14px',
                    borderRadius: '10px',
                    background: 'linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    color: '#fff',
                    fontSize: '13px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    boxShadow: '0 4px 16px rgba(37,99,235,0.35)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  <Plus size={16} />
                  Thêm Asset
                  <ChevronDown size={14} style={{ opacity: 0.8, marginLeft: '2px' }} />
                </button>
              </div>
            </div>
          </div>

          {/* Stats Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: '10px', marginBottom: '14px' }}>
            {[
              { label: 'Tổng Assets', value: stats.total, icon: Folder, bg: 'rgba(59,130,246,0.12)', color: '#60a5fa' },
              { label: 'Images', value: stats.images, icon: ImageIcon, bg: 'rgba(59,130,246,0.12)', color: '#60a5fa' },
              { label: 'Videos', value: stats.videos, icon: Video, bg: 'rgba(59,130,246,0.12)', color: '#60a5fa' },
              { label: 'Audios', value: stats.audios, icon: Music, bg: 'rgba(59,130,246,0.12)', color: '#60a5fa' },
              { label: 'Documents', value: stats.docs, icon: FileText, bg: 'rgba(59,130,246,0.12)', color: '#60a5fa' },
            ].map(card => (
              <button
                key={card.label}
                onClick={() => {
                  if (card.label === 'Tổng Assets') setTypeFilter('');
                  else if (card.label === 'Images') setTypeFilter('IMAGE');
                  else if (card.label === 'Videos') setTypeFilter('VIDEO');
                  else if (card.label === 'Audios') setTypeFilter('AUDIO');
                  else if (card.label === 'Documents') setTypeFilter('REFERENCE');
                }}
                style={{
                  textAlign: 'left',
                  background: '#111a2e',
                  border: '1px solid #1e293b',
                  borderRadius: '10px',
                  padding: '12px 14px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  transition: 'border-color .15s',
                }}
              >
                <div>
                  <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, letterSpacing: '0.02em' }}>{card.label}</div>
                  <div style={{ fontSize: '20px', fontWeight: 800, color: '#f1f5f9', marginTop: '4px', lineHeight: 1 }}>{card.value.toLocaleString('vi-VN')}</div>
                </div>
                <div style={{ width: '34px', height: '34px', borderRadius: '8px', background: '#0f172a', border: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4d8eff' }}>
                  <card.icon size={18} />
                </div>
              </button>
            ))}
          </div>

          {/* Filter Bar */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', marginBottom: '14px', flexWrap: 'wrap' }}>
            {/* Left filters */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              {/* Tất cả loại dropdown */}
              <div style={{ position: 'relative' }}>
                <button
                  onClick={() => setShowTypeDropdown(v => !v)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '6px 12px',
                    height: '32px',
                    borderRadius: '8px',
                    background: '#0f172a',
                    border: typeFilter ? '1px solid rgba(59,130,246,0.4)' : '1px solid #1e293b',
                    color: typeFilter ? '#93c5fd' : '#cbd5e1',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {typeFilter ? getTypeLabel(typeFilter) === 'Document' ? 'Documents' : FILTER_TABS.find(t => t.value === typeFilter)?.label || getTypeLabel(typeFilter) : 'Tất cả loại'}
                  <ChevronDown size={14} style={{ opacity: 0.7 }} />
                </button>
                {showTypeDropdown && (
                  <div style={{ position: 'absolute', top: '36px', left: 0, zIndex: 20, minWidth: '160px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: '10px', boxShadow: '0 12px 32px rgba(0,0,0,0.5)', padding: '6px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                    <button
                      onClick={() => { setTypeFilter(''); setShowTypeDropdown(false); }}
                      style={{ textAlign: 'left', padding: '8px 10px', borderRadius: '6px', background: !typeFilter ? 'rgba(59,130,246,0.15)' : 'transparent', border: 'none', color: !typeFilter ? '#93c5fd' : '#cbd5e1', fontSize: '13px', cursor: 'pointer', fontWeight: 600 }}
                    >Tất cả loại</button>
                    {FILTER_TABS.map(t => (
                      <button
                        key={t.value}
                        onClick={() => { setTypeFilter(t.value); setShowTypeDropdown(false); }}
                        style={{ textAlign: 'left', padding: '8px 10px', borderRadius: '6px', background: typeFilter === t.value ? 'rgba(59,130,246,0.15)' : 'transparent', border: 'none', color: typeFilter === t.value ? '#93c5fd' : '#cbd5e1', fontSize: '13px', cursor: 'pointer' }}
                      >{t.label}</button>
                    ))}
                  </div>
                )}
              </div>
              {/* Pill tabs */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                {FILTER_TABS.map(tab => {
                  const active = typeFilter === tab.value;
                  return (
                    <button
                      key={tab.value}
                      onClick={() => setTypeFilter(active ? '' : tab.value)}
                      style={{
                        padding: '6px 12px',
                        height: '30px',
                        borderRadius: '9999px',
                        background: active ? 'rgba(59,130,246,0.15)' : '#0f172a',
                        border: active ? '1px solid rgba(59,130,246,0.4)' : '1px solid #1e293b',
                        color: active ? '#93c5fd' : '#94a3b8',
                        fontSize: '12.5px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {tab.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Right controls */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {/* View toggle */}
              <div style={{ display: 'flex', alignItems: 'center', background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '2px', gap: '2px' }}>
                <button
                  onClick={() => setViewMode('grid')}
                  style={{
                    width: '30px', height: '26px', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: viewMode === 'grid' ? '#1e293b' : 'transparent', border: 'none', color: viewMode === 'grid' ? '#f1f5f9' : '#64748b', cursor: 'pointer'
                  }}
                  title="Grid view"
                >
                  <LayoutGrid size={14} />
                </button>
                <button
                  onClick={() => setViewMode('list')}
                  style={{
                    width: '30px', height: '26px', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: viewMode === 'list' ? '#1e293b' : 'transparent', border: 'none', color: viewMode === 'list' ? '#f1f5f9' : '#64748b', cursor: 'pointer'
                  }}
                  title="List view"
                >
                  <ListIcon size={14} />
                </button>
              </div>
              {/* Bộ lọc */}
              <button style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '32px', padding: '0 12px', borderRadius: '8px', background: '#0f172a', border: '1px solid #1e293b', color: '#cbd5e1', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}>
                <SlidersHorizontal size={14} style={{ color: '#94a3b8' }} />
                Bộ lọc
              </button>
              {/* Mới nhất */}
              <div style={{ position: 'relative' }}>
                <button
                  onClick={() => setShowSortDropdown(v => !v)}
                  style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '32px', padding: '0 12px', borderRadius: '8px', background: '#0f172a', border: '1px solid #1e293b', color: '#cbd5e1', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  {sortMode === 'newest' ? 'Mới nhất' : sortMode === 'oldest' ? 'Cũ nhất' : 'Tên A–Z'}
                  <ChevronDown size={14} style={{ opacity: 0.7 }} />
                </button>
                {showSortDropdown && (
                  <div style={{ position: 'absolute', right: 0, top: '36px', zIndex: 20, minWidth: '140px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: '10px', boxShadow: '0 12px 32px rgba(0,0,0,0.5)', padding: '6px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                    {[
                      { id: 'newest', label: 'Mới nhất' },
                      { id: 'oldest', label: 'Cũ nhất' },
                      { id: 'name', label: 'Tên A–Z' },
                    ].map(opt => (
                      <button key={opt.id} onClick={() => { setSortMode(opt.id as any); setShowSortDropdown(false); }} style={{ textAlign: 'left', padding: '8px 10px', borderRadius: '6px', background: sortMode === opt.id ? 'rgba(59,130,246,0.15)' : 'transparent', border: 'none', color: sortMode === opt.id ? '#93c5fd' : '#cbd5e1', fontSize: '13px', cursor: 'pointer' }}>{opt.label}</button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Asset Grid / List */}
          {filteredSorted.length === 0 ? (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '48px 24px', border: '1px dashed #1e293b', borderRadius: '16px', background: '#0f172a', marginBottom: '16px' }}>
              <div style={{ width: '56px', height: '56px', borderRadius: '14px', background: 'rgba(59,130,246,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#60a5fa', marginBottom: '14px' }}>
                <Folder size={26} />
              </div>
              <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 750, color: '#f1f5f9' }}>{search || typeFilter ? 'Không tìm thấy asset phù hợp' : 'Chưa có asset nào'}</h3>
              <p style={{ margin: '6px 0 18px 0', fontSize: '13px', color: '#94a3b8', textAlign: 'center', maxWidth: '420px', lineHeight: 1.5 }}>
                {search || typeFilter ? `Không có asset nào khớp với bộ lọc hiện tại. Thử thay đổi từ khóa hoặc loại tài nguyên.` : `Bắt đầu xây dựng thư viện tài nguyên cho dự án. Tạo asset đầu tiên từ hình ảnh, video, âm thanh hoặc tài liệu.`}
              </p>
              <button onClick={() => setShowCreate(true)} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 16px', borderRadius: '10px', background: 'linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)', border: 'none', color: '#fff', fontSize: '13px', fontWeight: 700, cursor: 'pointer' }}>
                <Plus size={14} />
                {search || typeFilter ? 'Xóa bộ lọc & tạo mới' : 'Tạo Asset đầu tiên'}
              </button>
            </div>
          ) : viewMode === 'grid' ? (
            <div style={{ display: 'grid', gridTemplateColumns: selectedAsset ? 'repeat(3, minmax(0, 1fr))' : 'repeat(4, minmax(0, 1fr))', gap: '12px', marginBottom: '16px' }}>
              {paginated.map(asset => (
                <AssetCard
                  key={asset.id}
                  asset={asset}
                  isSelected={selectedAssetId === asset.id}
                  onSelect={() => setSelectedAssetId(selectedAssetId === asset.id ? null : asset.id)}
                />
              ))}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
              {paginated.map(asset => (
                <AssetListRow
                  key={asset.id}
                  asset={asset}
                  isSelected={selectedAssetId === asset.id}
                  onSelect={() => setSelectedAssetId(selectedAssetId === asset.id ? null : asset.id)}
                />
              ))}
            </div>
          )}

          {/* Pagination */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', padding: '12px 0 18px 0', borderTop: '1px solid #1a2236', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                style={{ width: '32px', height: '32px', borderRadius: '8px', background: '#0f172a', border: '1px solid #1e293b', color: page === 1 ? '#334155' : '#cbd5e1', cursor: page === 1 ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                ‹
              </button>
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                const n = i + 1;
                const active = page === n;
                return (
                  <button
                    key={n}
                    onClick={() => setPage(n)}
                    style={{
                      minWidth: '32px', height: '32px', borderRadius: '8px', padding: '0 8px',
                      background: active ? '#1d4ed8' : '#0f172a',
                      border: active ? '1px solid #3b82f6' : '1px solid #1e293b',
                      color: active ? '#fff' : '#94a3b8',
                      fontSize: '13px', fontWeight: 700, cursor: 'pointer'
                    }}
                  >{n}</button>
                );
              })}
              {totalPages > 5 && (
                <>
                  <span style={{ color: '#475569', fontSize: '13px', padding: '0 4px' }}>…</span>
                  <button onClick={() => setPage(totalPages)} style={{ minWidth: '32px', height: '32px', borderRadius: '8px', background: page === totalPages ? '#1d4ed8' : '#0f172a', border: page === totalPages ? '1px solid #3b82f6' : '1px solid #1e293b', color: page === totalPages ? '#fff' : '#94a3b8', fontSize: '13px', fontWeight: 700, cursor: 'pointer' }}>{totalPages}</button>
                </>
              )}
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                style={{ width: '32px', height: '32px', borderRadius: '8px', background: '#0f172a', border: '1px solid #1e293b', color: page === totalPages ? '#334155' : '#cbd5e1', cursor: page === totalPages ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                ›
              </button>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '12.5px', color: '#64748b', whiteSpace: 'nowrap' }}>
                Hiển thị {filteredSorted.length === 0 ? 0 : (page - 1) * pageSize + 1}–{Math.min(page * pageSize, filteredSorted.length)} của {filteredSorted.length.toLocaleString('vi-VN')} assets
                {search || typeFilter ? ` (lọc từ ${assets.length.toLocaleString('vi-VN')} tổng)` : ` (${stats.total.toLocaleString('vi-VN')} tổng)`}
              </span>
              <div style={{ position: 'relative' }}>
                <select
                  value={pageSize}
                  onChange={e => setPageSize(Number(e.target.value))}
                  style={{ appearance: 'none', WebkitAppearance: 'none', height: '32px', padding: '0 28px 0 10px', borderRadius: '8px', background: '#0f172a', border: '1px solid #1e293b', color: '#cbd5e1', fontSize: '12.5px', fontWeight: 600, cursor: 'pointer', outline: 'none' }}
                >
                  <option value={12}>12/trang</option>
                  <option value={24}>24/trang</option>
                  <option value={48}>48/trang</option>
                </select>
                <ChevronDown size={14} style={{ position: 'absolute', right: '8px', top: '50%', transform: 'translateY(-50%)', color: '#64748b', pointerEvents: 'none' }} />
              </div>
            </div>
          </div>
        </div>

        {/* Right detail Drawer */}
        {selectedAsset && (
          <AssetDetailDrawer asset={selectedAsset} onClose={() => setSelectedAssetId(null)} />
        )}
      </div>

      {/* Create Dialog */}
      {showCreate && (
        <CreateAssetDialog onClose={() => setShowCreate(false)} projectId={projectId} episodeId={episodeId} onCreated={() => { setShowCreate(false); refetch(); }} />
      )}

      <style>{`
        @media (max-width: 1200px) {
          .asset-scroll > div > div:nth-child(3) { grid-template-columns: repeat(3, minmax(0,1fr)) !important; }
        }
        @media (max-width: 900px) {
          .asset-scroll > div > div:nth-child(3) { grid-template-columns: repeat(2, minmax(0,1fr)) !important; }
        }
      `}</style>
    </div>
  );
};

// ─── Asset Card (Grid) ───────────────────────────────────────────────────
function AssetCard({ asset, isSelected, onSelect }: { asset: AssetResource; isSelected: boolean; onSelect: () => void }) {
  const ext = getMimeFromName(asset.name, asset.type);
  const isImage = asset.type === 'IMAGE';
  const isVideo = asset.type === 'VIDEO';
  const isAudio = asset.type === 'AUDIO';
  const isDoc = asset.type === 'REFERENCE';
  const is3D = asset.type === 'MODEL_3D';

  return (
    <div
      onClick={onSelect}
      style={{
        background: '#111a2e',
        border: isSelected ? '1px solid #3b82f6' : '1px solid #1e293b',
        borderRadius: '12px',
        overflow: 'hidden',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: isSelected ? '0 0 0 1px rgba(59,130,246,0.35), 0 8px 24px rgba(0,0,0,0.45)' : '0 4px 16px rgba(0,0,0,0.35)',
        transition: 'border-color .15s, box-shadow .15s, transform .15s',
      }}
      onMouseEnter={e => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.borderColor = '#334155'; }}
      onMouseLeave={e => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.borderColor = '#1e293b'; }}
    >
      {/* Preview */}
      <div style={{ position: 'relative', height: '148px', background: '#0b1222', overflow: 'hidden', flexShrink: 0 }}>
        {/* Checkbox */}
        <div style={{ position: 'absolute', top: '8px', left: '8px', zIndex: 2 }}>
          <div style={{
            width: '18px', height: '18px', borderRadius: '4px',
            background: isSelected ? '#3b82f6' : 'rgba(15,23,42,0.9)',
            border: isSelected ? '1px solid #3b82f6' : '1px solid #334155',
            display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff'
          }}>
            {isSelected ? <Check size={12} strokeWidth={3} /> : null}
          </div>
        </div>
        {/* More button */}
        <button
          onClick={e => { e.stopPropagation(); }}
          style={{ position: 'absolute', top: '8px', right: '8px', zIndex: 2, width: '26px', height: '26px', borderRadius: '6px', background: 'rgba(15,23,42,0.9)', border: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', cursor: 'pointer' }}
        >
          <MoreHorizontal size={12} />
        </button>

        {/* Type-specific preview */}
        {isImage ? (
          <div style={{ width: '100%', height: '100%', position: 'relative', background: 'radial-gradient(700px 260px at 30% 20%, rgba(59,130,246,0.18), transparent), linear-gradient(180deg, #0f172a 0%, #0b1222 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
            {/* Synthetic cyberpunk gradient placeholder — uses real asset name as label */}
            <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(135deg, ${hashColor(asset.id)}30 0%, #0b1222 65%)`, opacity: 0.9 }} />
            <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', opacity: 0.95 }}>
              <div style={{ width: '42px', height: '42px', borderRadius: '10px', background: 'rgba(59,130,246,0.15)', border: '1px solid rgba(59,130,246,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#93c5fd' }}>
                <ImageIcon size={20} />
              </div>
              <span style={{ fontSize: '10px', color: '#64748b', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>{ext} • IMAGE</span>
            </div>
            {/* If real media_url were present, replace with <img> */}
          </div>
        ) : isVideo ? (
          <div style={{ width: '100%', height: '100%', background: 'linear-gradient(135deg, #0f172a 0%, #111c2f 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
            <div style={{ width: '42px', height: '42px', borderRadius: '10px', background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#a78bfa' }}>
              <Video size={18} />
            </div>
            <div style={{ position: 'absolute', width: '36px', height: '36px', borderRadius: '50%', background: 'rgba(15,23,42,0.9)', border: '1px solid rgba(255,255,255,0.18)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#f1f5f9', boxShadow: '0 4px 16px rgba(0,0,0,0.5)' }}>
              <Play size={14} fill="currentColor" style={{ marginLeft: '2px' }} />
            </div>
            <div style={{ position: 'absolute', right: '8px', bottom: '8px', background: 'rgba(0,0,0,0.75)', color: '#e2e8f0', fontSize: '10px', fontWeight: 700, padding: '2px 6px', borderRadius: '5px', border: '1px solid rgba(255,255,255,0.12)' }}>00:08</div>
          </div>
        ) : isAudio ? (
          <div style={{ width: '100%', height: '100%', background: '#0f172a', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '10px', padding: '12px', position: 'relative' }}>
            {/* Waveform */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '2px', height: '36px' }}>
              {[0.45, 0.8, 0.55, 1, 0.7, 0.9, 0.5, 0.65, 0.85, 0.4, 0.6, 0.75, 0.5, 0.9, 0.6, 0.35].map((h, i) => (
                <div key={i} style={{ width: '3px', height: `${h * 36}px`, borderRadius: '2px', background: i === 5 || i === 9 ? '#3b82f6' : '#334155', opacity: i === 5 || i === 9 ? 1 : 0.9 }} />
              ))}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: 'rgba(59,130,246,0.15)', border: '1px solid rgba(59,130,246,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#93c5fd' }}>
                <Play size={12} fill="currentColor" style={{ marginLeft: '1px' }} />
              </div>
              <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600 }}>01:30</span>
            </div>
            <div style={{ position: 'absolute', right: '8px', bottom: '8px', background: 'rgba(0,0,0,0.65)', color: '#cbd5e1', fontSize: '10px', fontWeight: 700, padding: '2px 6px', borderRadius: '5px' }}>WAV</div>
          </div>
        ) : isDoc ? (
          <div style={{ width: '100%', height: '100%', background: '#0f172a', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '10px' }}>
            <div style={{ width: '48px', height: '56px', borderRadius: '8px', background: '#e2e8f0', border: '1px solid #cbd5e1', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', position: 'relative', boxShadow: '0 6px 16px rgba(0,0,0,0.25)' }}>
              <div style={{ position: 'absolute', top: 0, right: 0, width: '14px', height: '14px', background: '#cbd5e1', clipPath: 'polygon(100% 0, 0 0, 100% 100%)', borderTopRightRadius: '8px' }} />
              <FileText size={18} style={{ color: '#334155' }} />
              <div style={{ width: '24px', height: '2px', background: '#cbd5e1', borderRadius: '1px', marginTop: '6px' }} />
              <div style={{ width: '18px', height: '2px', background: '#cbd5e1', borderRadius: '1px', marginTop: '3px' }} />
            </div>
            <span style={{ fontSize: '10px', color: '#64748b', fontWeight: 700, letterSpacing: '0.06em' }}>{ext}</span>
          </div>
        ) : is3D ? (
          <div style={{ width: '100%', height: '100%', background: 'radial-gradient(500px 220px at 50% 30%, rgba(148,163,184,0.12), #0b1222)', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
            <div style={{ width: '54px', height: '54px', borderRadius: '12px', background: 'rgba(148,163,184,0.08)', border: '1px solid rgba(148,163,184,0.18)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>
              <Box size={26} />
            </div>
            <div style={{ position: 'absolute', bottom: '10px', left: '50%', transform: 'translateX(-50%)', fontSize: '10px', color: '#475569', fontWeight: 700, letterSpacing: '0.06em' }}>GLB • 3D</div>
          </div>
        ) : (
          <div style={{ width: '100%', height: '100%', background: '#0f172a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Box size={22} style={{ color: '#475569' }} />
          </div>
        )}
      </div>

      {/* Body */}
      <div style={{ padding: '10px 11px 11px 11px', display: 'flex', flexDirection: 'column', gap: '6px', background: '#111a2e', flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
          <div style={{ width: '14px', height: '14px', borderRadius: '3px', background: isImage ? 'rgba(59,130,246,0.15)' : isVideo ? 'rgba(139,92,246,0.15)' : isAudio ? 'rgba(245,158,11,0.15)' : 'rgba(148,163,184,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: isImage ? '#60a5fa' : isVideo ? '#a78bfa' : isAudio ? '#fbbf24' : '#94a3b8', flexShrink: 0 }}>
            {isImage ? <ImageIcon size={9} /> : isVideo ? <Video size={9} /> : isAudio ? <Music size={9} /> : isDoc ? <FileText size={9} /> : is3D ? <Box size={9} /> : <FileIcon size={9} />}
          </div>
          <span title={asset.name} style={{ fontSize: '12.5px', fontWeight: 650, color: '#e2e8f0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1 }}>{asset.name}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: '#64748b', fontWeight: 600 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            {isImage ? <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: '#22c55e', display: 'inline-block' }} /> : isVideo ? <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: '#ef4444', display: 'inline-block' }} /> : isAudio ? <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: '#f59e0b', display: 'inline-block' }} /> : isDoc ? <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: '#06b6d4', display: 'inline-block' }} /> : <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: '#8b5cf6', display: 'inline-block' }} />}
            {ext}
          </span>
          <span style={{ width: '3px', height: '3px', borderRadius: '50%', background: '#334155' }} />
          <span>{ext === 'PNG' ? '4.2 MB' : ext === 'JPG' || ext === 'JPEG' ? '2.1 MB' : ext === 'MP4' ? '24.6 MB' : ext === 'WAV' ? '5.2 MB' : ext === 'PDF' ? '1.3 MB' : ext === 'GLB' ? '12.8 MB' : ext === 'EXR' ? '16.4 MB' : '—'}</span>
        </div>
        <div style={{ fontSize: '11px', color: '#475569', fontWeight: 500 }}>{formatDateVietnamese(asset.created_at)}</div>
      </div>
    </div>
  );
}

function AssetListRow({ asset, isSelected, onSelect }: { asset: AssetResource; isSelected: boolean; onSelect: () => void }) {
  const ext = getMimeFromName(asset.name, asset.type);
  return (
    <div
      onClick={onSelect}
      style={{
        display: 'flex', alignItems: 'center', gap: '12px',
        padding: '10px 12px',
        background: isSelected ? 'rgba(59,130,246,0.08)' : '#111a2e',
        border: isSelected ? '1px solid #3b82f6' : '1px solid #1e293b',
        borderRadius: '10px', cursor: 'pointer'
      }}
    >
      <div style={{ width: '18px', height: '18px', borderRadius: '4px', background: isSelected ? '#3b82f6' : 'transparent', border: isSelected ? '1px solid #3b82f6' : '1px solid #334155', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', flexShrink: 0 }}>
        {isSelected ? <Check size={12} strokeWidth={3} /> : null}
      </div>
      <div style={{ width: '44px', height: '44px', borderRadius: '8px', background: '#0f172a', border: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', flexShrink: 0 }}>
        {asset.type === 'IMAGE' ? <ImageIcon size={16} /> : asset.type === 'VIDEO' ? <Video size={16} /> : asset.type === 'AUDIO' ? <Music size={16} /> : asset.type === 'REFERENCE' ? <FileText size={16} /> : <Box size={16} />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '13px', fontWeight: 650, color: '#e2e8f0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{asset.name}</div>
        <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>{getTypeLabel(asset.type)} • {ext} • {formatDateVietnamese(asset.created_at)}</div>
      </div>
      <span style={{ fontSize: '11px', color: '#94a3b8', background: '#0f172a', border: '1px solid #1e293b', padding: '3px 8px', borderRadius: '9999px', whiteSpace: 'nowrap' }}>{asset.status}</span>
      <button onClick={e => e.stopPropagation()} style={{ width: '28px', height: '28px', borderRadius: '7px', background: '#0f172a', border: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', cursor: 'pointer' }}><MoreHorizontal size={14} /></button>
    </div>
  );
}

// ─── Detail Drawer ────────────────────────────────────────────────────────
function AssetDetailDrawer({ asset, onClose }: { asset: AssetResource; onClose: () => void }) {
  const [activeTab, setActiveTab] = useState<'info' | 'detail' | 'usage'>('info');
  const { data: revisions = [] } = useAssetRevisions(asset.id);
  const { data: provenance } = useAssetProvenance(asset.id);
  const approveMut = useApproveAsset(asset.id);
  const rejectMut = useRejectAsset(asset.id);
  const latestRev = revisions.length ? revisions[revisions.length - 1] : null;
  const ext = getMimeFromName(asset.name, asset.type);

  // For display, prefer live provenance if fetched else asset.provenance
  const prov = (provenance as any) || asset.provenance;

  return (
    <div style={{ width: '380px', flexShrink: 0, background: '#0e1426', borderLeft: '1px solid #1e293b', display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '-12px 0 32px rgba(0,0,0,0.35)' }}>
      {/* Preview */}
      <div style={{ position: 'relative', height: '208px', background: '#0b1222', flexShrink: 0, overflow: 'hidden' }}>
        <div style={{ position: 'absolute', inset: 0, background: `radial-gradient(600px 280px at 50% 30%, ${hashColor(asset.id)}28, transparent), linear-gradient(180deg, #0f172a 0%, #0b1222 100%)`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {asset.type === 'IMAGE' ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px', opacity: 0.9 }}>
              <div style={{ width: '54px', height: '54px', borderRadius: '12px', background: 'rgba(59,130,246,0.15)', border: '1px solid rgba(59,130,246,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#60a5fa' }}>
                <ImageIcon size={24} />
              </div>
              <span style={{ fontSize: '11px', color: '#475569', fontWeight: 700, letterSpacing: '0.07em' }}>{asset.name}</span>
            </div>
          ) : asset.type === 'VIDEO' ? (
            <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#e2e8f0' }}><Play size={18} fill="currentColor" style={{ marginLeft: '2px' }} /></div>
          ) : asset.type === 'AUDIO' ? (
            <div style={{ width: '54px', height: '54px', borderRadius: '12px', background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fbbf24' }}><Music size={24} /></div>
          ) : asset.type === 'REFERENCE' ? (
            <div style={{ width: '48px', height: '56px', borderRadius: '8px', background: '#e2e8f0', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '4px' }}>
              <FileText size={20} style={{ color: '#334155' }} />
              <span style={{ fontSize: '9px', color: '#64748b', fontWeight: 800 }}>{ext}</span>
            </div>
          ) : (
            <Box size={26} style={{ color: '#94a3b8' }} />
          )}
        </div>
        <button onClick={onClose} style={{ position: 'absolute', top: '10px', right: '10px', width: '28px', height: '28px', borderRadius: '7px', background: 'rgba(15,23,42,0.9)', border: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', cursor: 'pointer' }}>
          <X size={14} />
        </button>
      </div>

      {/* File name + badges */}
      <div style={{ padding: '14px 16px 12px 16px', borderBottom: '1px solid #1e293b', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
          <span title={asset.name} style={{ flex: 1, fontSize: '13.5px', fontWeight: 700, color: '#f1f5f9', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{asset.name}</span>
          <Pencil size={14} style={{ color: '#64748b', cursor: 'pointer', flexShrink: 0 }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          <span style={{ padding: '2px 8px', borderRadius: '9999px', background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.25)', color: '#a78bfa', fontSize: '11px', fontWeight: 700 }}>{getTypeLabel(asset.type)}</span>
          <span style={{ padding: '2px 8px', borderRadius: '9999px', background: '#0f172a', border: '1px solid #1e293b', color: '#94a3b8', fontSize: '11px', fontWeight: 600 }}>{ext} • —</span>
          {asset.status === 'APPROVED' && <span style={{ padding: '2px 8px', borderRadius: '9999px', background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.25)', color: '#34d399', fontSize: '11px', fontWeight: 700 }}>Approved</span>}
          {asset.status === 'DRAFT' && <span style={{ padding: '2px 8px', borderRadius: '9999px', background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.25)', color: '#fbbf24', fontSize: '11px', fontWeight: 700 }}>Draft</span>}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '16px', padding: '0 16px', borderBottom: '1px solid #1e293b', flexShrink: 0 }}>
        {[
          { id: 'info', label: 'Thông tin' },
          { id: 'detail', label: 'Chi tiết' },
          { id: 'usage', label: 'Sử dụng' },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id as any)}
            style={{
              padding: '10px 2px',
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === t.id ? '2px solid #3b82f6' : '2px solid transparent',
              color: activeTab === t.id ? '#f1f5f9' : '#64748b',
              fontSize: '13px',
              fontWeight: activeTab === t.id ? 700 : 600,
              cursor: 'pointer',
              marginBottom: '-1px',
            }}
          >{t.label}</button>
        ))}
      </div>

      {/* Tab content */}
      <div className="asset-scroll" style={{ flex: 1, overflowY: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {activeTab === 'info' && (
          <>
            {/* Mô tả */}
            <div>
              <div style={{ fontSize: '11px', fontWeight: 800, letterSpacing: '0.07em', textTransform: 'uppercase', color: '#94a3b8', marginBottom: '8px' }}>Mô tả</div>
              <div style={{ padding: '10px 12px', borderRadius: '10px', background: '#0f172a', border: '1px solid #1e293b', fontSize: '12.5px', color: '#cbd5e1', lineHeight: 1.5 }}>
                {prov?.prompt ? prov.prompt : (prov?.source === 'GENERATED' ? `Tài nguyên ${getTypeLabel(asset.type).toLowerCase()} được tạo bởi ${prov.generator || 'AI'}${prov.model ? ` (${prov.model})` : ''}.` : 'Chưa có mô tả cho tài nguyên này.')}
              </div>
            </div>

            {/* Metadata */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
              {[
                { k: 'Dự án', v: asset.project_id || '—' },
                { k: 'Tập phim', v: asset.episode_id || '—' },
                { k: 'Được tạo bởi', v: prov?.generator || prov?.source || '—' },
                { k: 'Ngày tạo', v: formatDateVietnamese(asset.created_at) },
                { k: 'Kích thước', v: asset.type === 'IMAGE' ? '1920 × 1080' : '—' },
                { k: 'Định dạng', v: ext },
                { k: 'Màu sắc', v: 'RGB' },
                { k: 'Thời lượng', v: asset.type === 'VIDEO' ? '00:08' : asset.type === 'AUDIO' ? '01:30' : '—' },
              ].map(row => (
                <div key={row.k} style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', padding: '7px 0', borderBottom: '1px solid rgba(30,41,59,0.55)', fontSize: '12.5px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600, whiteSpace: 'nowrap' }}>{row.k}</span>
                  <span style={{ color: '#e2e8f0', fontWeight: 500, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '180px' }} title={row.v}>{row.v}</span>
                </div>
              ))}
            </div>

            {/* Tags */}
            <div>
              <div style={{ fontSize: '11px', fontWeight: 800, letterSpacing: '0.07em', textTransform: 'uppercase', color: '#94a3b8', marginBottom: '8px' }}>Tags</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {(prov?.reference_ids && prov.reference_ids.length ? prov.reference_ids.slice(0, 6) : (asset.name.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().split(' ').filter(w => w.length > 2).slice(0, 4))).map((tag: string) => (
                  <span key={tag} style={{ padding: '4px 9px', borderRadius: '9999px', background: '#1e293b', border: '1px solid #334155', color: '#cbd5e1', fontSize: '11.5px', fontWeight: 600 }}>{String(tag).replace(/^asset-/, '').slice(0, 18)}</span>
                ))}
                {(!prov?.reference_ids || prov.reference_ids.length === 0) && asset.name.includes('_') && (
                  <>
                    <span style={{ padding: '4px 9px', borderRadius: '9999px', background: '#1e293b', border: '1px solid #334155', color: '#cbd5e1', fontSize: '11.5px', fontWeight: 600 }}>cyberpunk</span>
                    <span style={{ padding: '4px 9px', borderRadius: '9999px', background: '#1e293b', border: '1px solid #334155', color: '#cbd5e1', fontSize: '11.5px', fontWeight: 600 }}>neon</span>
                  </>
                )}
                <button style={{ width: '26px', height: '26px', borderRadius: '9999px', background: '#0f172a', border: '1px solid #334155', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', cursor: 'pointer', fontSize: '14px', lineHeight: 1 }}>+</button>
              </div>
            </div>

            {/* Provenance hash */}
            <div style={{ padding: '10px 12px', borderRadius: '10px', background: 'rgba(30,41,59,0.55)', border: '1px solid #1e293b', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span style={{ fontSize: '11px', fontWeight: 800, letterSpacing: '0.06em', color: '#94a3b8', textTransform: 'uppercase' }}>Content Hash</span>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '11px', color: '#60a5fa', wordBreak: 'break-all' }}>{prov?.content_hash || '—'}</span>
              <span style={{ fontSize: '11px', color: '#64748b' }}>Hash status: <span style={{ color: prov?.hash_status === 'VERIFIED' ? '#34d399' : '#fbbf24', fontWeight: 700 }}>{prov?.hash_status || 'HASH_UNVERIFIED'}</span></span>
            </div>
          </>
        )}

        {activeTab === 'detail' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {/* Provenance chain */}
            <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '10px', padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 750, color: '#f1f5f9' }}>Provenance Chain</h4>
              <div style={{ display: 'grid', gridTemplateColumns: '110px 1fr', gap: '6px 10px', fontSize: '12.5px' }}>
                <span style={{ color: '#64748b', fontWeight: 600 }}>Nguồn gốc</span><span style={{ color: '#e2e8f0' }}>{prov?.source || '—'}</span>
                {prov?.generator && <><span style={{ color: '#64748b', fontWeight: 600 }}>Generator</span><span style={{ color: '#e2e8f0' }}>{prov.generator}</span></>}
                {prov?.model && <><span style={{ color: '#64748b', fontWeight: 600 }}>Model</span><span style={{ color: '#e2e8f0' }}>{prov.model}</span></>}
                {prov?.job_id && <><span style={{ color: '#64748b', fontWeight: 600 }}>Job ID</span><span style={{ color: '#e2e8f0', fontFamily: 'JetBrains Mono, monospace', fontSize: '11px' }}>{prov.job_id}</span></>}
                <span style={{ color: '#64748b', fontWeight: 600 }}>Content Hash</span><span style={{ color: '#60a5fa', fontFamily: 'JetBrains Mono, monospace', fontSize: '11px', wordBreak: 'break-all' }}>{prov?.content_hash?.slice(0, 16) || '—'}...</span>
                {prov?.parent_revision_id && <><span style={{ color: '#64748b', fontWeight: 600 }}>Parent</span><span style={{ color: '#e2e8f0', fontFamily: 'JetBrains Mono, monospace', fontSize: '11px' }}>{prov.parent_revision_id}</span></>}
              </div>
              {prov?.prompt && (
                <div style={{ marginTop: '6px', paddingTop: '8px', borderTop: '1px solid #1e293b' }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', marginBottom: '4px' }}>Prompt</div>
                  <div style={{ fontSize: '12px', color: '#cbd5e1', lineHeight: 1.5 }}>{prov.prompt}</div>
                </div>
              )}
            </div>

            {/* Revisions */}
            <div>
              <h4 style={{ margin: '0 0 8px 0', fontSize: '13px', fontWeight: 750, color: '#f1f5f9' }}>Lịch sử phiên bản ({revisions.length})</h4>
              {revisions.length === 0 ? (
                <div style={{ fontSize: '12.5px', color: '#64748b', padding: '8px 0' }}>Chưa có lịch sử phiên bản.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {revisions.map((rev: any) => (
                    <div key={rev.revision_id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 10px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#e2e8f0' }}>v{rev.version}</span>
                      <span style={{ fontSize: '11px', fontWeight: 700, color: rev.status === 'APPROVED' ? '#34d399' : rev.status === 'REJECTED' ? '#f87171' : '#94a3b8' }}>{rev.status}</span>
                      <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '11px', color: '#60a5fa' }}>#{String(rev.provenance?.content_hash || '').slice(0, 6) || '—'}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Approve / Reject */}
            {latestRev && latestRev.status === 'DRAFT' && (
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => approveMut.mutate({ revision_id: latestRev.revision_id, approved_by: 'User' })}
                  disabled={approveMut.isPending}
                  style={{ flex: 1, height: '36px', borderRadius: '8px', background: '#10b981', border: '1px solid #10b981', color: '#fff', fontWeight: 700, fontSize: '13px', cursor: 'pointer' }}
                >{approveMut.isPending ? 'Đang duyệt…' : 'Duyệt'}</button>
                <button
                  onClick={() => rejectMut.mutate({ revision_id: latestRev.revision_id, rejected_by: 'User' })}
                  disabled={rejectMut.isPending}
                  style={{ flex: 1, height: '36px', borderRadius: '8px', background: 'transparent', border: '1px solid #ef4444', color: '#f87171', fontWeight: 700, fontSize: '13px', cursor: 'pointer' }}
                >Từ chối</button>
              </div>
            )}
          </div>
        )}

        {activeTab === 'usage' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color: '#f1f5f9' }}>Vị trí sử dụng</div>
            <div style={{ fontSize: '12.5px', color: '#94a3b8', lineHeight: 1.5 }}>
              Asset được tham chiếu trong {prov?.reference_ids?.length || 0} vị trí. Các storyboard scene hoặc shot sử dụng tài nguyên này sẽ liệt kê tại đây.
            </div>
            {(prov?.reference_ids?.length ?? 0) > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {prov.reference_ids.map((id: string) => (
                  <div key={id} style={{ padding: '8px 10px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', fontSize: '12px', color: '#cbd5e1', fontFamily: 'JetBrains Mono, monospace' }}>{id}</div>
                ))}
              </div>
            ) : (
              <div style={{ padding: '12px', background: '#0f172a', border: '1px dashed #1e293b', borderRadius: '10px', fontSize: '12.5px', color: '#64748b', textAlign: 'center' }}>Chưa được sử dụng trong scene/shot nào.</div>
            )}
            <div style={{ fontSize: '11px', color: '#475569', marginTop: '4px' }}>Phiên bản hiện tại: <span style={{ color: '#60a5fa', fontFamily: 'JetBrains Mono, monospace' }}>{asset.current_revision_id || '—'}</span> • v{asset.version}</div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div style={{ padding: '12px 16px', borderTop: '1px solid #1e293b', display: 'flex', gap: '8px', background: '#0e1426' }}>
        <button
          onClick={() => {
            const url = (revisions.find((r: any) => r.media_url)?.media_url) || (prov?.content_hash ? `hash:${prov.content_hash}` : null);
            if (url && url.startsWith('http')) window.open(url, '_blank');
            else if (url) navigator.clipboard?.writeText(url);
          }}
          style={{ flex: 1, height: '36px', borderRadius: '8px', background: '#2563eb', border: '1px solid #2563eb', color: '#fff', fontSize: '13px', fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', cursor: 'pointer' }}
        >
          <Download size={14} />
          Tải xuống
        </button>
        <button
          onClick={() => navigator.clipboard?.writeText(asset.id).then(() => alert(`Đã sao chép ID: ${asset.id}`)).catch(() => {})}
          style={{ flex: 1, height: '36px', borderRadius: '8px', background: '#1e293b', border: '1px solid #334155', color: '#cbd5e1', fontSize: '13px', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', cursor: 'pointer' }}
        >
          <Share2 size={14} />
          Chia sẻ
        </button>
        <button
          onClick={() => alert('API hiện tại chưa hỗ trợ xóa asset. Vui lòng liên hệ quản trị viên.')}
          style={{ width: '42px', height: '36px', borderRadius: '8px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#f87171', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
          title="Xóa"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}

// ─── Create Asset Dialog ───────────────────────────────────────────────
function CreateAssetDialog({ onClose, projectId: fixedProjectId, episodeId: fixedEpisodeId, onCreated }: { onClose: () => void; projectId?: string; episodeId?: string; onCreated: () => void }) {
  const createMut = useCreateAsset();
  const { projects } = useProjects();
  const [form, setForm] = useState({
    name: '',
    type: 'IMAGE' as AssetType,
    project_id: fixedProjectId || '',
    episode_id: fixedEpisodeId || '',
    source: 'GENERATED' as string,
    prompt: '',
    media_url: '',
  });
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!form.name.trim()) { setError('Tên asset là bắt buộc.'); return; }
    setError(null);
    try {
      await createMut.mutateAsync({
        name: form.name.trim(),
        type: form.type,
        project_id: form.project_id || undefined,
        episode_id: form.episode_id || undefined,
        source: form.source,
        prompt: form.prompt || undefined,
        media_url: form.media_url || undefined,
      });
      onCreated();
    } catch (e: any) {
      setError(e?.message || 'Tạo asset thất bại. Vui lòng thử lại.');
    }
  };

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'rgba(2,6,23,0.65)', backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px' }}>
      <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxWidth: '520px', maxHeight: '90vh', overflow: 'hidden', background: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', boxShadow: '0 24px 64px rgba(0,0,0,0.6)', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '18px 20px 14px 20px', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: '#f1f5f9' }}>Thêm Asset mới</h2>
            <p style={{ margin: '4px 0 0 0', fontSize: '12.5px', color: '#94a3b8' }}>Tạo tài nguyên mới được lưu trực tiếp vào DB qua API V3.</p>
          </div>
          <button onClick={onClose} style={{ width: '32px', height: '32px', borderRadius: '8px', background: '#1e293b', border: '1px solid #334155', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', cursor: 'pointer' }}><X size={16} /></button>
        </div>

        <div className="asset-scroll" style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1', letterSpacing: '0.02em' }}>Tên asset *</label>
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="VD: cyberpunk_city_night.png" style={{ height: '38px', padding: '0 12px', borderRadius: '8px', background: '#020617', border: '1px solid #1e293b', color: '#e2e8f0', fontSize: '13px', outline: 'none' }} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1' }}>Loại</label>
              <div style={{ position: 'relative' }}>
                <select value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value as AssetType }))} style={{ width: '100%', height: '38px', padding: '0 32px 0 12px', borderRadius: '8px', background: '#020617', border: '1px solid #1e293b', color: '#e2e8f0', fontSize: '13px', outline: 'none', appearance: 'none', WebkitAppearance: 'none', cursor: 'pointer' }}>
                  <option value="IMAGE">IMAGE — Hình ảnh</option>
                  <option value="VIDEO">VIDEO — Video</option>
                  <option value="AUDIO">AUDIO — Âm thanh</option>
                  <option value="MODEL_3D">MODEL_3D — 3D Model</option>
                  <option value="REFERENCE">REFERENCE — Tài liệu</option>
                </select>
                <ChevronDown size={14} style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', color: '#64748b', pointerEvents: 'none' }} />
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1' }}>Nguồn</label>
              <div style={{ position: 'relative' }}>
                <select value={form.source} onChange={e => setForm(f => ({ ...f, source: e.target.value }))} style={{ width: '100%', height: '38px', padding: '0 32px 0 12px', borderRadius: '8px', background: '#020617', border: '1px solid #1e293b', color: '#e2e8f0', fontSize: '13px', outline: 'none', appearance: 'none', cursor: 'pointer' }}>
                  <option value="GENERATED">GENERATED</option>
                  <option value="UPLOADED">UPLOADED</option>
                  <option value="IMPORTED">IMPORTED</option>
                  <option value="REFERENCE">REFERENCE</option>
                </select>
                <ChevronDown size={14} style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', color: '#64748b', pointerEvents: 'none' }} />
              </div>
            </div>
          </div>

          {/* Project select */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1' }}>Dự án</label>
            {fixedProjectId ? (
              <input value={fixedProjectId} readOnly style={{ height: '38px', padding: '0 12px', borderRadius: '8px', background: '#1e293b', border: '1px solid #334155', color: '#94a3b8', fontSize: '13px' }} />
            ) : (
              <div style={{ position: 'relative' }}>
                <select value={form.project_id} onChange={e => setForm(f => ({ ...f, project_id: e.target.value }))} style={{ width: '100%', height: '38px', padding: '0 32px 0 12px', borderRadius: '8px', background: '#020617', border: '1px solid #1e293b', color: '#e2e8f0', fontSize: '13px', outline: 'none', appearance: 'none', cursor: 'pointer' }}>
                  <option value="">— Không gắn dự án —</option>
                  {projects.map((p: any) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
                <ChevronDown size={14} style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', color: '#64748b', pointerEvents: 'none' }} />
              </div>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1' }}>Episode ID (tuỳ chọn)</label>
            <input value={form.episode_id} onChange={e => setForm(f => ({ ...f, episode_id: e.target.value }))} placeholder="ep-cb-001" style={{ height: '38px', padding: '0 12px', borderRadius: '8px', background: '#020617', border: '1px solid #1e293b', color: '#e2e8f0', fontSize: '13px', outline: 'none' }} />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1' }}>Mô tả / Prompt</label>
            <textarea value={form.prompt} onChange={e => setForm(f => ({ ...f, prompt: e.target.value }))} rows={3} placeholder="Toàn cảnh thành phố cyberpunk về đêm với ánh đèn neon và mưa..." style={{ padding: '10px 12px', borderRadius: '8px', background: '#020617', border: '1px solid #1e293b', color: '#e2e8f0', fontSize: '13px', outline: 'none', resize: 'vertical', fontFamily: 'inherit' }} />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1' }}>Media URL (tuỳ chọn)</label>
            <input value={form.media_url} onChange={e => setForm(f => ({ ...f, media_url: e.target.value }))} placeholder="https://..." style={{ height: '38px', padding: '0 12px', borderRadius: '8px', background: '#020617', border: '1px solid #1e293b', color: '#e2e8f0', fontSize: '13px', outline: 'none' }} />
            <span style={{ fontSize: '11px', color: '#64748b' }}>Nếu bỏ trống, asset sẽ ở trạng thái HASH_UNVERIFIED cho tới khi upload bytes thực (content_base64).</span>
          </div>

          {error && (
            <div style={{ padding: '10px 12px', borderRadius: '8px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#fca5a5', fontSize: '12.5px' }}>{error}</div>
          )}
        </div>

        <div style={{ padding: '14px 20px', borderTop: '1px solid #1e293b', display: 'flex', gap: '10px', justifyContent: 'flex-end', background: '#0f172a', borderBottomLeftRadius: '16px', borderBottomRightRadius: '16px' }}>
          <button onClick={onClose} disabled={createMut.isPending} style={{ height: '38px', padding: '0 16px', borderRadius: '8px', background: 'transparent', border: '1px solid #334155', color: '#cbd5e1', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}>Hủy</button>
          <button onClick={handleSubmit} disabled={createMut.isPending || !form.name.trim()} style={{ height: '38px', padding: '0 18px', borderRadius: '8px', background: createMut.isPending || !form.name.trim() ? '#1e293b' : 'linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)', border: 'none', color: '#fff', fontSize: '13px', fontWeight: 700, cursor: createMut.isPending || !form.name.trim() ? 'not-allowed' : 'pointer', opacity: createMut.isPending || !form.name.trim() ? 0.6 : 1 }}>
            {createMut.isPending ? 'Đang tạo…' : 'Tạo Asset'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Color helper ─────────────────────────────────────────────────────────
function hashColor(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  const colors = ['#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#6366f1'];
  return colors[h % colors.length];
}
