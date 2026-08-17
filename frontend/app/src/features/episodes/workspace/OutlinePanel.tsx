/**
 * OutlinePanel — Scene and act structural breakdown.
 */

import React from 'react';
import { Layers, Sparkles } from 'lucide-react';
import { Card, Badge, Button } from '@windagent/ui';

import type { EpisodeArtifactEnvelope } from '@windagent/api-contracts';

export interface OutlinePanelProps {
  artifact?: EpisodeArtifactEnvelope;
  isGenerating?: boolean;
  onStartGeneration: () => void;
}

export const OutlinePanel: React.FC<OutlinePanelProps> = ({
  artifact,
  isGenerating,
  onStartGeneration,
}) => {
  const content = artifact?.content || {};
  const acts = content.acts || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h3 style={{ margin: '0 0 4px 0', fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>
            Dàn Ý Kịch Bản (Episode Outline)
          </h3>
          <span style={{ fontSize: '13px', color: '#94a3b8' }}>
            Cấu trúc 3 hồi và các nút thắt kịch tính trong tập phim
          </span>
        </div>

        <Button
          variant="outline"
          onClick={onStartGeneration}
          disabled={isGenerating}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <Sparkles size={15} color="#38bdf8" />
          <span>{isGenerating ? 'Đang tạo dàn ý...' : 'Tạo lại dàn ý'}</span>
        </Button>
      </div>

      {!artifact || acts.length === 0 ? (
        <Card style={{ padding: '40px 24px', textAlign: 'center', background: 'var(--bg-canvas, #020617)' }}>
          <Layers size={32} style={{ color: '#c084fc', margin: '0 auto 12px' }} />
          <h4 style={{ margin: '0 0 6px 0', fontSize: '16px', fontWeight: 600 }}>Chưa có Dàn ý</h4>
          <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#94a3b8' }}>
            Dựa trên Story Bible, nhấn nút bên dưới để AI tự động xây dựng cấu trúc các hồi phân cảnh.
          </p>
          <Button variant="primary" onClick={onStartGeneration} disabled={isGenerating}>
            <Sparkles size={15} style={{ marginRight: '6px' }} />
            Tạo Dàn ý phân cảnh
          </Button>
        </Card>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {acts.map((act: any, idx: number) => (
            <Card
              key={idx}
              style={{
                padding: '20px',
                borderRadius: '12px',
                background: 'var(--bg-canvas, #020617)',
                border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                <Badge style={{ background: 'rgba(168, 85, 247, 0.15)', color: '#c084fc', fontSize: '11px', fontWeight: 700 }}>
                  HỒI {act.act_number || idx + 1}
                </Badge>
                <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#f8fafc' }}>
                  {act.title}
                </h4>
              </div>
              <p style={{ margin: 0, fontSize: '14px', color: '#cbd5e1', lineHeight: 1.6 }}>
                {act.summary}
              </p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
