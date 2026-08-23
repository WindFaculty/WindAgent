/**
 * P1.7 — ProductionPage
 * Canonical Episode-Centric Pre-Production Workspace.
 * ZERO FakeProductionApiClient. ZERO hardcoded proj-alpha. ZERO fake timers.
 * Fully backed by /api/v3/episodes/{episodeId}/production + WebSocket stream.
 *
 * P1 truth rules: the fake Render / Animate / Generate-Video buttons are GONE.
 * The default tab is the Production Readiness gate (P1.6 preflight) with an
 * explicit Finalize action producing a content-addressed package. Stage tabs
 * below are honest, read-only job history viewers — engine executors arrive
 * in P2 and no button pretends otherwise.
 */
import React, { useState } from 'react';
import {
  useProductionPlan,
  useShots,
  useCreateShot,
  useProductionJobs,
  useDeliveryArtifact,
  useProductionRealtime,
} from '../hooks/useProduction';
import { JobProgress } from '../components/JobProgress';
import { JobFailure } from '../components/JobFailure';
import { ArtifactPreview } from '../components/ArtifactPreview';
import { ProductionReadiness } from '../components/ProductionReadiness';

export type ProductionTab = 'readiness' | 'overview' | 'shots' | 'audio' | 'animation' | 'render' | 'delivery';

interface ProductionPageProps {
  episodeId: string;
  initialTab?: ProductionTab;
  apiBaseUrl?: string;
}

/** Honest notice rendered in every stage panel: P1 ships no executor. */
const StagePendingNotice: React.FC<{ stage: string }> = ({ stage }) => (
  <div className="production-stage-panel__notice">
    <strong>P1 chưa kết nối executor {stage}.</strong>{' '}
    Không thể gửi job mới từ giao diện — danh sách dưới đây chỉ là lịch sử job
    đọc-cho-muộn từ API. Luồng bàn giao pre-production nằm ở tab{' '}
    <em>Readiness</em> (Production Package).
  </div>
);

export const ProductionPage: React.FC<ProductionPageProps> = ({
  episodeId,
  initialTab = 'readiness',
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

  const selectedShot = shots.find((s: any) => s.id === selectedShotId) ?? shots[0] ?? null;

  const audioJobs = jobs.filter((j: any) => j.job_type === 'AUDIO');
  const animJobs = jobs.filter((j: any) => j.job_type === 'ANIMATION');
  const renderJobs = jobs.filter((j: any) => j.job_type === 'RENDER');

  const tabs: { id: ProductionTab; label: string; count?: number }[] = [
    { id: 'readiness', label: '✅ Readiness' },
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
            <span className="production-stat__value">{jobs.filter((j: any) => j.state === 'SUCCEEDED').length}/{jobs.length}</span>
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
        {/* ─── READINESS TAB (P1.7 default) ─── */}
        {activeTab === 'readiness' && (
          <ProductionReadiness episodeId={episodeId} />
        )}

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
                <h3>🚦 Trạng thái pre-production</h3>
                <p className="empty-hint">
                  P1 kết thúc ở ranh giới pre-production: gate chân thực duy nhất
                  là Production Readiness. Xem checklist trực tiếp tại tab{' '}
                  <em>Readiness</em>.
                </p>
                <div className="production-stage-checklist">
                  <div className={`production-stage-item ${shots.length > 0 ? 'done' : ''}`}>
                    <span>1. Phân cảnh (Shot Plan)</span>
                    <span>{shots.length > 0 ? `✅ ${shots.length} shots` : '⏳ Chưa có'}</span>
                  </div>
                  <div className={`production-stage-item ${audioJobs.some((j: any) => j.state === 'SUCCEEDED') ? 'done' : ''}`}>
                    <span>2. Thực thi engine (Audio → Animation → Render)</span>
                    <span>⏳ P2</span>
                  </div>
                  <div className={`production-stage-item ${delivery?.video_asset_id ? 'done' : ''}`}>
                    <span>3. Xuất bản (Delivery)</span>
                    <span>⏳ P2</span>
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
                  {shots.map((shot: any) => (
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

        {/* ─── AUDIO TAB (read-only job history) ─── */}
        {activeTab === 'audio' && (
          <div className="production-stage-panel">
            <div className="production-stage-panel__header">
              <div>
                <h3>🎙️ Giai đoạn Audio & Lồng tiếng (TTS)</h3>
                <p>Tạo file âm thanh thoại và tiếng động nền từ kịch bản phân cảnh.</p>
              </div>
            </div>

            <StagePendingNotice stage="Audio/TTS" />

            <div className="production-jobs-list">
              <h4>Lịch sử Audio Jobs ({audioJobs.length})</h4>
              {audioJobs.length === 0 ? (
                <p className="empty-hint">Chưa có audio job nào trong lịch sử.</p>
              ) : (
                audioJobs.map((job: any) => (
                  <div key={job.job_id} className="production-job-card">
                    <JobProgress job={job} />
                    <JobFailure job={job} />
                    <ArtifactPreview artifactId={job.artifact_id} type="audio" />
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ─── ANIMATION TAB (read-only job history) ─── */}
        {activeTab === 'animation' && (
          <div className="production-stage-panel">
            <div className="production-stage-panel__header">
              <div>
                <h3>🧊 Giai đoạn Diễn hoạt 3D / Animation</h3>
                <p>Tạo animation curves, camera tracking và visual blockout.</p>
              </div>
            </div>

            <StagePendingNotice stage="Animation" />

            <div className="production-jobs-list">
              <h4>Lịch sử Animation Jobs ({animJobs.length})</h4>
              {animJobs.length === 0 ? (
                <p className="empty-hint">Chưa có animation job nào trong lịch sử.</p>
              ) : (
                animJobs.map((job: any) => (
                  <div key={job.job_id} className="production-job-card">
                    <JobProgress job={job} />
                    <JobFailure job={job} />
                    <ArtifactPreview artifactId={job.artifact_id} type="animation" />
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ─── RENDER TAB (read-only job history) ─── */}
        {activeTab === 'render' && (
          <div className="production-stage-panel">
            <div className="production-stage-panel__header">
              <div>
                <h3>🖥️ Giai đoạn Kết xuất (Render Engine)</h3>
                <p>Thực hiện raytracing, compositing và hiệu ứng ánh sáng.</p>
              </div>
            </div>

            <StagePendingNotice stage="Render" />

            <div className="production-jobs-list">
              <h4>Lịch sử Render Jobs ({renderJobs.length})</h4>
              {renderJobs.length === 0 ? (
                <p className="empty-hint">Chưa có render job nào trong lịch sử.</p>
              ) : (
                renderJobs.map((job: any) => (
                  <div key={job.job_id} className="production-job-card">
                    <JobProgress job={job} />
                    <JobFailure job={job} />
                    <ArtifactPreview artifactId={job.artifact_id} type="render" />
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ─── DELIVERY TAB (read-only) ─── */}
        {activeTab === 'delivery' && (
          <div className="production-stage-panel">
            <div className="production-stage-panel__header">
              <div>
                <h3>📦 Gói xuất bản & Phân phối (Delivery)</h3>
                <p>Xuất bản tập phim hoàn chỉnh sau khi kết xuất tất cả phân cảnh.</p>
              </div>
            </div>

            <StagePendingNotice stage="Video/Delivery" />

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
