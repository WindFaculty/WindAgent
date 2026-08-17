/**
 * StoryBiblePanel — Characters, setting, and world rules presentation.
 */

import React from 'react';
import { Users, Globe, BookOpen, Sparkles } from 'lucide-react';
import { Card, Badge, Button } from '@windagent/ui';
import type { EpisodeArtifactEnvelope } from '@windagent/api-contracts';

export interface StoryBiblePanelProps {
  artifact?: EpisodeArtifactEnvelope;
  isGenerating?: boolean;
  onStartGeneration: () => void;
}

export const StoryBiblePanel: React.FC<StoryBiblePanelProps> = ({
  artifact,
  isGenerating,
  onStartGeneration,
}) => {
  const content = artifact?.content || {};
  const characters = content.characters || [];
  const worldRules = content.world_rules;
  const theme = content.theme;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h3 style={{ margin: '0 0 4px 0', fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>
            Story Bible (Kinh Thánh Cốt Truyện)
          </h3>
          <span style={{ fontSize: '13px', color: '#94a3b8' }}>
            Thiết lập nhân vật trọng tâm, quy tắc thế giới và thông điệp chủ đề
          </span>
        </div>

        <Button
          variant="outline"
          onClick={onStartGeneration}
          disabled={isGenerating}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <Sparkles size={15} color="#38bdf8" />
          <span>{isGenerating ? 'Đang cập nhật...' : 'Cập nhật Story Bible'}</span>
        </Button>
      </div>

      {!artifact ? (
        <Card style={{ padding: '40px 24px', textAlign: 'center', background: 'var(--bg-canvas, #020617)' }}>
          <BookOpen size={32} style={{ color: '#818cf8', margin: '0 auto 12px' }} />
          <h4 style={{ margin: '0 0 6px 0', fontSize: '16px', fontWeight: 600 }}>Chưa có Story Bible</h4>
          <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#94a3b8' }}>
            Sau khi chọn ý tưởng, nhấn nút bên dưới để tạo tài liệu Story Bible chi tiết.
          </p>
          <Button variant="primary" onClick={onStartGeneration} disabled={isGenerating}>
            <Sparkles size={15} style={{ marginRight: '6px' }} />
            Tạo Story Bible
          </Button>
        </Card>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Theme & World Overview */}
          <Card style={{ padding: '20px', background: 'var(--bg-canvas, #020617)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', color: '#38bdf8' }}>
              <Globe size={18} />
              <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>Quy Tắc Thế Giới & Bối Cảnh</h4>
            </div>
            <p style={{ margin: '0 0 16px 0', fontSize: '14px', color: '#cbd5e1', lineHeight: 1.6 }}>
              {worldRules || 'Chưa thiết lập quy tắc thế giới.'}
            </p>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#a78bfa' }}>
              <span style={{ fontSize: '13px', fontWeight: 600 }}>Chủ đề chính:</span>
              <span style={{ fontSize: '13px', color: '#e2e8f0' }}>{theme || 'Chưa định nghĩa'}</span>
            </div>
          </Card>

          {/* Characters Section */}
          <div>
            <h4 style={{ margin: '0 0 12px 0', fontSize: '16px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Users size={18} color="#4ade80" />
              <span>Dàn Nhân Vật ({characters.length})</span>
            </h4>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
              {characters.map((char: any, idx: number) => (
                <Card key={idx} style={{ padding: '16px', background: 'var(--bg-canvas, #020617)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <span style={{ fontSize: '15px', fontWeight: 700, color: '#f8fafc' }}>{char.name}</span>
                    <Badge style={{ background: 'rgba(255, 255, 255, 0.08)', color: '#38bdf8', fontSize: '11px' }}>
                      {char.role}
                    </Badge>
                  </div>
                  <span style={{ fontSize: '12px', color: '#94a3b8' }}>Hình mẫu: {char.archetype}</span>
                </Card>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
