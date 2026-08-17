/**
 * Desktop CharactersPage — delegates fully to @windagent/app canonical CharactersPage.
 * ZERO DEFAULT_CHARACTERS. All data from /api/v3/projects/{id}/characters.
 */
import { CharactersPage as CanonicalCharactersPage } from '@windagent/app/src/features/characters';
import { useSearchParams } from '@windagent/app/src/shared/hooks/useSearchParams';

export function CharactersPage() {
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get('projectId') ?? 'proj-cyberpunk-01';
  return <CanonicalCharactersPage projectId={projectId} />;
}
