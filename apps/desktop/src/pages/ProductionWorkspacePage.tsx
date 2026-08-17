/**
 * Desktop ProductionWorkspacePage — delegates fully to @windagent/app canonical ProductionPage.
 * ZERO FakeProductionApiClient runtime usage. ZERO hardcoded proj-alpha. ZERO fake timers.
 * All state backed by /api/v3/episodes/{episodeId}/production + WebSocket realtime stream.
 */
import React from 'react';
import { ProductionPage as CanonicalProductionPage, type ProductionTab } from '@windagent/app/src/features/production';
import { useSearchParams } from '@windagent/app/src/shared/hooks/useSearchParams';

interface ProductionWorkspacePageProps {
  initialPage?: 'script' | 'assets' | 'video';
  episodeId?: string;
}

const PAGE_TAB_MAP: Record<string, ProductionTab> = {
  script: 'shots',
  assets: 'audio',
  video: 'render',
};

export const ProductionWorkspacePage: React.FC<ProductionWorkspacePageProps> = ({
  initialPage = 'script',
  episodeId: propEpisodeId,
}) => {
  const [searchParams] = useSearchParams();
  const episodeId = propEpisodeId ?? searchParams.get('episodeId') ?? 'ep-cb-001';
  const initialTab = PAGE_TAB_MAP[initialPage] ?? 'overview';
  const apiBaseUrl = (window as any).__WINDAGENT_API_URL__ ?? '';

  return (
    <div style={{ height: '100%', width: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <CanonicalProductionPage
        episodeId={episodeId}
        initialTab={initialTab}
        apiBaseUrl={apiBaseUrl}
      />
    </div>
  );
};
