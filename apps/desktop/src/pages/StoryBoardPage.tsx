/**
 * Desktop StoryBoardPage — delegates fully to @windagent/app canonical StoryboardPage.
 * ZERO DEFAULT_SCENES. ZERO setTimeout fake timers. ZERO hardcoded image URLs.
 * All data from /api/v3/episodes/{id}/storyboard + WebSocket realtime.
 */
import { StoryboardPage as CanonicalStoryboardPage } from '@windagent/app/src/features/storyboard';
import { useSearchParams } from '@windagent/app/src/shared/hooks/useSearchParams';

export function StoryBoardPage() {
  const [searchParams] = useSearchParams();
  const episodeId = searchParams.get('episodeId') ?? 'ep-cb-001';
  const apiBaseUrl = (window as any).__WINDAGENT_API_URL__ ?? '';
  return <CanonicalStoryboardPage episodeId={episodeId} apiBaseUrl={apiBaseUrl} />;
}
