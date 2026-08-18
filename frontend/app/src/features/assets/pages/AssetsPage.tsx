/**
 * Phase 9E — AssetsPage
 * Canonical asset catalog with provenance chain.
 * ZERO hardcoded media URLs as runtime dependencies.
 */
import React, { useState } from 'react';
import { useAssets, useAssetRevisions, useAssetProvenance, useApproveAsset, useRejectAsset } from '../hooks/useAssets';
import type { AssetResource, AssetType } from '@windagent/api-contracts';

interface AssetsPageProps {
  episodeId?: string;
  projectId?: string;
}

const TYPE_LABELS: Record<AssetType, string> = {
  IMAGE: '🖼 Hình ảnh',
  AUDIO: '🎵 Âm thanh',
  VIDEO: '🎬 Video',
  MODEL_3D: '🧊 3D Model',
  REFERENCE: '📎 Tham khảo',
};

const STATUS_COLORS: Record<string, string> = {
  DRAFT: '#6b7280',
  APPROVED: '#22c55e',
  REJECTED: '#ef4444',
};

export const AssetsPage: React.FC<AssetsPageProps> = ({ episodeId, projectId }) => {
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>('');

  const { data: assets = [], isLoading, error } = useAssets({ episode_id: episodeId, project_id: projectId, type: typeFilter || undefined });

  if (isLoading) {
    return (
      <div className="assets-page assets-page--loading">
        <div className="loading-spinner" />
        <p>Đang tải assets...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="assets-page assets-page--error">
        <h3>Không thể tải assets</h3>
        <p>{(error as Error).message}</p>
      </div>
    );
  }

  return (
    <div className="assets-page">
      <header className="assets-page__header">
        <h1>Assets</h1>
        <div className="assets-page__filters">
          <select
            className="form-select form-select--sm"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">Tất cả loại</option>
            <option value="IMAGE">Hình ảnh</option>
            <option value="AUDIO">Âm thanh</option>
            <option value="VIDEO">Video</option>
            <option value="MODEL_3D">3D Model</option>
          </select>
          <span className="assets-page__count">{assets.length} assets</span>
        </div>
      </header>

      <div className="assets-page__layout">
        <div className="assets-page__grid">
          {assets.length === 0 ? (
            <div className="assets-page__empty">
              <span>🗂</span>
              <p>Chưa có asset nào</p>
            </div>
          ) : (
            assets.map((asset: AssetResource) => (
              <AssetCard
                key={asset.id}
                asset={asset}
                isSelected={selectedAssetId === asset.id}
                onSelect={() => setSelectedAssetId(asset.id === selectedAssetId ? null : asset.id)}
              />
            ))
          )}
        </div>

        {selectedAssetId && (
          <div className="assets-page__sidebar">
            <AssetDetail assetId={selectedAssetId} onClose={() => setSelectedAssetId(null)} />
          </div>
        )}
      </div>
    </div>
  );
};

function AssetCard({ asset, isSelected, onSelect }: { asset: AssetResource; isSelected: boolean; onSelect: () => void }) {
  const statusColor = STATUS_COLORS[asset.status] ?? '#6b7280';
  return (
    <div className={`asset-card${isSelected ? ' asset-card--selected' : ''}`} onClick={onSelect}>
      <div className="asset-card__preview">
        {asset.type === 'IMAGE' && asset.current_revision_id ? (
          <div className="asset-card__image-placeholder">🖼</div>
        ) : (
          <div className="asset-card__type-icon">{TYPE_LABELS[asset.type as AssetType] ?? asset.type}</div>
        )}
      </div>

      <div className="asset-card__body">
        <h4 className="asset-card__name">{asset.name}</h4>
        <div className="asset-card__meta">
          <span className="asset-card__type">{TYPE_LABELS[asset.type as AssetType] ?? asset.type}</span>
          <span
            className="asset-card__status"
            style={{ color: statusColor }}
          >
            {asset.status}
          </span>
        </div>
        <div className="asset-card__provenance">
          <span>🔬 {asset.provenance.source}</span>
          {asset.provenance.generator && <span>{asset.provenance.generator}</span>}
          <span className="asset-card__hash">#{asset.provenance.content_hash.slice(0, 8)}</span>
        </div>
        <div className="asset-card__revision">v{asset.version}</div>
      </div>
    </div>
  );
}

function AssetDetail({ assetId, onClose }: { assetId: string; onClose: () => void }) {
  const { data: revisions = [] } = useAssetRevisions(assetId);
  const { data: provenance } = useAssetProvenance(assetId);
  const approveAsset = useApproveAsset(assetId);
  const rejectAsset = useRejectAsset(assetId);

  const latestRevision = revisions[revisions.length - 1];

  return (
    <div className="asset-detail">
      <div className="asset-detail__header">
        <h3>Chi tiết Asset</h3>
        <button className="asset-detail__close" onClick={onClose}>✕</button>
      </div>

      {provenance && (
        <div className="asset-detail__provenance">
          <h4>Provenance Chain</h4>
          <dl>
            <dt>Nguồn gốc</dt><dd>{provenance.source}</dd>
            {provenance.generator && <><dt>Generator</dt><dd>{provenance.generator}</dd></>}
            {provenance.model && <><dt>Model</dt><dd>{provenance.model}</dd></>}
            {provenance.job_id && <><dt>Job ID</dt><dd>{provenance.job_id}</dd></>}
            <dt>Content Hash</dt><dd className="asset-detail__hash">{provenance.content_hash}</dd>
            {provenance.parent_revision_id && <><dt>Parent Revision</dt><dd>{provenance.parent_revision_id}</dd></>}
            {provenance.prompt && (
              <><dt>Prompt</dt><dd className="asset-detail__prompt">{provenance.prompt}</dd></>
            )}
          </dl>
        </div>
      )}

      <div className="asset-detail__revisions">
        <h4>Lịch sử phiên bản ({revisions.length})</h4>
        {revisions.map((rev: any) => (
          <div key={rev.revision_id} className="asset-revision">
            <span className="asset-revision__version">v{rev.version}</span>
            <span className="asset-revision__status" style={{ color: STATUS_COLORS[rev.status] ?? '#6b7280' }}>{rev.status}</span>
            <span className="asset-revision__hash">#{rev.provenance.content_hash.slice(0, 8)}</span>
          </div>
        ))}
      </div>

      {latestRevision && latestRevision.status === 'DRAFT' && (
        <div className="asset-detail__actions">
          <button
            className="btn btn--success btn--sm"
            disabled={approveAsset.isPending}
            onClick={() => approveAsset.mutate({ revision_id: latestRevision.revision_id, approved_by: 'User' })}
          >
            ✅ Duyệt
          </button>
          <button
            className="btn btn--danger btn--sm"
            disabled={rejectAsset.isPending}
            onClick={() => rejectAsset.mutate({ revision_id: latestRevision.revision_id, rejected_by: 'User' })}
          >
            ✕ Từ chối
          </button>
        </div>
      )}
    </div>
  );
}
