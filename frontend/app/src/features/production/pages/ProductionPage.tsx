/**
 * Phase 10 — ProductionPage
 * Canonical Episode-Centric Production Workspace.
 * ZERO FakeProductionApiClient. ZERO hardcoded proj-alpha. ZERO fake timers.
 * Fully backed by /api/v3/episodes/{episodeId}/production + WebSocket stream.
 */
import React, { useState } from 'react';
import {
  useProductionPlan,
  useShots,
  useCreateShot,
  useProductionJobs,
  useSubmitStageJob,
  useRetryStageJob,
  useDeliveryArtifact,
  useProductionRealtime,
} from '../hooks/useProduction';
import { JobProgress } from '../components/JobProgress';
import { JobFailure } from '../components/JobFailure';
import { ArtifactPreview } from '../components/ArtifactPreview';
import type { JobStage } from '@windagent/api-contracts';

export type ProductionTab = 'overview' | 'shots' | 'audio' | 'animation' | 'render' | 'delivery';

interface ProductionPageProps {
  episodeId: string;
  initialTab?: ProductionTab;
  apiBaseUrl?: string;
}

export const ProductionPage: React.FC<ProductionPageProps> = ({
  episodeId,
  initialTab = 'overview',
  apiBaseUrl = '',
}) => {
  const [activeTab, setActiveTab] = useState<ProductionTab>(initialTab);
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);

  // Queries
  const { data: plan, isLoading: loadingPlan, error: planError } = useProductionPlan(episodeId);
  const { data: shots = [], isLoading: loadingShots } = useShots(episodeId);
  const { data: jobs = [] } = useProductionJobs(episodeId);
  const { data: delivery } = useDeliveryArtifact(episodeId);

  // Mutations
  const createShot = useCreateShot(episodeId);
  const submitAudio = useSubmitStageJob(episodeId, 'AUDIO');
  const submitAnimation = useSubmitStageJob(episodeId, 'ANIMATION');
  const submitRender = useSubmitStageJob(episodeId, 'RENDER');
  const submitVideo = useSubmitStageJob(episodeId, 'VIDEO');

  const retryJob = useRetryStageJob(episodeId, (jobs.find(j => j.job_id)?.job_type as JobStage) || 'RENDER');

  // Realtime WebSocket subscription
  useProductionRealtime(episodeId, apiBaseUrl);

  const isLoading = loadingPlan || loadingShots;

  if (isLoading) {
    return (
      <div className="production-page production-page--loading">
        <div className="loading-spinner" />
        <p>Đang tải Production Workspace...</p>
      </div>
    );
  }

  if (planError) {
    return (
      <div className="production-page production-page--error">
        <h3>Không thể tải Production Plan</h3>
        <p>{(planError as Error).message}</p>
      </div>
    );
  }

  const selectedShot = shots.find((s) => s.id === selectedShotId) ?? shots[0] ?? null;

  const audioJobs = jobs.filter((j) => j.job_type === 'AUDIO');
  const animJobs = jobs.filter((j) => j.job_type === 'ANIMATION');
  const renderJobs = jobs.filter((j) => j.job_type === 'RENDER');

  const tabs: { id: ProductionTab; label: string; count?: number }[] = [
    { id: 'overview', label: '📊 Tổng quan' },
    { id: 'shots', label: '🎬 Phân cảnh (Shots)', count: shots.length },
    { id: 'audio', label: '🎙️ Audio / Voice', count: audioJobs.length },
    { id: 'animation', label: '🧊 Animation', count: animJobs.length },
    { id: 'render', label: '🖥️ Render Engine', count: renderJobs.length },
    { id: 'delivery', label: '📦 Xuất bản (Delivery)' },
  ];

  return (
    <div className="production-page">
      <header className="production-page__header">
        <div className="production-page__title-block">
          <div className="production-page__badge">EPISODE PRODUCTION</div>
          <h1>Tập phim: {episodeId}</h1>
          {plan && (
            <div className="production-page__pins">
              <span className="production-page__pin" title="Locked Screenplay Revision">
                📜 {plan.screenplay_revision_id}
              </span>
              <span className="production-page__pin" title="Locked Storyboard Revision">
                🎨 {plan.storyboard_revision_id}
              </span>
            </div>
          )}
        </div>

        <div className="production-page__stats">
          <div className="production-stat">
            <span className="production-stat__value">{shots.length}</span>
            <span className="production-stat__label">Shots</span>
          </div>
          <div className="production-stat">
            <span className="production-stat__value">{plan?.progress_percent ?? 0}%</span>
            <span className="production-stat__label">Tiến độ</span>
          </div>
          <div className="production-stat">
            <span className="production-stat__value">{jobs.filter((j) => j.state === 'SUCCEEDED').length}/{jobs.length}</span>
            <span className="production-stat__label">Jobs Done</span>
          </div>
        </div>
      </header>

      <nav className="production-page__tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`production-page__tab${activeTab === tab.id ? ' production-page__tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.count !== undefined && <span className="production-page__tab-count">{tab.count}</span>}
          </button>
        ))}
      </nav>

      <main className="production-page__content">
        {/* ─── OVERVIEW TAB ─── */}
        {activeTab === 'overview' && plan && (
          <div className="production-overview">
            <div className="production-overview__grid">
              <div className="production-card">
                <h3>📌 Kịch bản & Storyboard đã khóa</h3>
                <dl className="production-dl">
                  <dt>Screenplay Revision</dt>
                  <dd><code>{plan.screenplay_revision_id}</code></dd>
                  <dt>Storyboard Revision</dt>
                  <dd><code>{plan.storyboard_revision_id}</code></dd>
                  <dt>Trạng thái Plan</dt>
                  <dd><span className="status-badge status-badge--active">{plan.status}</span></dd>
                  <dt>Nhân vật liên kết</dt>
                  <dd>{plan.character_references.length} nhân vật</dd>
                  <dt>Assets liên kết</dt>
                  <dd>{plan.asset_references.length} assets</dd>
                </dl>
              </div>

              <div className="production-card">
                <h3>🚀 Tiến trình sản xuất</h3>
                <div className="production-progress-bar">
                  <div
                    className="production-progress-bar__fill"
                    style={{ width: `${plan.progress_percent}%` }}
                  />
                </div>
                <div className="production-stage-checklist">
                  <div className={`production-stage-item ${shots.length > 0 ? 'done' : ''}`}>
                    <span>1. Phân cảnh (Shots Breakdown)</span>
                    <span>{shots.length > 0 ? '✅ Hoàn tất' : '⏳ Chưa có'}</span>
                  </div>
                  <div className={`production-stage-item ${audioJobs.some(j => j.state === 'SUCCEEDED') ? 'done' : ''}`}>
                    <span>2. Tạo thoại (Audio/TTS)</span>
                    <span>{audioJobs.some(j => j.state === 'SUCCEEDED') ? '✅ Hoàn tất' : '⏳ Đang chờ'}</span>
                  </div>
                  <div className={`production-stage-item ${animJobs.some(j => j.state === 'SUCCEEDED') ? 'done' : ''}`}>
                    <span>3. Diễn hoạt (Animation)</span>
                    <span>{animJobs.some(j => j.state === 'SUCCEEDED') ? '✅ Hoàn tất' : '⏳ Đang chờ'}</span>
                  </div>
                  <div className={`production-stage-item ${renderJobs.some(j => j.state === 'SUCCEEDED') ? 'done' : ''}`}>
                    <span>4. Kết xuất (Render Engine)</span>
                    <span>{renderJobs.some(j => j.state === 'SUCCEEDED') ? '✅ Hoàn tất' : '⏳ Đang chờ'}</span>
                  </div>
                  <div className={`production-stage-item ${delivery?.video_asset_id ? 'done' : ''}`}>
                    <span>5. Đóng gói & Xuất bản (Delivery)</span>
                    <span>{delivery?.video_asset_id ? '✅ Sẵn sàng' : '⏳ Đang chờ'}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ─── SHOTS TAB ─── */}
        {activeTab === 'shots' && (
          <div className="production-shots-layout">
            <div className="production-shots-list">
              <div className="production-shots-list__header">
                <h3>Danh sách Shots ({shots.length})</h3>
                <button
                  className="btn btn--primary btn--sm"
                  onClick={() => createShot.mutate({ camera_movement: 'Static', focal_length: '35mm', duration_seconds: 5 })}
                  disabled={createShot.isPending}
                >
                  + Thêm Shot
                </button>
              </div>

              {shots.length === 0 ? (
                <div className="empty-state">
                  <p>Chưa có shot nào được tạo. Hãy thêm shot đầu tiên.</p>
                </div>
              ) : (
                <div className="shots-grid">
                  {shots.map((shot) => (
                    <div
                      key={shot.id}
                      className={`shot-card${selectedShot?.id === shot.id ? ' shot-card--selected' : ''}`}
                      onClick={() => setSelectedShotId(shot.id)}
                    >
                      <div className="shot-card__header">
                        <span className="shot-card__number">Shot #{shot.shot_number}</span>
                        <span className="shot-card__status">{shot.status}</span>
                      </div>
                      <div className="shot-card__details">
                        <span>🎥 {shot.camera_movement}</span>
                        <span>🔍 {shot.focal_length}</span>
                        <span>⏱️ {shot.duration_seconds}s</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {selectedShot && (
              <div className="production-shot-inspector">
                <h3>Chi tiết Shot #{selectedShot.shot_number}</h3>
                <dl className="production-dl">
                  <dt>Camera Movement</dt>
                  <dd>{selectedShot.camera_movement}</dd>
                  <dt>Focal Length</dt>
                  <dd>{selectedShot.focal_length}</dd>
                  <dt>Duration</dt>
                  <dd>{selectedShot.duration_seconds} giây</dd>
                  <dt>Trạng thái</dt>
                  <dd>{selectedShot.status}</dd>
                  <dt>Audio Asset</dt>
                  <dd>{selectedShot.audio_asset_id ?? '—'}</dd>
                  <dt>Animation Asset</dt>
                  <dd>{selectedShot.animation_asset_id ?? '—'}</dd>
                  <dt>Render Asset</dt>
                  <dd>{selectedShot.render_asset_id ?? '—'}</dd>
                </dl>
              </div>
            )}
          </div>
        )}

        {/* ─── AUDIO TAB ─── */}
        {activeTab === 'audio' && (
          <div className="production-stage-panel">
            <div className="production-stage-panel__header">
              <div>
                <h3>🎙️ Giai đoạn Audio & Lồng tiếng (TTS)</h3>
                <p>Tạo file âm thanh thoại và tiếng động nền từ kịch bản phân cảnh.</p>
              </div>
              <button
                className="btn btn--primary"
                onClick={() => submitAudio.mutate({ shot_id: selectedShot?.id })}
                disabled={submitAudio.isPending}
              >
                {submitAudio.isPending ? '⏳ Đang gửi...' : '🚀 Bắt đầu tạo Audio'}
              </button>
            </div>

            <div className="production-jobs-list">
              <h4>Tiến trình Audio Jobs ({audioJobs.length})</h4>
              {audioJobs.length === 0 ? (
                <p className="empty-hint">Chưa có audio job nào được gửi.</p>
              ) : (
                audioJobs.map((job) => (
                  <div key={job.job_id} className="production-job-card">
                    <JobProgress job={job} />
                    <JobFailure
                      job={job}
                      onRetry={() => retryJob.mutate(job.job_id)}
                      isRetrying={retryJob.isPending}
                    />
                    <ArtifactPreview artifactId={job.artifact_id} type="audio" />
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ─── ANIMATION TAB ─── */}
        {activeTab === 'animation' && (
          <div className="production-stage-panel">
            <div className="production-stage-panel__header">
              <div>
                <h3>🧊 Giai đoạn Diễn hoạt 3D / Animation</h3>
                <p>Tạo animation curves, camera tracking và visual blockout.</p>
              </div>
              <button
                className="btn btn--primary"
                onClick={() => submitAnimation.mutate({ shot_id: selectedShot?.id })}
                disabled={submitAnimation.isPending}
              >
                {submitAnimation.isPending ? '⏳ Đang gửi...' : '🚀 Bắt đầu Animation Job'}
              </button>
            </div>

            <div className="production-jobs-list">
              <h4>Tiến trình Animation Jobs ({animJobs.length})</h4>
              {animJobs.length === 0 ? (
                <p className="empty-hint">Chưa có animation job nào được gửi.</p>
              ) : (
                animJobs.map((job) => (
                  <div key={job.job_id} className="production-job-card">
                    <JobProgress job={job} />
                    <JobFailure
                      job={job}
                      onRetry={() => retryJob.mutate(job.job_id)}
                      isRetrying={retryJob.isPending}
                    />
                    <ArtifactPreview artifactId={job.artifact_id} type="animation" />
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ─── RENDER TAB ─── */}
        {activeTab === 'render' && (
          <div className="production-stage-panel">
            <div className="production-stage-panel__header">
              <div>
                <h3>🖥️ Giai đoạn Kết xuất (Render Engine)</h3>
                <p>Thực hiện raytracing, compositing và hiệu ứng ánh sáng.</p>
              </div>
              <button
                className="btn btn--primary"
                onClick={() => submitRender.mutate({ shot_id: selectedShot?.id })}
                disabled={submitRender.isPending}
              >
                {submitRender.isPending ? '⏳ Đang gửi...' : '🚀 Bắt đầu Render Job'}
              </button>
            </div>

            <div className="production-jobs-list">
              <h4>Tiến trình Render Jobs ({renderJobs.length})</h4>
              {renderJobs.length === 0 ? (
                <p className="empty-hint">Chưa có render job nào được gửi.</p>
              ) : (
                renderJobs.map((job) => (
                  <div key={job.job_id} className="production-job-card">
                    <JobProgress job={job} />
                    <JobFailure
                      job={job}
                      onRetry={() => retryJob.mutate(job.job_id)}
                      isRetrying={retryJob.isPending}
                    />
                    <ArtifactPreview artifactId={job.artifact_id} type="render" />
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ─── DELIVERY TAB ─── */}
        {activeTab === 'delivery' && (
          <div className="production-stage-panel">
            <div className="production-stage-panel__header">
              <div>
                <h3>📦 Gói xuất bản & Phân phối (Delivery)</h3>
                <p>Xuất bản tập phim hoàn chỉnh sau khi kết xuất tất cả phân cảnh.</p>
              </div>
              <button
                className="btn btn--primary"
                onClick={() => submitVideo.mutate({})}
                disabled={submitVideo.isPending}
              >
                {submitVideo.isPending ? '⏳ Đang xuất...' : '🎬 Đóng gói Video'}
              </button>
            </div>

            {delivery && (
              <div className="delivery-card">
                <h4>Thông tin gói xuất bản</h4>
                <dl className="production-dl">
                  <dt>Độ phân giải</dt><dd>{delivery.resolution}</dd>
                  <dt>Định dạng Codec</dt><dd>{delivery.codec}</dd>
                  <dt>Thời lượng</dt><dd>{delivery.duration_seconds} giây</dd>
                  <dt>Dung lượng</dt><dd>{(delivery.file_size_bytes / (1024 * 1024)).toFixed(1)} MB</dd>
                  <dt>Video Asset ID</dt><dd>{delivery.video_asset_id ?? 'Chưa xuất'}</dd>
                </dl>

                {delivery.video_asset_id && (
                  <ArtifactPreview
                    artifactId={delivery.video_asset_id}
                    type="video"
                    title={`Master Video — ${episodeId}`}
                    url={delivery.download_url}
                  />
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
};
