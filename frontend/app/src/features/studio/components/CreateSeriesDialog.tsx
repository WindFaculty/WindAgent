/**
 * CreateSeriesDialog — Modal to create a new canonical Studio Series.
 */

import React, { useState } from 'react';
import { Film, X } from 'lucide-react';
import { Button, Input, Textarea, Card } from '@windagent/ui';
import type { CreateSeriesInput } from '../hooks/useStudioSeries';

export interface CreateSeriesDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (input: CreateSeriesInput) => Promise<void>;
  initialData?: Partial<CreateSeriesInput>;
}

const GENRES = ['Sci-Fi', 'Fantasy', 'Cyberpunk', 'Action', 'Drama', 'Mystery', 'Animation', 'Horror'];
const TONES = ['Cinematic', 'Dark & Gritty', 'Heroic & Epic', 'Humorous & Satirical', 'Philosophical', 'Suspenseful'];
const AUDIENCES = [
  { id: '5-8', label: 'Thiếu nhi (5-8 tuổi)' },
  { id: '9-12', label: 'Thiếu niên (9-12 tuổi)' },
  { id: '13-17', label: 'Thanh thiếu niên (13-17 tuổi)' },
  { id: '18+', label: 'Trưởng thành (18+)' },
  { id: 'General', label: 'Mọi lứa tuổi (General)' },
];

export const CreateSeriesDialog: React.FC<CreateSeriesDialogProps> = ({
  isOpen,
  onClose,
  onSubmit,
  initialData,
}) => {
  const [title, setTitle] = useState(initialData?.title || '');
  const [description, setDescription] = useState(initialData?.description || '');
  const [genre, setGenre] = useState(initialData?.genre || 'Sci-Fi');
  const [tone, setTone] = useState(initialData?.tone || 'Cinematic');
  const [targetAudience, setTargetAudience] = useState(initialData?.target_audience || '13-17');
  const [language, setLanguage] = useState(initialData?.language || 'vi');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  React.useEffect(() => {
    if (initialData) {
      if (initialData.title) setTitle(initialData.title);
      if (initialData.description) setDescription(initialData.description);
      if (initialData.genre) setGenre(initialData.genre);
      if (initialData.tone) setTone(initialData.tone);
      if (initialData.target_audience) setTargetAudience(initialData.target_audience);
      if (initialData.language) setLanguage(initialData.language);
    }
  }, [initialData]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError('Vui lòng nhập tên Series/Dự án phim.');
      return;
    }

    setError(null);
    setIsSubmitting(true);
    try {
      await onSubmit({
        title: title.trim(),
        description: description.trim(),
        genre,
        tone,
        target_audience: targetAudience,
        language,
      });
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Không thể tạo Series mới.');
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
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}
      data-testid="create-series-dialog"
    >
      <Card
        style={{
          width: '100%',
          maxWidth: '560px',
          background: 'var(--bg-panel, #0f172a)',
          border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.12))',
          borderRadius: '20px',
          padding: '28px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.6)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '10px',
                background: 'rgba(59, 130, 246, 0.15)',
                color: '#3b82f6',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Film size={18} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>
                Tạo Series Phim Mới
              </h3>
              <span style={{ fontSize: '12px', color: '#94a3b8' }}>
                Định hình vũ trụ điện ảnh và định hướng phong cách sáng tạo
              </span>
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer',
              padding: '6px',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {error && (
          <div
            style={{
              padding: '10px 14px',
              borderRadius: '8px',
              background: 'rgba(239, 68, 68, 0.15)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: '#f87171',
              fontSize: '13px',
              marginBottom: '16px',
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
              Tên Series / Dự Án Phim <span style={{ color: '#f87171' }}>*</span>
            </label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="VD: Cyberpunk 2099: Thành Phố Không Ngủ"
              style={{ width: '100%', background: 'var(--bg-canvas, #020617)' }}
              autoFocus
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
              Mô Tả Tổng Quan & Tiền Đề Vũ Trụ
            </label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Mô tả bối cảnh, câu chuyện tổng thể hoặc thông điệp của toàn bộ series..."
              rows={3}
              style={{ width: '100%', background: 'var(--bg-canvas, #020617)' }}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                Thể Loại (Genre)
              </label>
              <select
                value={genre}
                onChange={(e) => setGenre(e.target.value)}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '8px',
                  background: 'var(--bg-canvas, #020617)',
                  border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.12))',
                  color: '#f8fafc',
                  fontSize: '13px',
                }}
              >
                {GENRES.map((g) => (
                  <option key={g} value={g} style={{ background: '#0f172a' }}>
                    {g}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                Âm Hưởng / Tone
              </label>
              <select
                value={tone}
                onChange={(e) => setTone(e.target.value)}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '8px',
                  background: 'var(--bg-canvas, #020617)',
                  border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.12))',
                  color: '#f8fafc',
                  fontSize: '13px',
                }}
              >
                {TONES.map((t) => (
                  <option key={t} value={t} style={{ background: '#0f172a' }}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                Khán Giả Mục Tiêu
              </label>
              <select
                value={targetAudience}
                onChange={(e) => setTargetAudience(e.target.value)}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '8px',
                  background: 'var(--bg-canvas, #020617)',
                  border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.12))',
                  color: '#f8fafc',
                  fontSize: '13px',
                }}
              >
                {AUDIENCES.map((a) => (
                  <option key={a.id} value={a.id} style={{ background: '#0f172a' }}>
                    {a.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                Ngôn Ngữ
              </label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '8px',
                  background: 'var(--bg-canvas, #020617)',
                  border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.12))',
                  color: '#f8fafc',
                  fontSize: '13px',
                }}
              >
                <option value="vi" style={{ background: '#0f172a' }}>Tiếng Việt (vi)</option>
                <option value="en" style={{ background: '#0f172a' }}>English (en)</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '12px' }}>
            <Button type="button" variant="ghost" onClick={onClose} disabled={isSubmitting}>
              Hủy
            </Button>
            <Button type="submit" variant="primary" disabled={isSubmitting}>
              {isSubmitting ? 'Đang tạo...' : 'Tạo Series Mới'}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};
