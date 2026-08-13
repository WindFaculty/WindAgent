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

function fmtSeconds(seconds?: number): string {
  if (typeof seconds !== 'number') return '—';
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export interface OutlineScene {
  scene_id?: string;
  order?: number;
  intent?: string;
  location_id?: string;
  estimated_seconds?: number;
  dialogue_budget_seconds?: number;
  conflict_change?: string;
  visual_action?: string;
  beat_refs?: string[];
  character_ids?: string[];
}

export interface EpisodeOutlineContent {
  title?: string;
  scenes?: OutlineScene[];
  target_duration_seconds?: number;
  tolerance_seconds?: number;
  audience_band?: string;
  language?: string;
  duration_formula_version?: string;
}

export function OutlineView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = (artifact.content as EpisodeOutlineContent) ?? {};
  const scenes = c.scenes ?? [];
  const total = scenes.reduce((sum, s) => sum + (s.estimated_seconds ?? 0), 0);
  const target = c.target_duration_seconds;
  const tolerance = c.tolerance_seconds ?? 15;
  const delta = typeof target === 'number' ? total - target : null;
  const withinBudget = delta !== null && Math.abs(delta) <= tolerance;

  // Extract unique locations and characters
  const uniqueLocations = Array.from(new Set(scenes.map((s) => s.location_id).filter(Boolean)));
  const uniqueCharacters = Array.from(new Set(scenes.flatMap((s) => s.character_ids ?? []).filter(Boolean)));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <ArtifactHeader artifact={artifact} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontWeight: 700, fontSize: 18, color: '#e2e8f0' }}>{c.title ?? 'Episode outline'}</div>
        {c.audience_band && (
          <Badge color="#0f172a">Audience {c.audience_band}{c.language ? ` · ${c.language}` : ''}</Badge>
        )}
      </div>

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
        <div style={{ background: '#1e293b', border: '1px solid #334155', padding: 12, borderRadius: 8 }}>
          <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>Total Duration</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: withinBudget ? '#4ade80' : '#fca5a5', marginTop: 2 }}>
            {fmtSeconds(total)}
          </div>
          {typeof target === 'number' && (
            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>
              Target {fmtSeconds(target)} ({delta !== null && delta > 0 ? '+' : ''}{delta}s)
            </div>
          )}
        </div>

        <div style={{ background: '#1e293b', border: '1px solid #334155', padding: 12, borderRadius: 8 }}>
          <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>Scenes Count</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#7dd3fc', marginTop: 2 }}>{scenes.length} Scenes</div>
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>Locations: {uniqueLocations.length}</div>
        </div>

        <div style={{ background: '#1e293b', border: '1px solid #334155', padding: 12, borderRadius: 8 }}>
          <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>Cast Required</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0', marginTop: 2 }}>{uniqueCharacters.length} Characters</div>
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>
            {uniqueCharacters.slice(0, 3).join(', ')}{uniqueCharacters.length > 3 ? '…' : ''}
          </div>
        </div>
      </div>

      {/* Scene list cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 6 }}>
        {scenes.map((s) => (
          <div
            key={s.scene_id ?? s.order}
            style={{
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 8,
              padding: 14,
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontWeight: 700, fontSize: 15, color: '#e2e8f0' }}>
                Scene {s.order}: {s.intent ?? '—'}
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: '#7dd3fc' }}>{s.location_id ?? '—'}</span>
                <Badge color="#0f172a">{fmtSeconds(s.estimated_seconds)}</Badge>
              </div>
            </div>

            {s.visual_action && (
              <div style={{ ...LONG_TEXT, fontSize: 13, color: '#cbd5e1', margin: '4px 0' }}>
                <b>Visual Action:</b> {s.visual_action}
              </div>
            )}

            {s.conflict_change && (
              <div style={{ ...LONG_TEXT, fontSize: 13, color: '#fbbf24' }}>
                <b>Conflict Turn:</b> {s.conflict_change}
              </div>
            )}

            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 4, fontSize: 12 }}>
              {s.dialogue_budget_seconds ? (
                <span style={MUTED}>Dialogue budget {fmtSeconds(s.dialogue_budget_seconds)}</span>
              ) : null}
              {s.beat_refs && s.beat_refs.length > 0 && (
                <span style={MUTED}>Beats: {s.beat_refs.join(', ')}</span>
              )}
            </div>

            {s.character_ids && s.character_ids.length > 0 && (
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                {s.character_ids.map((cid) => (
                  <Badge key={cid} color="#0f172a">{cid}</Badge>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {scenes.length > 0 && (
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 8 }}>
          <span style={MUTED}>Scene total: {fmtSeconds(total)}</span>
          {typeof target === 'number' && (
            <span style={{ color: withinBudget ? '#4ade80' : '#fca5a5', fontWeight: 600 }} title={`tolerance ±${tolerance}s`}>
              vs target {fmtSeconds(target)} ({delta !== null && delta > 0 ? '+' : ''}{delta}s)
            </span>
          )}
        </div>
      )}
    </div>
  );
}
