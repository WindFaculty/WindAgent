/**
 * Phase 9D — ReviewsPage
 * Canonical review system UI.
 * ZERO DEFAULT_VERSIONS. ZERO DEFAULT_COMMENTS.
 * Decisions are pinned to revision_id + expected_version.
 */
import React, { useState } from 'react';
import { useReviews, useReview, useReviewComments, useAddReviewComment, useSubmitReviewDecision } from '../hooks/useReviews';
import type { ReviewResource, ReviewDecisionKind, ReviewSubjectType } from '@windagent/api-contracts';

interface ReviewsPageProps {
  episodeId?: string;
  projectId?: string;
}

const SUBJECT_LABELS: Record<ReviewSubjectType, string> = {
  storyboard: 'Storyboard',
  character_revision: 'Nhân vật',
  asset_revision: 'Asset',
  production_preview: 'Xem trước',
  screenplay: 'Kịch bản',
};

const STATUS_COLORS: Record<string, string> = {
  PENDING: '#f59e0b',
  APPROVED: '#22c55e',
  REVISION_NEEDED: '#f97316',
  REJECTED: '#ef4444',
};

const STATUS_LABELS: Record<string, string> = {
  PENDING: 'Đang xem xét',
  APPROVED: 'Đã duyệt',
  REVISION_NEEDED: 'Cần sửa',
  REJECTED: 'Từ chối',
};

