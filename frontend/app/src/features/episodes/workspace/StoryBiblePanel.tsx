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
  const premise = content.premise;
  const arcSummary = content.arc_summary;
  const stakes = content.stakes;
  const storyRules = Array.isArray(content.story_rules)
    ? content.story_rules
    : typeof content.world_rules === 'string'
    ? [content.world_rules]
    : [];
  const theme = content.theme;
  const tone = content.tone;
  const characters = content.characters || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h3 style={{ margin: '0 0 4px 0', fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>
            Story Bible (Kinh Thánh Cốt Truyện)
          </h3>
          <span style={{ fontSize: '13px', color: '#94a3b8' }}>
            Thiết lập nhân vật trọng tâm, quy tắc thế giới và cấu trúc câu chuyện
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
          {/* Premise & Theme */}
          <Card style={{ padding: '20px', background: 'var(--bg-canvas, #020617)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8' }}>
                <Globe size={18} />
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>Tiền Đề & Thông Điệp Chủ Đề</h4>
              </div>
              <div style={{ display: 'flex', gap: '6px' }}>
                {tone && <Badge style={{ background: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa' }}>Tone: {tone}</Badge>}
                {theme && <Badge style={{ background: 'rgba(168, 85, 247, 0.15)', color: '#c084fc' }}>Theme: {theme}</Badge>}
              </div>
            </div>

            {premise && (
              <div style={{ marginBottom: '12px' }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase' }}>Tiền đề (Premise):</span>
                <p style={{ margin: '4px 0 0 0', fontSize: '14px', color: '#cbd5e1', lineHeight: 1.6 }}>{premise}</p>
              </div>
            )}

            {arcSummary && (
              <div style={{ marginBottom: '12px' }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase' }}>Tóm tắt hành trình (Arc Summary):</span>
                <p style={{ margin: '4px 0 0 0', fontSize: '14px', color: '#cbd5e1', lineHeight: 1.6 }}>{arcSummary}</p>
              </div>
            )}

            {stakes && (
              <div>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase' }}>Hiểm họa & Thách thức (Stakes):</span>
                <p style={{ margin: '4px 0 0 0', fontSize: '14px', color: '#cbd5e1', lineHeight: 1.6 }}>{stakes}</p>
              </div>
            )}
          </Card>

          {/* Story Rules */}
          {storyRules.length > 0 && (
            <Card style={{ padding: '20px', background: 'var(--bg-canvas, #020617)' }}>
              <h4 style={{ margin: '0 0 12px 0', fontSize: '15px', fontWeight: 700, color: '#f8fafc' }}>
                Quy Tắc Cốt Truyện & Thế Giới
              </h4>
              <ul style={{ margin: 0, paddingLeft: '20px', color: '#cbd5e1', fontSize: '14px', lineHeight: 1.7 }}>
                {storyRules.map((rule: string, rIdx: number) => (
                  <li key={rIdx}>{rule}</li>
                ))}
              </ul>
            </Card>
          )}

          {/* Characters Section */}
          {characters.length > 0 && (
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
                        {char.role || 'Character'}
                      </Badge>
                    </div>
                    {char.archetype && <span style={{ fontSize: '12px', color: '#94a3b8' }}>Hình mẫu: {char.archetype}</span>}
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
