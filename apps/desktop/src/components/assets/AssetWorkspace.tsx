/**
 * Desktop AssetWorkspace — delegates fully to @windagent/app canonical AssetsPage (V3).
 * Eliminates legacy direct /api/v2/video-production/assets calls.
 */
import React from 'react';
import { AssetsPage as CanonicalAssetsPage } from '@windagent/app/src/features/assets';
import { useSearchParams } from '@windagent/app/src/shared/hooks/useSearchParams';

export const AssetWorkspace: React.FC<{ projectId?: string; episodeId?: string }> = ({
  projectId: propProjectId,
  episodeId: propEpisodeId,
}) => {
  const [searchParams] = useSearchParams();
  const projectId = propProjectId ?? searchParams.get('projectId') ?? undefined;
  const episodeId = propEpisodeId ?? searchParams.get('episodeId') ?? undefined;

  return <CanonicalAssetsPage projectId={projectId} episodeId={episodeId} />;
};
