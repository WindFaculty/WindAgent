import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';

import { IdeaSetView, SelectedIdeaView } from '../idea/IdeaSetView';
import { StoryBibleView, WorldBibleView, CharacterCanonView, BeatsView } from '../story/StoryBibleView';
import { OutlineView } from '../outline/OutlineView';
import { ScreenplayView } from '../screenplay/ScreenplayView';
import { ReviewReportView } from '../review/ReviewReportView';
import { RevisionProposalView } from '../revisions/RevisionProposalView';
import { LockReceiptView, LockPackageView } from '../approval/ApprovalBar';

const MUTED = { color: '#94a3b8' } as const;

function ArtifactHeader({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const hash = artifact.content_hash ?? '';
  return (
    <div style={{ fontSize: 12, marginBottom: 4 }}>
      <span>{artifact.artifact_type}</span>{' '}
      <span style={MUTED}>
        · rev {artifact.revision_id ?? '—'} · hash {hash.slice(0, 12)}…
        {artifact.status ? ` · ${artifact.status}` : ''}
      </span>
    </div>
  );
}

function Provenance({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const parts: string[] = [];
  if (artifact.provider_id) parts.push(`provider ${artifact.provider_id}`);
  if (artifact.canonical_model_id) parts.push(`canonical ${artifact.canonical_model_id}`);
  if (artifact.provider_model_id) parts.push(`model ${artifact.provider_model_id}`);
  else if (artifact.model_id) parts.push(`model ${artifact.model_id}`);
  if (artifact.endpoint_id) parts.push(`endpoint ${artifact.endpoint_id}`);
  if (artifact.provider_binding_id) parts.push(`binding ${artifact.provider_binding_id}`);
  if (artifact.model_route_id) parts.push(`route ${artifact.model_route_id}`);
  if (artifact.provider_attempt_id) parts.push(`attempt ${artifact.provider_attempt_id}`);
  if (artifact.prompt_id) parts.push(`prompt ${artifact.prompt_id}`);
  if (artifact.prompt_version) parts.push(`prompt version ${artifact.prompt_version}`);
  if (artifact.output_schema_contract) parts.push(`schema ${artifact.output_schema_contract}`);
  if (parts.length === 0) return null;
  return (
    <div style={{ ...MUTED, fontSize: 12, marginTop: 6 }}>
      Provenance: {parts.join(' · ')}
    </div>
  );
}

export function GenericArtifactView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const keys = Object.keys(artifact.content ?? {});
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      <div style={MUTED}>
        {artifact.artifact_type} persisted — {keys.length > 0 ? `${keys.length} content fields` : 'no content fields'}.
      </div>
      <Provenance artifact={artifact} />
    </div>
  );
}

export function UnsupportedArtifactView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  return (
    <div role="note" aria-label="Unsupported artifact version">
      <ArtifactHeader artifact={artifact} />
      <div style={{ color: '#fbbf24' }}>
        unsupported schema {artifact.schema_version} — {artifact.artifact_type} cannot be rendered by
        this build.
      </div>
    </div>
  );
}

export function ArtifactContentView({
  artifact,
  onSelectIdea,
  selectDisabled,
  isLocked,
}: {
  artifact: StudioArtifactEnvelope;
  onSelectIdea?: (candidateId: string) => void;
  selectDisabled?: boolean;
  isLocked?: boolean;
}) {
  if (!artifact.schema_version.startsWith('studio.artifact/v1alpha1')) {
    return <UnsupportedArtifactView artifact={artifact} />;
  }

  const safe: StudioArtifactEnvelope = artifact.content
    ? artifact
    : { ...artifact, content: {} };

  switch (safe.artifact_type) {
    case 'IdeaCandidateSet':
      return onSelectIdea
        ? <IdeaSetView artifact={safe} onSelect={onSelectIdea} disabled={selectDisabled} />
        : <IdeaSetView artifact={safe} onSelect={() => undefined} disabled />;
    case 'SelectedIdea':
      return <SelectedIdeaView artifact={safe} />;
    case 'StoryBible':
      return <StoryBibleView artifact={safe} />;
    case 'WorldBible':
      return <WorldBibleView artifact={safe} />;
    case 'CharacterCanon':
      return <CharacterCanonView artifact={safe} />;
    case 'BeatSheet':
      return <BeatsView artifact={safe} />;
    case 'EpisodeOutline':
      return <OutlineView artifact={safe} />;
    case 'ScreenplayDraft':
      return <ScreenplayView artifact={safe} isLocked={isLocked} />;
    case 'ReviewReport':
      return <ReviewReportView artifact={safe} />;
    case 'RevisionProposal':
      return <RevisionProposalView artifact={safe} />;
    case 'LockedScreenplayReceipt':
      return <LockReceiptView artifact={safe} />;
    case 'LockedScreenplayPackage':
      return <LockPackageView artifact={safe} />;
    default:
      return <GenericArtifactView artifact={safe} />;
  }
}
