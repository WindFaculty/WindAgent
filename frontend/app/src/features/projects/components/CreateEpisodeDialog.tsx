/**
 * CreateEpisodeDialog — Modal for creating a new episode under a project.
 */

import React, { useState } from 'react';
import { X, Film } from 'lucide-react';
import { Button, Input } from '@windagent/ui';

import type { CreateEpisodeInput } from '../hooks/useCreateEpisode';

export interface CreateEpisodeDialogProps {
  isOpen: boolean;
  projectId: string;
  projectName: string;
  nextEpisodeNumber: number;
  onClose: () => void;
  onSubmit: (input: CreateEpisodeInput) => Promise<any>;
}

export const CreateEpisodeDialog: React.FC<CreateEpisodeDialogProps> = ({
  isOpen,
  projectId,
  projectName,
  nextEpisodeNumber,
  onClose,
  onSubmit,
}) => {
  const [title, setTitle] = useState(`Tập ${String(nextEpisodeNumber).padStart(2, '0')}: `);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  React.useEffect(() => {
    if (isOpen) {
      setTitle(`Tập ${String(nextEpisodeNumber).padStart(2, '0')}: `);
    }
  }, [isOpen, nextEpisodeNumber]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setErrorMsg('Vui lòng nhập tên tập phim.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      await onSubmit({
        projectId,
        title: title.trim(),
        episode_number: nextEpisodeNumber,
      });
      onClose();
    } catch (err: any) {
      setErrorMsg(err?.message || 'Không thể tạo tập phim. Vui lòng thử lại.');
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
          maxWidth: '480px',
          background: 'var(--bg-panel, #0f172a)',
          border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.12))',
          borderRadius: '16px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.6)',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
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
              <Film size={20} />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: 'var(--text-primary, #f8fafc)' }}>
                Tạo tập phim mới
              </h2>
              <span style={{ fontSize: '12px', color: 'var(--text-muted, #94a3b8)' }}>
                Dự án: {projectName}
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
            }}
          >
            <X size={18} />
          </button>
        </div>

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
              Tên tập phim <span style={{ color: '#f87171' }}>*</span>
            </label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="VD: Tập 02: Mê Cung Neon..."
              autoFocus
              required
              style={{
                width: '100%',
                background: 'var(--bg-canvas, #020617)',
                borderColor: 'var(--border-subtle, rgba(255, 255, 255, 0.12))',
              }}
            />
          </div>

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
              {isSubmitting ? 'Đang tạo...' : 'Tạo tập phim'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
