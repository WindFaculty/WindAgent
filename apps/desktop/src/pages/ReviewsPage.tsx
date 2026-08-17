/**
 * Desktop ReviewsPage — delegates fully to @windagent/app canonical ReviewsPage.
 * ZERO DEFAULT_VERSIONS. ZERO DEFAULT_COMMENTS.
 * Decisions are pinned to revision_id + expected_version.
 */
import { ReviewsPage as CanonicalReviewsPage } from '@windagent/app/src/features/reviews';
import { useSearchParams } from '@windagent/app/src/shared/hooks/useSearchParams';

export function ReviewsPage() {
  const [searchParams] = useSearchParams();
  const episodeId = searchParams.get('episodeId') ?? undefined;
  const projectId = searchParams.get('projectId') ?? undefined;
  return <CanonicalReviewsPage episodeId={episodeId} projectId={projectId} />;
}
