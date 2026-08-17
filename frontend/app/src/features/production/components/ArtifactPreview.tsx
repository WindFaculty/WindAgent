/**
 * Phase 10 — ArtifactPreview Component
 * Displays output artifacts from production stages (Audio, Animation, Render, Delivery).
 */
import React from 'react';

interface ArtifactPreviewProps {
  artifactId?: string | null;
  type: 'audio' | 'animation' | 'render' | 'video';
  title?: string;
  url?: string | null;
}

const TYPE_ICONS: Record<string, string> = {
  audio: '🎵',
  animation: '🧊',
  render: '🎬',
  video: '🎞️',
};

export const ArtifactPreview: React.FC<ArtifactPreviewProps> = ({
  artifactId,
  type,
  title,
  url,
}) => {
  if (!artifactId && !url) {
    return (
      <div className="artifact-preview artifact-preview--empty">
        <span className="artifact-preview__icon">{TYPE_ICONS[type] ?? '📦'}</span>
        <span className="artifact-preview__label">Chưa có output artifact</span>
      </div>
    );
  }

  return (
    <div className="artifact-preview">
      <div className="artifact-preview__icon">{TYPE_ICONS[type] ?? '📦'}</div>
      <div className="artifact-preview__details">
        <div className="artifact-preview__title">{title ?? `Artifact ${type.toUpperCase()}`}</div>
        {artifactId && <code className="artifact-preview__id">#{artifactId}</code>}
      </div>
      {url && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn--secondary btn--sm artifact-preview__action"
        >
          Mở xem
        </a>
      )}
    </div>
  );
};
