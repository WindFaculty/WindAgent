/**
 * CreateProjectDialog — Modal for creating a new canonical project.
 */

import React, { useState } from 'react';
import { X, FolderPlus } from 'lucide-react';
import { Button, Input, Textarea } from '@windagent/ui';

import type { CreateProjectInput } from '../hooks/useCreateProject';

export interface CreateProjectDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (input: CreateProjectInput) => Promise<any>;
  initialData?: Partial<CreateProjectInput>;
}

const GENRE_OPTIONS = [
  { value: 'Cyberpunk / Sci-Fi', label: 'Cyberpunk / Sci-Fi' },
  { value: 'High Fantasy / Adventure', label: 'High Fantasy / Adventure' },
  { value: 'Drama / Mystery Noir', label: 'Drama / Mystery Noir' },
  { value: 'Thriller / Psychological', label: 'Thriller / Psychological' },
  { value: 'Animation / Epic Saga', label: 'Animation / Epic Saga' },
  { value: 'Slice of Life / Comedy', label: 'Slice of Life / Comedy' },
];

export const CreateProjectDialog: React.FC<CreateProjectDialogProps> = ({
  isOpen,
  onClose,
  onSubmit,
  initialData,
}) => {
  const [name, setName] = useState(initialData?.name ?? '');
  const [description, setDescription] = useState(initialData?.description ?? '');
  const [genre, setGenre] = useState(initialData?.genre ?? 'Cyberpunk / Sci-Fi');
  const [initialEpisode, setInitialEpisode] = useState(initialData?.initial_episode_title ?? 'Tập 01: Khởi Đầu');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Sync initialData changes if opened with template
  React.useEffect(() => {
    if (isOpen && initialData) {
      if (initialData.name) setName(initialData.name);
      if (initialData.description) setDescription(initialData.description);
      if (initialData.genre) setGenre(initialData.genre);
      if (initialData.initial_episode_title) setInitialEpisode(initialData.initial_episode_title);
    }
  }, [isOpen, initialData]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setErrorMsg('Vui lòng nhập tên dự án.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      await onSubmit({
        name: name.trim(),
        description: description.trim() || undefined,
        genre,
        initial_episode_title: initialEpisode.trim() || undefined,
      });
      onClose();
    } catch (err: any) {
      setErrorMsg(err?.message || 'Không thể tạo dự án. Vui lòng thử lại.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '540px',
          background: 'var(--bg-panel, #0f172a)',
          border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.12))',
          borderRadius: '16px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.6)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '10px',
                background: 'rgba(59, 130, 246, 0.15)',
                color: 'var(--color-primary, #3b82f6)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <FolderPlus size={20} />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: 'var(--text-primary, #f8fafc)' }}>
                Tạo dự án mới
              </h2>
              <span style={{ fontSize: '12px', color: 'var(--text-muted, #94a3b8)' }}>
                Khởi tạo không gian kịch bản và sản xuất phim AI
              </span>
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted, #94a3b8)',
              cursor: 'pointer',
              padding: '4px',
              borderRadius: '6px',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body Form */}
        <form onSubmit={handleSubmit} style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {errorMsg && (
            <div
              style={{
                padding: '10px 14px',
                borderRadius: '8px',
                background: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                color: '#f87171',
                fontSize: '13px',
              }}
            >
              {errorMsg}
            </div>
          )}

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary, #e2e8f0)', marginBottom: '6px' }}>
              Tên dự án <span style={{ color: '#f87171' }}>*</span>
            </label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="VD: Cyberpunk Odyssey 2099..."
              autoFocus
              required
              style={{
                width: '100%',
                background: 'var(--bg-canvas, #020617)',
                borderColor: 'var(--border-subtle, rgba(255, 255, 255, 0.12))',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary, #e2e8f0)', marginBottom: '6px' }}>
              Thể loại chính
            </label>
            <select
              value={genre}
              onChange={(e) => setGenre(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: '8px',
                background: 'var(--bg-canvas, #020617)',
                border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.12))',
                color: 'var(--text-primary, #f8fafc)',
                fontSize: '14px',
                outline: 'none',
              }}
            >
              {GENRE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value} style={{ background: '#0f172a' }}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary, #e2e8f0)', marginBottom: '6px' }}>
              Mô tả / Logline
            </label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Tóm tắt bối cảnh, chủ đề chính hoặc ý tưởng tổng quan của phim..."
              rows={3}
              style={{
                width: '100%',
                background: 'var(--bg-canvas, #020617)',
                borderColor: 'var(--border-subtle, rgba(255, 255, 255, 0.12))',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary, #e2e8f0)', marginBottom: '6px' }}>
              Tên tập phim đầu tiên (Tập 01)
            </label>
            <Input
              value={initialEpisode}
              onChange={(e) => setInitialEpisode(e.target.value)}
              placeholder="VD: Tập 01: Mã Nguồn Thức Tỉnh"
              style={{
                width: '100%',
                background: 'var(--bg-canvas, #020617)',
                borderColor: 'var(--border-subtle, rgba(255, 255, 255, 0.12))',
              }}
            />
          </div>

          {/* Modal Footer Actions */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: '12px',
              marginTop: '12px',
              paddingTop: '16px',
              borderTop: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
            }}
          >
            <Button variant="ghost" type="button" onClick={onClose} disabled={isSubmitting}>
              Hủy
            </Button>
            <Button variant="primary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Đang tạo...' : 'Tạo dự án'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
