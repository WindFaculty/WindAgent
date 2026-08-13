import React from 'react';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';

const LONG_TEXT: React.CSSProperties = {
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

const MUTED = { color: '#94a3b8' } as const;

function Badge({ children, variant = 'default' }: { children: React.ReactNode; variant?: 'default' | 'gold' | 'danger' | 'success' | 'info' | 'slate' }) {
  let bg = '#334155';
  let color = '#e2e8f0';
  if (variant === 'gold') {
    bg = '#78350f';
    color = '#fbbf24';
  } else if (variant === 'danger') {
    bg = '#7f1d1d';
    color = '#fca5a5';
  } else if (variant === 'success') {
    bg = '#14532d';
    color = '#4ade80';
  } else if (variant === 'info') {
    bg = '#0284c7';
    color = '#ffffff';
  } else if (variant === 'slate') {
    bg = '#1e293b';
    color = '#94a3b8';
  }
  return (
    <span style={{ background: bg, color, fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 12, display: 'inline-block' }}>
      {children}
    </span>
  );
}

function ArtifactHeader({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const hash = artifact.content_hash ?? '';
  return (
    <div style={{ fontSize: 12, marginBottom: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
      <Badge variant="info">{artifact.artifact_type}</Badge>
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
    <div style={{ ...MUTED, fontSize: 12, marginTop: 4 }}>
      Provenance: {parts.join(' · ')}
    </div>
  );
}

export interface ReviewFinding {
  code?: string;
  dimension?: string | null;
  severity?: string;
  location?: string;
  evidence?: string;
  remediation?: string;
  source?: string;
}

export interface ReviewReportContent {
  report_id?: string;
  draft_id?: string;
  verdict?: string;
  quality_summary?: string;
  review_iteration?: number;
  maximum_iterations?: number;
  dimensions?: Array<{ dimension?: string; score?: number; blocking?: boolean; note?: string }>;
  findings?: ReviewFinding[];
}

export function ReviewReportView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = (artifact.content as ReviewReportContent) ?? {};
  const findings = c.findings ?? [];
  const dimensions = c.dimensions ?? [];

  let verdictVariant: 'success' | 'danger' | 'gold' | 'info' = 'info';
  if (c.verdict === 'APPROVED' || c.verdict === 'PASSED') verdictVariant = 'success';
  else if (c.verdict === 'REJECTED' || c.verdict === 'FAILED') verdictVariant = 'danger';
  else if (c.verdict === 'REVISION_REQUIRED' || c.verdict === 'REVIEW_REQUIRED') verdictVariant = 'gold';

  // Group findings by severity
  const blockingFindings = findings.filter((f) => f.severity?.toUpperCase() === 'BLOCKING');
  const majorFindings = findings.filter((f) => ['MAJOR', 'WARNING'].includes(f.severity?.toUpperCase() ?? ''));
  const minorFindings = findings.filter((f) => ['MINOR', 'INFO'].includes(f.severity?.toUpperCase() ?? ''));
  const suggestions = findings.filter((f) => ['SUGGESTION', 'NOTE'].includes(f.severity?.toUpperCase() ?? ''));
  const otherFindings = findings.filter(
    (f) => !['BLOCKING', 'MAJOR', 'WARNING', 'MINOR', 'INFO', 'SUGGESTION', 'NOTE'].includes(f.severity?.toUpperCase() ?? '')
  );

  const categorized = [
    { title: 'BLOCKING FINDINGS', items: blockingFindings, variant: 'danger' as const },
    { title: 'MAJOR FINDINGS', items: majorFindings, variant: 'gold' as const },
    { title: 'MINOR FINDINGS', items: minorFindings, variant: 'info' as const },
    { title: 'SUGGESTIONS & NOTES', items: suggestions, variant: 'slate' as const },
    { title: 'OTHER FINDINGS', items: otherFindings, variant: 'default' as const },
  ].filter((group) => group.items.length > 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <ArtifactHeader artifact={artifact} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Badge variant={verdictVariant}>{c.verdict ?? 'REVIEW_REQUIRED'}</Badge>
          <span style={{ fontWeight: 700, fontSize: 16, color: '#e2e8f0' }}>Review Report</span>
        </div>
        {typeof c.review_iteration === 'number' && typeof c.maximum_iterations === 'number' && (
          <span style={{ ...MUTED, fontSize: 13 }}>Iteration {c.review_iteration}/{c.maximum_iterations}</span>
        )}
      </div>

      <Provenance artifact={artifact} />

      {c.quality_summary && (
        <div style={{ ...LONG_TEXT, background: '#1e293b', border: '1px solid #334155', borderRadius: 8, padding: 12, fontSize: 13, color: '#cbd5e1' }}>
          <b>Quality Summary:</b> {c.quality_summary}
        </div>
      )}

      {/* Dimensions Grid */}
      {dimensions.length > 0 && (
        <div style={{ background: '#0f172a', border: '1px solid #334155', padding: 12, borderRadius: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', marginBottom: 8 }}>
            Scoring Dimensions
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
            {dimensions.map((d) => (
              <div key={d.dimension} style={{ background: '#1e293b', padding: 8, borderRadius: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, color: '#cbd5e1', fontWeight: 600 }}>{d.dimension}</span>
                  {d.blocking && <Badge variant="danger">blocking</Badge>}
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: d.blocking ? '#fca5a5' : '#4ade80' }}>
                  {typeof d.score === 'number' ? d.score.toFixed(2) : '—'}
                </div>
                {d.note && <div style={{ ...MUTED, fontSize: 11 }}>{d.note}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Categorized Findings */}
      {findings.length === 0 && <div style={MUTED}>No quality findings recorded.</div>}

      {categorized.map((group) => (
        <div key={group.title} style={{ marginTop: 4 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', marginBottom: 6 }}>
            {group.title} ({group.items.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {group.items.map((f, idx) => (
              <div
                key={f.code ?? idx}
                style={{
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: 6,
                  padding: 10,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <Badge variant={group.variant}>{f.severity ?? 'FINDING'}</Badge>
                    <span style={{ fontWeight: 600, fontSize: 13, color: '#e2e8f0' }}>{f.code ?? `finding_${idx + 1}`}</span>
                  </div>
                  {f.dimension && <span style={{ ...MUTED, fontSize: 12 }}>{f.dimension}</span>}
                </div>

                {f.location && <div style={{ ...MUTED, fontSize: 12 }}>{f.location.startsWith('at ') ? f.location : `at ${f.location}`}</div>}
                {f.evidence && <div style={{ ...LONG_TEXT, fontSize: 13, color: '#cbd5e1' }}><b>Evidence:</b> {f.evidence}</div>}
                {f.remediation && <div style={{ ...LONG_TEXT, fontSize: 13, color: '#7dd3fc' }}><b>Remediation:</b> {f.remediation}</div>}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
