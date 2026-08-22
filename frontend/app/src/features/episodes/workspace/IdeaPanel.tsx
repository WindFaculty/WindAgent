/**
 * IdeaPanel — Idea candidate review, generation, and selection.
 */

import React from 'react';
import { Sparkles, Check, Lightbulb } from 'lucide-react';
import { Card, Button, Badge } from '@windagent/ui';

import type { EpisodeArtifactEnvelope } from '@windagent/api-contracts';

export interface IdeaPanelProps {
  artifact?: EpisodeArtifactEnvelope;
  isGenerating?: boolean;
  onStartGeneration: () => void;
  onSelectIdea: (ideaId: string) => void;
  isSelectingIdea?: boolean;
}

export const IdeaPanel: React.FC<IdeaPanelProps> = ({
  artifact,
  isGenerating,
  onStartGeneration,
  onSelectIdea,
  isSelectingIdea,
}) => {
  const content = artifact?.content || {};
  const ideas = content.candidates || content.ideas || [];
  const selectedIdeaId = content.selected_candidate_id || content.selected_idea_id;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h3 style={{ margin: '0 0 4px 0', fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>
            Ý Tưởng Cốt Truyện (Idea Candidates)
          </h3>
          <span style={{ fontSize: '13px', color: '#94a3b8' }}>
            Tuyển chọn tiền đề và hướng đi ban đầu cho tập phim ({ideas.length} ý tưởng)
          </span>
        </div>

        <Button
          variant="outline"
          onClick={onStartGeneration}
          disabled={isGenerating}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <Sparkles size={15} color="#38bdf8" />
          <span>{isGenerating ? 'Đang tạo ý tưởng...' : 'Sinh thêm ý tưởng AI'}</span>
        </Button>
      </div>

      {ideas.length === 0 ? (
        <Card style={{ padding: '40px 24px', textAlign: 'center', background: 'var(--bg-canvas, #020617)' }}>
          <Lightbulb size={32} style={{ color: '#fbbf24', margin: '0 auto 12px' }} />
          <h4 style={{ margin: '0 0 6px 0', fontSize: '16px', fontWeight: 600 }}>Chưa có ý tưởng nào</h4>
          <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#94a3b8' }}>
            Nhấn nút bên dưới để AI tự động khám phá và đề xuất các tiền đề kịch bản hấp dẫn.
          </p>
          <Button variant="primary" onClick={onStartGeneration} disabled={isGenerating}>
            <Sparkles size={15} style={{ marginRight: '6px' }} />
            Bắt đầu sinh ý tưởng
          </Button>
        </Card>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
          {ideas.map((idea: any) => {
            const ideaId = idea.candidate_id || idea.id;
            const isSelected = ideaId === selectedIdeaId;
            const score = typeof idea.score === 'number' ? Math.round(idea.score * 100) : null;
            const tone = idea.tone || (idea.themes && idea.themes[0]) || 'Cinematic';

            return (
              <Card
                key={ideaId}
                style={{
                  padding: '20px',
                  borderRadius: '12px',
                  background: isSelected ? 'rgba(59, 130, 246, 0.12)' : 'var(--bg-canvas, #020617)',
                  border: isSelected
                    ? '1px solid var(--color-primary, #3b82f6)'
                    : '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px', flexWrap: 'wrap', gap: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Badge style={{ background: 'rgba(255, 255, 255, 0.08)', color: '#38bdf8', fontSize: '11px' }}>
                        {tone}
                      </Badge>
                      {score !== null && (
                        <Badge style={{ background: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa', fontSize: '11px' }}>
                          Khớp: {score}%
                        </Badge>
                      )}
                    </div>
                    {isSelected && (
                      <Badge style={{ background: 'rgba(34, 197, 94, 0.15)', color: '#4ade80', fontSize: '11px' }}>
                        ĐÃ CHỌN
                      </Badge>
                    )}
                  </div>

                  <h4 style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: 700, color: '#f8fafc' }}>
                    {idea.title}
                  </h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#cbd5e1', lineHeight: 1.5 }}>
                    {idea.premise || idea.summary || idea.logline}
                  </p>
                </div>

                <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid rgba(255, 255, 255, 0.06)', display: 'flex', justifyContent: 'flex-end' }}>
                  <Button
                    variant={isSelected ? 'outline' : 'primary'}
                    onClick={() => onSelectIdea(ideaId)}
                    disabled={isSelectingIdea || isSelected}
                    style={{ fontSize: '13px', padding: '6px 14px' }}
                  >
                    {isSelected ? (
                      <>
                        <Check size={14} style={{ marginRight: '4px' }} /> Đã chọn
                      </>
                    ) : (
                      'Chọn ý tưởng này'
                    )}
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};