export const ReviewsPage: React.FC<ReviewsPageProps> = ({ episodeId, projectId }) => {
  const [selectedReviewId, setSelectedReviewId] = useState<string | null>(null);

  const { data: reviews = [], isLoading, error } = useReviews({ episode_id: episodeId, project_id: projectId });

  if (isLoading) {
    return (
      <div className="reviews-page reviews-page--loading">
        <div className="loading-spinner" />
        <p>Đang tải danh sách reviews...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="reviews-page reviews-page--error">
        <h3>Không thể tải reviews</h3>
        <p>{(error as Error).message}</p>
      </div>
    );
  }

  return (
    <div className="reviews-page">
      <header className="reviews-page__header">
        <h1>Reviews</h1>
        <span className="reviews-page__count">{reviews.length} reviews</span>
      </header>

      <div className="reviews-page__layout">
        <div className="reviews-page__list">
          {reviews.length === 0 ? (
            <div className="reviews-page__empty">
              <span>📋</span>
              <p>Chưa có review nào</p>
            </div>
          ) : (
            reviews.map((review: ReviewResource) => (
              <ReviewListItem
                key={review.id}
                review={review}
                isSelected={selectedReviewId === review.id}
                onSelect={() => setSelectedReviewId(review.id === selectedReviewId ? null : review.id)}
              />
            ))
          )}
        </div>

        <div className="reviews-page__detail">
          {selectedReviewId ? (
            <ReviewDetail reviewId={selectedReviewId} />
          ) : (
            <div className="reviews-page__select-prompt">
              <span>👈</span>
              <p>Chọn một review để xem chi tiết</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

function ReviewListItem({ review, isSelected, onSelect }: { review: ReviewResource; isSelected: boolean; onSelect: () => void }) {
  const statusColor = STATUS_COLORS[review.status] ?? '#6b7280';
  return (
    <div className={`review-list-item${isSelected ? ' review-list-item--selected' : ''}`} onClick={onSelect}>
      <div className="review-list-item__header">
        <span className="review-list-item__subject">{SUBJECT_LABELS[review.subject_type as ReviewSubjectType] ?? review.subject_type}</span>
        <span
          className="review-list-item__status"
          style={{ color: statusColor, backgroundColor: `${statusColor}22`, border: `1px solid ${statusColor}44` }}
        >
          {STATUS_LABELS[review.status] ?? review.status}
        </span>
      </div>
      <div className="review-list-item__subject-id">{review.subject_id}</div>
      <div className="review-list-item__meta">{review.comments_count} bình luận</div>
    </div>
  );
}

function ReviewDetail({ reviewId }: { reviewId: string }) {
  const { data: review } = useReview(reviewId);
  const { data: comments = [] } = useReviewComments(reviewId);
  const addComment = useAddReviewComment(reviewId);
  const submitDecision = useSubmitReviewDecision(reviewId);
  const [commentText, setCommentText] = useState('');
  const [showDecision, setShowDecision] = useState(false);
  const [decisionForm, setDecisionForm] = useState({ decision: 'APPROVED' as ReviewDecisionKind, revision_id: '', expected_version: 1, reason: '', decided_by: 'User' });

  if (!review) return <div className="loading-spinner" />;

  const isTerminal = review.status === 'APPROVED' || review.status === 'REJECTED';

  return (
    <div className="review-detail">
      <div className="review-detail__header">
        <h3>{SUBJECT_LABELS[review.subject_type as ReviewSubjectType] ?? review.subject_type}</h3>
        <span className="review-detail__subject-id">{review.subject_id}</span>
      </div>

      {review.decision && (
        <div className="review-detail__decision">
          <div className="review-detail__decision-badge" style={{ color: STATUS_COLORS[review.status] }}>
            ✅ {STATUS_LABELS[review.status]}
          </div>
          <div className="review-detail__decision-meta">
            <span>Bởi {review.decision.decided_by}</span>
            <span>Rev: {review.decision.revision_id} (v{review.decision.expected_version})</span>
          </div>
          {review.decision.reason && <p className="review-detail__decision-reason">{review.decision.reason}</p>}
        </div>
      )}

      <div className="review-detail__comments">
        <h4>Bình luận ({comments.length})</h4>
        {comments.map((c: any) => (
          <div key={c.id} className="review-comment">
            <div className="review-comment__header">
              <strong>{c.author}</strong>
              <span className="review-comment__role">{c.role}</span>
              <span className="review-comment__time">{new Date(c.timestamp).toLocaleTimeString('vi-VN')}</span>
            </div>
            <p className="review-comment__text">{c.text}</p>
          </div>
        ))}

        {!isTerminal && (
          <div className="review-detail__add-comment">
            <textarea
              className="form-textarea"
              rows={3}
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              placeholder="Thêm bình luận..."
            />
            <button
              className="btn btn--secondary btn--sm"
              disabled={!commentText.trim() || addComment.isPending}
              onClick={async () => {
                await addComment.mutateAsync({ author: 'User', text: commentText });
                setCommentText('');
              }}
            >
              Gửi bình luận
            </button>
          </div>
        )}
      </div>

      {!isTerminal && (
        <div className="review-detail__decision-section">
          {!showDecision ? (
            <button className="btn btn--primary" onClick={() => setShowDecision(true)}>
              Gửi quyết định
            </button>
          ) : (
            <div className="review-detail__decision-form">
              <h4>Gửi quyết định</h4>

              <div className="form-group">
                <label>Quyết định</label>
                <select
                  className="form-select"
                  value={decisionForm.decision}
                  onChange={(e) => setDecisionForm((f) => ({ ...f, decision: e.target.value as ReviewDecisionKind }))}
                >
                  <option value="APPROVED">Duyệt</option>
                  <option value="REVISION_NEEDED">Cần sửa</option>
                  <option value="REJECTED">Từ chối</option>
                </select>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Revision ID *</label>
                  <input
                    className="form-input"
                    value={decisionForm.revision_id}
                    onChange={(e) => setDecisionForm((f) => ({ ...f, revision_id: e.target.value }))}
                    placeholder="rev-..."
                  />
                </div>
                <div className="form-group">
                  <label>Version *</label>
                  <input
                    className="form-input"
                    type="number"
                    min={1}
                    value={decisionForm.expected_version}
                    onChange={(e) => setDecisionForm((f) => ({ ...f, expected_version: Number(e.target.value) }))}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Lý do</label>
                <textarea
                  className="form-textarea"
                  rows={2}
                  value={decisionForm.reason}
                  onChange={(e) => setDecisionForm((f) => ({ ...f, reason: e.target.value }))}
                  placeholder="Lý do quyết định..."
                />
              </div>

              <div className="modal__actions">
                <button className="btn btn--ghost" onClick={() => setShowDecision(false)}>Hủy</button>
                <button
                  className="btn btn--primary"
                  disabled={!decisionForm.revision_id || submitDecision.isPending}
                  onClick={() => submitDecision.mutate(decisionForm)}
                >
                  {submitDecision.isPending ? 'Đang gửi...' : 'Xác nhận quyết định'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
