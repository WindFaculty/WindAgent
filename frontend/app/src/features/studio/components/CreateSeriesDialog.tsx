/**
 * CreateSeriesDialog — Cinematic modal matching reference mock [Image 1].
 * Glassmorphism + neon border + inner icons + 2x2 selects grid + gradient CTA.
 */
import React, { useState } from 'react';
import { Film, X, Tag, FileText, Orbit, Star, Users, Globe, ChevronDown, Sparkles } from 'lucide-react';
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

export const CreateSeriesDialog: React.FC<CreateSeriesDialogProps> = ({ isOpen, onClose, onSubmit, initialData }) => {
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

  // close on backdrop
  const onBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div
      onClick={onBackdropClick}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'rgba(3, 7, 18, 0.78)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}
      data-testid="create-series-dialog"
    >
      {/* outer glow soft blobs — mimics mock blurred background */}
      <div
        aria-hidden
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            position: 'absolute',
            width: '480px',
            height: '480px',
            left: '8%',
            top: '12%',
            background: 'radial-gradient(ellipse at center, rgba(59,130,246,0.12), transparent 70%)',
            filter: 'blur(30px)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            width: '520px',
            height: '520px',
            right: '6%',
            bottom: '8%',
            background: 'radial-gradient(ellipse at center, rgba(139,92,246,0.13), transparent 70%)',
            filter: 'blur(30px)',
          }}
        />
      </div>

      {/* modal card */}
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '640px',
          maxHeight: '90vh',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          borderRadius: '20px',
          border: '1px solid rgba(108, 122, 255, 0.28)',
          background:
            'radial-gradient(900px 320px at 50% -15%, rgba(99,102,241,0.18), transparent 60%), linear-gradient(180deg, #16223d 0%, #0f172a 55%, #0b1224 100%)',
          boxShadow:
            '0 0 0 1px rgba(99,102,241,0.12) inset, 0 0 40px rgba(59,130,246,0.18), 0 0 80px rgba(139,92,246,0.12), 0 25px 60px rgba(0,0,0,0.65)',
          position: 'relative',
        }}
      >
        {/* top hairline glow */}
        <div
          aria-hidden
          style={{
            position: 'absolute',
            top: 0,
            left: '6%',
            right: '6%',
            height: '1px',
            background: 'linear-gradient(90deg, transparent, rgba(148,163,255,0.55), transparent)',
            pointerEvents: 'none',
          }}
        />
        {/* left/right edge glow */}
        <div
          aria-hidden
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '20px',
            border: '1px solid transparent',
            background: 'linear-gradient(180deg, rgba(99,102,241,0.25), rgba(59,130,246,0.12) 40%, transparent 75%) border-box',
            WebkitMask: 'linear-gradient(#fff 0 0) padding-box, linear-gradient(#fff 0 0)',
            WebkitMaskComposite: 'xor' as any,
            maskComposite: 'exclude' as any,
            pointerEvents: 'none',
            opacity: 0.9,
          }}
        />

        {/* header */}
        <div style={{ padding: '22px 22px 14px 22px', display: 'flex', alignItems: 'flex-start', gap: '14px', position: 'relative' }}>
          <div
            style={{
              width: '52px',
              height: '52px',
              borderRadius: '50%',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'radial-gradient(ellipse at 30% 20%, rgba(99,102,241,0.35), rgba(15,23,42,0.95))',
              border: '1.5px solid rgba(99,102,241,0.45)',
              boxShadow: '0 0 18px rgba(99,102,241,0.45), 0 0 36px rgba(59,130,246,0.25) inset',
              color: '#a5b4fc',
            }}
          >
            <Film size={22} strokeWidth={1.9} />
          </div>
          <div style={{ flex: 1, minWidth: 0, paddingTop: '2px' }}>
            <h2 style={{ margin: 0, fontSize: '22px', fontWeight: 800, color: '#f1f5f9', letterSpacing: '-0.4px', lineHeight: 1.2 }}>
              Tạo Series Phim Mới
            </h2>
            <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#94a3b8', fontWeight: 500, lineHeight: 1.4 }}>
              Định hình vũ trụ điện ảnh và định hướng phong cách sáng tạo
            </p>
          </div>

          <button
            aria-label="Đóng"
            onClick={onClose}
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '50%',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(15, 23, 42, 0.9)',
              border: '1px solid rgba(255,255,255,0.12)',
              color: '#cbd5e1',
              cursor: 'pointer',
              boxShadow: '0 2px 10px rgba(0,0,0,0.4)',
              transition: 'background 0.15s, border-color 0.15s',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = 'rgba(30,41,59,0.95)';
              (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.2)';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = 'rgba(15,23,42,0.9)';
              (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.12)';
            }}
          >
            <X size={16} strokeWidth={2.2} />
          </button>
        </div>

        {/* body scroll */}
        <form
          onSubmit={handleSubmit}
          style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}
        >
          <div style={{ padding: '6px 22px 18px 22px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {error && (
              <div
                style={{
                  padding: '10px 14px',
                  borderRadius: '10px',
                  background: 'rgba(239,68,68,0.10)',
                  border: '1px solid rgba(239,68,68,0.28)',
                  color: '#fecaca',
                  fontSize: '13px',
                  lineHeight: 1.4,
                }}
              >
                {error}
              </div>
            )}

            {/* Tên Series */}
            <div>
              <label style={{ display: 'block', fontSize: '13.5px', fontWeight: 700, color: '#f1f5f9', marginBottom: '8px', letterSpacing: '0.1px' }}>
                Tên Series / Dự Án Phim <span style={{ color: '#f87171' }}>*</span>
              </label>
              <div style={{ position: 'relative' }}>
                <span
                  style={{
                    position: 'absolute',
                    left: '12px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    color: '#8b7dff',
                    display: 'flex',
                    pointerEvents: 'none',
                  }}
                >
                  <Tag size={18} strokeWidth={2} />
                </span>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="VD: Cyberpunk 2099: Thành Phố Không Ngủ"
                  autoFocus
                  style={{
                    width: '100%',
                    height: '48px',
                    padding: '0 14px 0 42px',
                    borderRadius: '12px',
                    background: 'rgba(15, 27, 54, 0.95)',
                    border: '1px solid rgba(96, 110, 180, 0.55)',
                    color: '#f1f5f9',
                    fontSize: '14px',
                    fontWeight: 500,
                    outline: 'none',
                    boxShadow: '0 0 0 1px rgba(99,102,241,0.08) inset',
                    transition: 'border-color 0.15s, box-shadow 0.15s',
                  }}
                  onFocus={(e) => {
                    (e.target as HTMLInputElement).style.borderColor = '#6366f1';
                    (e.target as HTMLInputElement).style.boxShadow = '0 0 0 3px rgba(99,102,241,0.25), 0 0 18px rgba(99,102,241,0.18)';
                  }}
                  onBlur={(e) => {
                    (e.target as HTMLInputElement).style.borderColor = 'rgba(96,110,180,0.55)';
                    (e.target as HTMLInputElement).style.boxShadow = '0 0 0 1px rgba(99,102,241,0.08) inset';
                  }}
                />
              </div>
            </div>

            {/* Mô tả */}
            <div>
              <label style={{ display: 'block', fontSize: '13.5px', fontWeight: 700, color: '#f1f5f9', marginBottom: '8px' }}>
                Mô Tả Tổng Quan & Tiền Đề Vũ Trụ
              </label>
              <div style={{ position: 'relative' }}>
                <span
                  style={{
                    position: 'absolute',
                    left: '12px',
                    top: '14px',
                    color: '#8b7dff',
                    display: 'flex',
                    pointerEvents: 'none',
                  }}
                >
                  <FileText size={18} strokeWidth={2} />
                </span>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Mô tả bối cảnh, câu chuyện tổng thể hoặc thông điệp của toàn bộ series..."
                  rows={4}
                  style={{
                    width: '100%',
                    minHeight: '118px',
                    padding: '13px 14px 14px 42px',
                    borderRadius: '12px',
                    background: 'rgba(15, 27, 54, 0.95)',
                    border: '1px solid rgba(96, 110, 180, 0.55)',
                    color: '#f1f5f9',
                    fontSize: '14px',
                    fontWeight: 400,
                    lineHeight: 1.5,
                    outline: 'none',
                    resize: 'vertical',
                    fontFamily: 'inherit',
                    boxShadow: '0 0 0 1px rgba(99,102,241,0.08) inset',
                    transition: 'border-color 0.15s, box-shadow 0.15s',
                  }}
                  onFocus={(e) => {
                    (e.target as HTMLTextAreaElement).style.borderColor = '#6366f1';
                    (e.target as HTMLTextAreaElement).style.boxShadow = '0 0 0 3px rgba(99,102,241,0.25), 0 0 18px rgba(99,102,241,0.18)';
                  }}
                  onBlur={(e) => {
                    (e.target as HTMLTextAreaElement).style.borderColor = 'rgba(96,110,180,0.55)';
                    (e.target as HTMLTextAreaElement).style.boxShadow = '0 0 0 1px rgba(99,102,241,0.08) inset';
                  }}
                />
                {/* resize handle subtle mimic */}
                <span
                  aria-hidden
                  style={{
                    position: 'absolute',
                    right: '10px',
                    bottom: '10px',
                    width: '10px',
                    height: '10px',
                    background:
                      'linear-gradient(135deg, transparent 30%, rgba(148,163,255,0.35) 30%, rgba(148,163,255,0.35) 45%, transparent 45%, transparent 60%, rgba(148,163,255,0.35) 60%, rgba(148,163,255,0.35) 75%, transparent 75%)',
                    opacity: 0.5,
                    pointerEvents: 'none',
                  }}
                />
              </div>
            </div>

            {/* 2x2 selects */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              {/* Genre */}
              <div>
                <label style={{ display: 'block', fontSize: '13.5px', fontWeight: 700, color: '#f1f5f9', marginBottom: '8px' }}>
                  Thể Loại (Genre)
                </label>
                <div style={{ position: 'relative' }}>
                  <span style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#8b7dff', display: 'flex', pointerEvents: 'none' }}>
                    <Orbit size={18} strokeWidth={2} />
                  </span>
                  <select
                    value={genre}
                    onChange={(e) => setGenre(e.target.value)}
                    style={{
                      width: '100%',
                      height: '46px',
                      padding: '0 36px 0 42px',
                      borderRadius: '12px',
                      background: 'rgba(15, 27, 54, 0.95)',
                      border: '1px solid rgba(96, 110, 180, 0.55)',
                      color: '#e2e8f0',
                      fontSize: '14px',
                      fontWeight: 500,
                      outline: 'none',
                      appearance: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    {GENRES.map((g) => (
                      <option key={g} value={g} style={{ background: '#0f172a' }}>
                        {g}
                      </option>
                    ))}
                  </select>
                  <span style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', pointerEvents: 'none', display: 'flex' }}>
                    <ChevronDown size={18} strokeWidth={2} />
                  </span>
                </div>
              </div>

              {/* Tone */}
              <div>
                <label style={{ display: 'block', fontSize: '13.5px', fontWeight: 700, color: '#f1f5f9', marginBottom: '8px' }}>
                  Âm Hưởng / Tone
                </label>
                <div style={{ position: 'relative' }}>
                  <span style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#8b7dff', display: 'flex', pointerEvents: 'none' }}>
                    <Star size={18} strokeWidth={2} fill="currentColor" style={{ fill: '#8b7dff', opacity: 0.95 }} />
                  </span>
                  <select
                    value={tone}
                    onChange={(e) => setTone(e.target.value)}
                    style={{
                      width: '100%',
                      height: '46px',
                      padding: '0 36px 0 42px',
                      borderRadius: '12px',
                      background: 'rgba(15, 27, 54, 0.95)',
                      border: '1px solid rgba(96, 110, 180, 0.55)',
                      color: '#e2e8f0',
                      fontSize: '14px',
                      fontWeight: 500,
                      outline: 'none',
                      appearance: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    {TONES.map((t) => (
                      <option key={t} value={t} style={{ background: '#0f172a' }}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <span style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', pointerEvents: 'none', display: 'flex' }}>
                    <ChevronDown size={18} strokeWidth={2} />
                  </span>
                </div>
              </div>

              {/* Audience */}
              <div>
                <label style={{ display: 'block', fontSize: '13.5px', fontWeight: 700, color: '#f1f5f9', marginBottom: '8px' }}>
                  Khán Giả Mục Tiêu
                </label>
                <div style={{ position: 'relative' }}>
                  <span style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#8b7dff', display: 'flex', pointerEvents: 'none' }}>
                    <Users size={18} strokeWidth={2} />
                  </span>
                  <select
                    value={targetAudience}
                    onChange={(e) => setTargetAudience(e.target.value)}
                    style={{
                      width: '100%',
                      height: '46px',
                      padding: '0 36px 0 42px',
                      borderRadius: '12px',
                      background: 'rgba(15, 27, 54, 0.95)',
                      border: '1px solid rgba(96, 110, 180, 0.55)',
                      color: '#e2e8f0',
                      fontSize: '14px',
                      fontWeight: 500,
                      outline: 'none',
                      appearance: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    {AUDIENCES.map((a) => (
                      <option key={a.id} value={a.id} style={{ background: '#0f172a' }}>
                        {a.label}
                      </option>
                    ))}
                  </select>
                  <span style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', pointerEvents: 'none', display: 'flex' }}>
                    <ChevronDown size={18} strokeWidth={2} />
                  </span>
                </div>
              </div>

              {/* Language */}
              <div>
                <label style={{ display: 'block', fontSize: '13.5px', fontWeight: 700, color: '#f1f5f9', marginBottom: '8px' }}>
                  Ngôn Ngữ
                </label>
                <div style={{ position: 'relative' }}>
                  <span style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#8b7dff', display: 'flex', pointerEvents: 'none' }}>
                    <Globe size={18} strokeWidth={2} />
                  </span>
                  <select
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    style={{
                      width: '100%',
                      height: '46px',
                      padding: '0 36px 0 42px',
                      borderRadius: '12px',
                      background: 'rgba(15, 27, 54, 0.95)',
                      border: '1px solid rgba(96, 110, 180, 0.55)',
                      color: '#e2e8f0',
                      fontSize: '14px',
                      fontWeight: 500,
                      outline: 'none',
                      appearance: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    <option value="vi" style={{ background: '#0f172a' }}>
                      Tiếng Việt (vi)
                    </option>
                    <option value="en" style={{ background: '#0f172a' }}>
                      English (en)
                    </option>
                  </select>
                  <span style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', pointerEvents: 'none', display: 'flex' }}>
                    <ChevronDown size={18} strokeWidth={2} />
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* footer */}
          <div
            style={{
              padding: '14px 22px 18px 22px',
              borderTop: '1px solid rgba(255,255,255,0.08)',
              background: 'linear-gradient(180deg, rgba(255,255,255,0.02), rgba(0,0,0,0.08))',
              display: 'flex',
              justifyContent: 'flex-end',
              alignItems: 'center',
              gap: '12px',
              flexShrink: 0,
            }}
          >
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              style={{
                height: '44px',
                padding: '0 22px',
                borderRadius: '12px',
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.14)',
                color: '#e2e8f0',
                fontSize: '14px',
                fontWeight: 700,
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
                opacity: isSubmitting ? 0.6 : 1,
                minWidth: '86px',
                boxShadow: '0 2px 10px rgba(0,0,0,0.25) inset',
                transition: 'background 0.15s, border-color 0.15s',
              }}
              onMouseEnter={(e) => {
                if (!isSubmitting) {
                  (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.10)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.20)';
                }
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.06)';
                (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.14)';
              }}
            >
              Hủy
            </button>

            <button
              type="submit"
              disabled={isSubmitting}
              style={{
                height: '44px',
                padding: '0 20px',
                borderRadius: '12px',
                border: '1px solid rgba(99,102,241,0.55)',
                background: isSubmitting
                  ? 'linear-gradient(135deg, #334155, #475569)'
                  : 'linear-gradient(135deg, #0ea5e9 0%, #2563eb 28%, #7c3aed 68%, #a855f7 100%)',
                color: '#fff',
                fontSize: '14px',
                fontWeight: 800,
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                boxShadow: isSubmitting
                  ? 'none'
                  : '0 6px 20px rgba(59,130,246,0.45), 0 0 20px rgba(139,92,246,0.35), 0 0 0 1px rgba(255,255,255,0.12) inset',
                opacity: isSubmitting ? 0.85 : 1,
                minWidth: '168px',
                justifyContent: 'center',
                transition: 'transform 0.12s, box-shadow 0.15s, filter 0.15s',
                textShadow: '0 1px 2px rgba(0,0,0,0.25)',
              }}
              onMouseEnter={(e) => {
                if (!isSubmitting) {
                  (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(-1px)';
                  (e.currentTarget as HTMLButtonElement).style.filter = 'brightness(1.06)';
                  (e.currentTarget as HTMLButtonElement).style.boxShadow =
                    '0 8px 26px rgba(59,130,246,0.55), 0 0 28px rgba(139,92,246,0.45), 0 0 0 1px rgba(255,255,255,0.14) inset';
                }
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(0)';
                (e.currentTarget as HTMLButtonElement).style.filter = 'brightness(1)';
                (e.currentTarget as HTMLButtonElement).style.boxShadow =
                  '0 6px 20px rgba(59,130,246,0.45), 0 0 20px rgba(139,92,246,0.35), 0 0 0 1px rgba(255,255,255,0.12) inset';
              }}
            >
              <span>{isSubmitting ? 'Đang tạo...' : 'Tạo Series Mới'}</span>
              <Sparkles size={16} strokeWidth={2.2} style={{ opacity: 0.95 }} />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
