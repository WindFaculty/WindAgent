import React from 'react';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';

const LONG_TEXT: React.CSSProperties = {
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

const MUTED = { color: '#94a3b8' } as const;

function Badge({ children, variant = 'default' }: { children: React.ReactNode; variant?: 'default' | 'gold' | 'danger' | 'success' }) {
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
  }
  return (
    <span style={{ background: bg, color, fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 12, display: 'inline-block' }}>
      {children}
    </span>
  );
}

export interface IdeaCandidateContent {
  candidate_id: string;
  title: string;
  logline?: string;
  premise?: string;
  summary?: string;
  score?: number | null;
  score_dimensions?: Record<string, number>;
  safety_ok?: boolean;
  themes?: string[];
}

export interface IdeaSetContent {
  candidates?: IdeaCandidateContent[];
  evaluated?: boolean;
  recommended_candidate_id?: string | null;
  scoring_rubric_version?: string | null;
}

export interface SelectedIdeaContent {
  title?: string;
  summary?: string;
  rationale?: string;
  candidate_id?: string;
  source_set_id?: string;
  selection_policy?: string;
  score?: number | null;
  score_dimensions?: Record<string, number>;
}

function ScoreRows({ dimensions }: { dimensions?: Record<string, number> }) {
  if (!dimensions || Object.keys(dimensions).length === 0) return null;
  const entries = Object.entries(dimensions).sort(([a], [b]) => a.localeCompare(b));
  return (
    <div style={{ margin: '8px 0 4px', background: '#0f172a', padding: 8, borderRadius: 6 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: '#94a3b8', marginBottom: 4, textTransform: 'uppercase' }}>
        Score Breakdown
      </div>
      <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '2px 12px', margin: 0, fontSize: 12 }}>
        {entries.map(([name, value]) => (
          <React.Fragment key={name}>
            <dt style={{ color: '#94a3b8' }}>{name}</dt>
            <dd style={{ margin: 0, textAlign: 'right', fontWeight: 600, color: '#e2e8f0' }}>
              {typeof value === 'number' ? value.toFixed(3) : String(value)}
            </dd>
          </React.Fragment>
        ))}
      </dl>
    </div>
  );
}

function ArtifactHeader({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const hash = artifact.content_hash ?? '';
  return (
    <div style={{ fontSize: 12, marginBottom: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
      <Badge variant="default">{artifact.artifact_type}</Badge>
      <span style={MUTED}>
        rev {artifact.revision_id ?? '—'} · hash {hash.slice(0, 12)}…
        {artifact.status ? ` · ${artifact.status}` : ''}
      </span>
    </div>
  );
}

export function IdeaSetView({
  artifact,
  onSelect,
  disabled,
}: {
  artifact: StudioArtifactEnvelope;
  onSelect: (candidateId: string) => void;
  disabled?: boolean;
}) {
  const content = (artifact.content as IdeaSetContent) ?? {};
  const candidates = content.candidates ?? [];

  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      {content.evaluated === false && (
        <div style={{ color: '#fbbf24', fontSize: 13, marginBottom: 8 }}>
          Candidates generated — awaiting evaluation.
        </div>
      )}
      {candidates.length === 0 && <div style={MUTED}>No candidates in this set.</div>}
      {content.scoring_rubric_version && (
        <div style={{ ...MUTED, fontSize: 12, marginBottom: 8 }}>
          Scoring Rubric {content.scoring_rubric_version}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, marginTop: 8 }}>
        {candidates.map((c) => {
          const recommended = content.recommended_candidate_id === c.candidate_id;
          return (
            <div
              key={c.candidate_id}
              style={{
                border: `1px solid ${recommended ? '#fbbf24' : '#334155'}`,
                borderRadius: 8,
                padding: 14,
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
                background: recommended ? 'rgba(251, 191, 36, 0.04)' : '#1e293b',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ fontWeight: 700, fontSize: 16, color: '#e2e8f0' }}>{c.title}</div>
                {recommended && <Badge variant="gold">★ recommended</Badge>}
              </div>

              {c.logline && (
                <div style={{ ...LONG_TEXT, fontWeight: 500, fontSize: 13, color: '#cbd5e1' }}>
                  {c.logline}
                </div>
              )}

              {c.premise && (
                <div style={{ ...LONG_TEXT, fontSize: 13, color: '#94a3b8' }}>
                  <b>Premise:</b> {c.premise}
                </div>
              )}

              {c.summary && <div style={{ ...LONG_TEXT, fontSize: 13 }}>{c.summary}</div>}

              {c.themes && c.themes.length > 0 && (
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                  {c.themes.map((t, idx) => (
                    <Badge key={idx}>{t}</Badge>
                  ))}
                </div>
              )}

              {c.safety_ok === false && (
                <Badge variant="danger">⚠️ Safety flag — review before use</Badge>
              )}

              {typeof c.score === 'number' && (
                <div style={{ fontSize: 13, fontWeight: 600, color: '#4ade80', marginTop: 4 }}>
                  Score: {c.score.toFixed(3)}
                </div>
              )}

              <ScoreRows dimensions={c.score_dimensions} />

              <button
                onClick={() => onSelect(c.candidate_id)}
                disabled={disabled}
                style={{
                  marginTop: 'auto',
                  alignSelf: 'flex-start',
                  padding: '6px 14px',
                  borderRadius: 6,
                  border: 'none',
                  background: disabled ? '#334155' : recommended ? '#fbbf24' : '#0284c7',
                  color: disabled ? '#94a3b8' : recommended ? '#0f172a' : '#ffffff',
                  fontWeight: 600,
                  cursor: disabled ? 'not-allowed' : 'pointer',
                }}
              >
                Select this idea
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function SelectedIdeaView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = (artifact.content as SelectedIdeaContent) ?? {};
  return (
    <div style={{ border: '1px solid #0284c7', borderRadius: 8, padding: 14, background: 'rgba(2, 132, 199, 0.05)' }}>
      <ArtifactHeader artifact={artifact} />
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
        <Badge variant="success">✓ Selected Idea</Badge>
        <span style={{ fontWeight: 700, fontSize: 16, color: '#e2e8f0' }}>{c.title ?? 'Selected idea'}</span>
      </div>
      {c.summary && <div style={{ ...LONG_TEXT, fontSize: 13, marginBottom: 6 }}>{c.summary}</div>}
      {c.rationale && <div style={{ ...LONG_TEXT, ...MUTED, fontSize: 13, marginBottom: 6 }}>Rationale: {c.rationale}</div>}
      <div style={{ ...MUTED, fontSize: 12, marginBottom: 6 }}>
        candidate {c.candidate_id ?? '—'} · set {c.source_set_id ?? '—'} · policy {c.selection_policy ?? '—'}
      </div>
      <ScoreRows dimensions={c.score_dimensions} />
    </div>
  );
}
