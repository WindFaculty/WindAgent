/**
 * ProjectTemplatePicker — Modal for selecting curated cinematic templates.
 */

import React from 'react';
import { Sparkles, X, ArrowRight, Film } from 'lucide-react';
import { Badge, Card } from '@windagent/ui';

import type { ProjectTemplate } from '@windagent/api-contracts';

export interface ProjectTemplatePickerProps {
  isOpen: boolean;
  templates: ProjectTemplate[];
  onClose: () => void;
  onSelectTemplate: (template: ProjectTemplate) => void;
}

export const ProjectTemplatePicker: React.FC<ProjectTemplatePickerProps> = ({
  isOpen,
  templates,
  onClose,
  onSelectTemplate,
}) => {
  if (!isOpen) return null;

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
          maxWidth: '780px',
          maxHeight: '90vh',
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
                background: 'rgba(56, 189, 248, 0.15)',
                color: '#38bdf8',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Sparkles size={20} />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: 'var(--text-primary, #f8fafc)' }}>
                Mẫu kịch bản & vũ trụ AI Starter
              </h2>
              <span style={{ fontSize: '12px', color: 'var(--text-muted, #94a3b8)' }}>
                Khởi chạy nhanh dự án với thiết lập cốt truyện, nhân vật và tập đầu được dựng sẵn
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

        <div
          style={{
            padding: '24px',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: '16px',
            overflowY: 'auto',
          }}
        >
          {templates.map((tmpl) => (
            <Card
              key={tmpl.id}
              interactive
              onClick={() => {
                onSelectTemplate(tmpl);
                onClose();
              }}
              style={{
                padding: '20px',
                borderRadius: '12px',
                background: 'var(--bg-canvas, #020617)',
                border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                cursor: 'pointer',
                transition: 'border-color 0.2s, transform 0.2s',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                  <Badge
                    style={{
                      background: 'rgba(255, 255, 255, 0.08)',
                      border: `1px solid ${tmpl.accent_color}`,
                      color: tmpl.accent_color,
                      fontSize: '11px',
                    }}
                  >
                    {tmpl.genre}
                  </Badge>
                </div>

                <h3 style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: 700, color: 'var(--text-primary, #f8fafc)' }}>
                  {tmpl.title}
                </h3>

                <p style={{ margin: '0 0 12px 0', fontSize: '13px', color: 'var(--text-muted, #94a3b8)', lineHeight: 1.5 }}>
                  {tmpl.description}
                </p>

                <div
                  style={{
                    padding: '8px 12px',
                    borderRadius: '8px',
                    background: 'rgba(255, 255, 255, 0.03)',
                    border: '1px solid rgba(255, 255, 255, 0.05)',
                    marginBottom: '12px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 600, color: '#e2e8f0', marginBottom: '2px' }}>
                    <Film size={12} color={tmpl.accent_color} />
                    <span>{tmpl.initial_episode}</span>
                  </div>
                  <span style={{ fontSize: '11px', color: '#64748b' }}>{tmpl.episode_brief}</span>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px', color: tmpl.accent_color, fontWeight: 600, fontSize: '13px' }}>
                <span>Chọn mẫu này</span>
                <ArrowRight size={14} />
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
};
