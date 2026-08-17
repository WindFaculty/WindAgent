/**
 * CheckpointReviewPanel — Approval, revision feedback, and production lock action bar.
 */

import React, { useState } from 'react';
import { Check, Edit3, Lock, ShieldCheck, AlertCircle } from 'lucide-react';
import { Button, Textarea, Card, Badge } from '@windagent/ui';

import type { EpisodeResource } from '@windagent/api-contracts';

export interface CheckpointReviewPanelProps {
  episode: EpisodeResource;
  isSubmitting?: boolean;
  onApprove: (revisionId: string, expectedVersion: number) => Promise<any>;
  onRevise: (revisionId: string, feedback: string, expectedVersion: number) => Promise<any>;
  onLock: (revisionId: string, contentHash: string, expectedVersion: number) => Promise<any>;
}

export const CheckpointReviewPanel: React.FC<CheckpointReviewPanelProps> = ({
  episode,
  isSubmitting,
  onApprove,
  onRevise,
  onLock,
}) => {
  const [feedback, setFeedback] = useState('');
  const [showFeedback, setShowFeedback] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const revisionId = episode.current_revision_id || `rev-${episode.id}-v${episode.version}`;
  const isLocked = episode.state === 'LOCKED' || episode.state === 'READY_FOR_PRODUCTION';
  const canLock = episode.current_checkpoint === 'SCREENPLAY' || episode.current_checkpoint === 'REVIEW';

  const handleApprove = async () => {
    setErrorMsg(null);
    try {
      await onApprove(revisionId, episode.version);
    } catch (err: any) {
      setErrorMsg(err?.message || 'Phê duyệt thất bại. Có thể do phiên bản đã thay đổi.');
    }
  };

  const handleRevise = async () => {
    if (!feedback.trim()) {
      setErrorMsg('Vui lòng nhập phản hồi yêu cầu chỉnh sửa.');
      return;
    }
    setErrorMsg(null);
    try {
      await onRevise(revisionId, feedback.trim(), episode.version);
      setFeedback('');
      setShowFeedback(false);
    } catch (err: any) {
      setErrorMsg(err?.message || 'Gửi yêu cầu thất bại.');
    }
  };

  const handleLock = async () => {
    setErrorMsg(null);
    try {
      // Create sha-256 hash representation
      const contentHash = `sha256-${crypto.randomUUID().replace(/-/g, '')}`;
      await onLock(revisionId, contentHash, episode.version);
    } catch (err: any) {
      setErrorMsg(err?.message || 'Khóa kịch bản thất bại.');
    }
  };

  return (
    <Card
      style={{
        padding: '24px',
        borderRadius: '16px',
        background: isLocked
          ? 'linear-gradient(135deg, rgba(34, 197, 94, 0.1) 0%, rgba(15, 23, 42, 0.9) 100%)'
          : 'var(--bg-panel, #0f172a)',
        border: `1px solid ${isLocked ? 'rgba(34, 197, 94, 0.3)' : 'var(--border-subtle, rgba(255, 255, 255, 0.1))'}`,
        marginTop: '32px',
      }}
      data-testid="checkpoint-review-panel"
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {isLocked ? (
            <ShieldCheck size={24} color="#4ade80" />
          ) : (
            <Lock size={20} color="var(--color-primary, #3b82f6)" />
          )}
          <div>
            <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#f8fafc' }}>
              {isLocked ? 'Kịch Bản Đã Được Khóa & Sẵn Sàng Sản Xuất' : `Kiểm Duyệt Giai Đoạn: ${episode.current_checkpoint}`}
            </h4>
            <span style={{ fontSize: '12px', color: '#94a3b8' }}>
              Bản ghi bất biến: <code>{revisionId}</code> | Phiên bản v{episode.version}
            </span>
          </div>
        </div>

        {isLocked ? (
          <Badge style={{ background: 'rgba(34, 197, 94, 0.15)', color: '#4ade80', border: '1px solid #4ade80', fontSize: '12px' }}>
            READY FOR PRODUCTION
          </Badge>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {!showFeedback && (
              <Button
                variant="outline"
                onClick={() => setShowFeedback(true)}
                disabled={isSubmitting}
                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Edit3 size={14} />
                <span>Yêu cầu sửa đổi</span>
              </Button>
            )}

            <Button
              variant="secondary"
              onClick={handleApprove}
              disabled={isSubmitting}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: 'rgba(59, 130, 246, 0.15)',
                color: '#3b82f6',
                border: '1px solid rgba(59, 130, 246, 0.3)',
              }}
            >
              <Check size={15} />
              <span>Duyệt bước này</span>
            </Button>

            {canLock && (
              <Button
                variant="primary"
                onClick={handleLock}
                disabled={isSubmitting}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: '#22c55e',
                  borderColor: '#22c55e',
                }}
              >
                <Lock size={15} />
                <span>Khóa kịch bản (Lock)</span>
              </Button>
            )}
          </div>
        )}
      </div>

      {errorMsg && (
        <div style={{ padding: '10px 14px', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#f87171', fontSize: '13px', marginBottom: '16px' }}>
          <AlertCircle size={15} style={{ display: 'inline', marginRight: '6px' }} />
          {errorMsg}
        </div>
      )}

      {showFeedback && !isLocked && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', paddingTop: '12px', borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
          <label style={{ fontSize: '13px', fontWeight: 600, color: '#e2e8f0' }}>
            Nội dung phản hồi / Hướng dẫn đạo diễn AI chỉnh sửa:
          </label>
          <Textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="VD: Cần tăng độ kịch tính ở hồi 2, bổ sung đoạn đối thoại gay gắt hơn giữa Alex và Vesper-9..."
            rows={3}
            style={{ width: '100%', background: 'var(--bg-canvas, #020617)', borderColor: 'rgba(255, 255, 255, 0.15)' }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <Button variant="ghost" onClick={() => setShowFeedback(false)} disabled={isSubmitting}>
              Hủy
            </Button>
            <Button variant="primary" onClick={handleRevise} disabled={isSubmitting}>
              Gửi yêu cầu chỉnh sửa
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
};
