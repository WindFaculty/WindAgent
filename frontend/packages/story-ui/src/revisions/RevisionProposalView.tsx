import React from 'react';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';

const LONG_TEXT: React.CSSProperties = {
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

const MUTED = { color: '#94a3b8' } as const;

function Badge({ children, color = '#334155', textColor = '#e2e8f0' }: { children: React.ReactNode; color?: string; textColor?: string }) {
  return (
    <span style={{ background: color, color: textColor, fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 12, display: 'inline-block' }}>
      {children}
    </span>
  );
}

function ArtifactHeader({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const hash = artifact.content_hash ?? '';
  return (
    <div style={{ fontSize: 12, marginBottom: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
      <Badge color="#0284c7">{artifact.artifact_type}</Badge>
      <span style={MUTED}>
        · rev {artifact.revision_id ?? '—'} · hash {hash.slice(0, 12)}…
        {artifact.status ? ` · ${artifact.status}` : ''}
      </span>
    </div>
  );
}

export interface RevisionProposalContent {
  proposal_id?: string;
  draft_id?: string;
  review_report_id?: string;
  revision_reason?: string;
  accepted_finding_codes?: string[];
  iteration_number?: number;
  maximum_iterations?: number;
}

export function RevisionProposalView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = (artifact.content as RevisionProposalContent) ?? {};
  const findings = c.accepted_finding_codes ?? [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <ArtifactHeader artifact={artifact} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Badge color="#fbbf24" textColor="#0f172a">Revision Proposal</Badge>
          <span style={{ fontWeight: 700, fontSize: 16, color: '#e2e8f0' }}>
            Revision {artifact.revision_id ?? 'Proposal'}
          </span>
        </div>
        {typeof c.iteration_number === 'number' && typeof c.maximum_iterations === 'number' && (
          <span style={{ ...MUTED, fontSize: 13 }}>Iteration {c.iteration_number}/{c.maximum_iterations}</span>
        )}
      </div>

      {c.revision_reason && (
        <div style={{ ...LONG_TEXT, background: '#1e293b', border: '1px solid #334155', borderRadius: 8, padding: 12, fontSize: 13, color: '#cbd5e1' }}>
          <b>Revision Reason:</b> {c.revision_reason}
        </div>
      )}

      {findings.length > 0 && (
        <div style={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', marginBottom: 6 }}>
            Addresses: {findings.join(', ')}
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {findings.map((code) => (
              <Badge key={code} color="#14532d" textColor="#4ade80">✓ {code}</Badge>
            ))}
          </div>
        </div>
      )}

      <div style={{ ...MUTED, fontSize: 12, display: 'flex', gap: 12 }}>
        {c.proposal_id && <span>proposal {c.proposal_id}</span>}
        {c.draft_id && <span>draft {c.draft_id}</span>}
        {c.review_report_id && <span>review report {c.review_report_id}</span>}
      </div>
    </div>
  );
}
