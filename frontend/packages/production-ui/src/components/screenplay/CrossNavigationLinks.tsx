import React from 'react';
import { ProductionRouteCodec } from '@windagent/production-contracts';

interface CrossNavigationLinksProps {
  projectId: string;
  revisionId?: string;
  sceneId?: string;
  entityId?: string;
  assetId?: string;
  requirementId?: string;
  onNavigate?: (url: string) => void;
}

export const CrossNavigationLinks: React.FC<CrossNavigationLinksProps> = ({
  projectId,
  revisionId,
  sceneId,
  entityId,
  assetId,
  requirementId,
  onNavigate,
}) => {
  const handleOpenAsset = () => {
    if (!assetId) return;
    const url = ProductionRouteCodec.stringifyRoute({
      projectId,
      page: 'assets',
      revisionId,
      assetId,
      entityId,
    });
    if (onNavigate) {
      onNavigate(url);
    } else {
      window.history.pushState({}, '', url);
    }
  };

  const handleOpenScript = () => {
    const url = ProductionRouteCodec.stringifyRoute({
      projectId,
      page: 'script',
      revisionId,
      sceneId,
      entityId,
    });
    if (onNavigate) {
      onNavigate(url);
    } else {
      window.history.pushState({}, '', url);
    }
  };

  return (
    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
      {assetId && (
        <button
          onClick={handleOpenAsset}
          style={{
            padding: '0.35rem 0.65rem',
            borderRadius: '4px',
            backgroundColor: '#313244',
            border: '1px solid #45475A',
            color: '#89B4FA',
            fontSize: '0.75rem',
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
          }}
        >
          🔍 View Asset ({assetId})
        </button>
      )}

      {sceneId && (
        <button
          onClick={handleOpenScript}
          style={{
            padding: '0.35rem 0.65rem',
            borderRadius: '4px',
            backgroundColor: '#313244',
            border: '1px solid #45475A',
            color: '#A6E3A1',
            fontSize: '0.75rem',
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
          }}
        >
          🎬 Open Scene ({sceneId})
        </button>
      )}
    </div>
  );
};
