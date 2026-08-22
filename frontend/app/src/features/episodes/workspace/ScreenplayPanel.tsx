/**
 * ScreenplayPanel — Full formatted cinematic screenplay reader & previewer.
 */

import React from 'react';
import { Sparkles, FileText } from 'lucide-react';
import { Card, Button } from '@windagent/ui';

import type { EpisodeArtifactEnvelope } from '@windagent/api-contracts';

export interface ScreenplayPanelProps {
  artifact?: EpisodeArtifactEnvelope;
  isGenerating?: boolean;
  onStartGeneration: () => void;
}

export const ScreenplayPanel: React.FC<ScreenplayPanelProps> = ({
  artifact,
  isGenerating,
  onStartGeneration,
}) => {
  const content = artifact?.content || {};
  const scenes = content.scenes || [];
  const logline = content.logline;
  const title = content.title;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h3 style={{ margin: '0 0 4px 0', fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>
            {title ? `Bản Thảo Kịch Bản: ${title}` : 'Bản Thảo Kịch Bản (Screenplay Draft)'}
          </h3>
          <span style={{ fontSize: '13px', color: '#94a3b8' }}>
            {logline || 'Kịch bản chi tiết theo chuẩn công nghiệp điện ảnh'} ({scenes.length} cảnh)
          </span>
        </div>

        <Button
          variant="outline"
          onClick={onStartGeneration}
          disabled={isGenerating}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <Sparkles size={15} color="#38bdf8" />
          <span>{isGenerating ? 'Đang viết kịch bản...' : 'Tạo lại kịch bản'}</span>
        </Button>
      </div>

      {!artifact || scenes.length === 0 ? (
        <Card style={{ padding: '40px 24px', textAlign: 'center', background: 'var(--bg-canvas, #020617)' }}>
          <FileText size={32} style={{ color: '#38bdf8', margin: '0 auto 12px' }} />
          <h4 style={{ margin: '0 0 6px 0', fontSize: '16px', fontWeight: 600 }}>Chưa có Kịch bản</h4>
          <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#94a3b8' }}>
            Sau khi hoàn thành Dàn ý, nhấn nút bên dưới để AI tự động viết toàn bộ các cảnh phân đoạn và lời thoại.
          </p>
          <Button variant="primary" onClick={onStartGeneration} disabled={isGenerating}>
            <Sparkles size={15} style={{ marginRight: '6px' }} />
            Viết Kịch bản chi tiết
          </Button>
        </Card>
      ) : (
        <div
          style={{
            background: 'var(--bg-canvas, #020617)',
            borderRadius: '16px',
            border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
            padding: '32px',
            fontFamily: '"Courier Prime", Courier, monospace',
            color: '#e2e8f0',
            lineHeight: 1.6,
          }}
        >
          {scenes.map((scene: any, idx: number) => {
            const sceneNumber = scene.order || scene.scene_number || idx + 1;
            const heading = scene.heading || (scene.location_id ? `CẢNH TẠI ${String(scene.location_id).toUpperCase()}` : `CẢNH ${sceneNumber}`);
            const actionText = scene.action_description || scene.action || '';
            const dialogues = scene.dialogue || [];
            const transition = scene.transition;

            return (
              <div key={idx} style={{ marginBottom: '32px' }}>
                <div
                  style={{
                    fontWeight: 700,
                    fontSize: '15px',
                    color: '#38bdf8',
                    marginBottom: '12px',
                    letterSpacing: '0.5px',
                  }}
                >
                  CẢNH {sceneNumber}: {heading}
                </div>

                {actionText && (
                  <p style={{ margin: '0 0 16px 0', fontSize: '14px', color: '#cbd5e1' }}>
                    {actionText}
                  </p>
                )}

                {scene.narration && (
                  <div style={{ margin: '12px auto', maxWidth: '520px', fontStyle: 'italic', color: '#94a3b8', textAlign: 'center', fontSize: '13px' }}>
                    [Lời dẫn: {scene.narration}]
                  </div>
                )}

                {dialogues.map((d: any, dIdx: number) => {
                  const speaker = d.speaker || d.character_id || 'NHÂN VẬT';
                  return (
                    <div key={dIdx} style={{ margin: '14px auto', maxWidth: '480px', textAlign: 'center' }}>
                      <div style={{ fontWeight: 700, color: '#facc15', fontSize: '13px', letterSpacing: '1px' }}>
                        {String(speaker).toUpperCase()}
                      </div>
                      {d.delivery && (
                        <div style={{ fontSize: '12px', color: '#94a3b8', fontStyle: 'italic' }}>
                          ({d.delivery})
                        </div>
                      )}
                      <div style={{ fontSize: '14px', color: '#f8fafc', marginTop: '2px', textAlign: 'left', display: 'inline-block' }}>
                        {d.text}
                      </div>
                    </div>
                  );
                })}

                {transition && (
                  <div style={{ textAlign: 'right', fontWeight: 700, color: '#64748b', fontSize: '13px', marginTop: '16px' }}>
                    {transition}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
