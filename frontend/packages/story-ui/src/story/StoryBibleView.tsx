import React, { useState } from 'react';
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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 12, background: '#1e293b', padding: 12, borderRadius: 8, border: '1px solid #334155' }}>
      <div style={{ fontWeight: 600, marginBottom: 4, color: '#7dd3fc', fontSize: 13, textTransform: 'uppercase' }}>
        {title}
      </div>
      {children}
    </div>
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

export interface StoryBibleContent {
  title?: string;
  premise?: string;
  theme?: string;
  tone?: string;
  arc_summary?: string;
  stakes?: string;
  story_rules?: string[];
}

export interface WorldRule {
  rule_id?: string;
  kind?: string;
  statement?: string;
}

export interface RecurringLocation {
  location_id?: string;
  name?: string;
  description?: string;
  atmosphere?: string;
  lighting?: string;
}

export interface RecurringObject {
  prop_id?: string;
  name?: string;
  description?: string;
  significance?: string;
}

export interface WorldBibleContent {
  physical_rules?: WorldRule[];
  story_rules?: WorldRule[];
  recurring_locations?: RecurringLocation[];
  recurring_objects?: RecurringObject[];
}

export interface CharacterEntry {
  character_id?: string;
  name?: string;
  role?: string;
  age_band?: string;
  appearance?: string;
  goal?: string;
  voice?: string;
  traits?: string[];
  relationships?: Array<{ from_id?: string; to_id?: string; kind?: string; description?: string }>;
}

export interface CharacterCanonContent {
  characters?: CharacterEntry[];
}

export interface Beat {
  beat_id?: string;
  order?: number;
  description?: string;
  emotional_beat?: string;
  role?: string;
  target_seconds?: number;
  character_ids?: string[];
}

export interface BeatSheetContent {
  beats?: Beat[];
  total_target_seconds?: number;
  target_duration_seconds?: number;
  tolerance_seconds?: number;
}

export function StoryBibleView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = (artifact.content as StoryBibleContent) ?? {};
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 12, color: '#e2e8f0' }}>
        {c.title ?? 'Story bible'}
      </div>
      <Section title="Premise"><div style={{ ...LONG_TEXT, fontSize: 14 }}>{c.premise ?? '—'}</div></Section>
      <Section title="Theme"><div style={{ ...LONG_TEXT, fontSize: 14 }}>{c.theme || '—'}</div></Section>
      <Section title="Tone"><div style={{ ...LONG_TEXT, fontSize: 14 }}>{c.tone || '—'}</div></Section>
      <Section title="Arc"><div style={{ ...LONG_TEXT, fontSize: 14 }}>{c.arc_summary || '—'}</div></Section>
      <Section title="Stakes"><div style={{ ...LONG_TEXT, fontSize: 14 }}>{c.stakes || '—'}</div></Section>
      {c.story_rules && c.story_rules.length > 0 && (
        <Section title="Story rules">
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {c.story_rules.map((r, i) => <li key={i} style={{ ...LONG_TEXT, fontSize: 13, marginBottom: 4 }}>{r}</li>)}
          </ul>
        </Section>
      )}
    </div>
  );
}

export function WorldBibleView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = (artifact.content as WorldBibleContent) ?? {};
  const rules = [...(c.physical_rules ?? []), ...(c.story_rules ?? [])];
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      {rules.length > 0 && (
        <Section title="World rules">
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {rules.map((r) => (
              <li key={`${r.kind ?? 'rule'}-${r.rule_id ?? rules.indexOf(r)}`} style={{ ...LONG_TEXT, fontSize: 13, marginBottom: 4 }}>
                {r.statement ?? '—'}
                {r.kind ? <span style={{ color: '#fbbf24', marginLeft: 6 }}>({r.kind})</span> : null}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {c.recurring_locations && c.recurring_locations.length > 0 && (
        <Section title="Recurring locations">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 10, marginTop: 4 }}>
            {c.recurring_locations.map((l) => (
              <div key={l.location_id ?? l.name} style={{ background: '#0f172a', padding: 10, borderRadius: 6 }}>
                <b style={{ color: '#7dd3fc', fontSize: 14 }}>{l.name}</b>
                {l.description && <div style={{ ...LONG_TEXT, fontSize: 12, margin: '4px 0' }}>{l.description}</div>}
                {l.atmosphere && <div style={{ ...MUTED, fontSize: 12 }}>Atmosphere: {l.atmosphere}</div>}
                {l.lighting && <div style={{ ...MUTED, fontSize: 12 }}>Lighting: {l.lighting}</div>}
              </div>
            ))}
          </div>
        </Section>
      )}
      {c.recurring_objects && c.recurring_objects.length > 0 && (
        <Section title="Recurring objects">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 10, marginTop: 4 }}>
            {c.recurring_objects.map((o) => (
              <div key={o.prop_id ?? o.name} style={{ background: '#0f172a', padding: 10, borderRadius: 6 }}>
                <b style={{ color: '#fbbf24', fontSize: 14 }}>{o.name}</b>
                {o.description && <div style={{ ...LONG_TEXT, fontSize: 12, margin: '4px 0' }}>{o.description}</div>}
                {o.significance && <div style={{ ...MUTED, fontSize: 12 }}>Significance: {o.significance}</div>}
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

export function CharacterCanonView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = (artifact.content as CharacterCanonContent) ?? {};
  const characters = c.characters ?? [];
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      {characters.length === 0 && <div style={MUTED}>No characters.</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
        {characters.map((ch) => {
          let roleColor = '#334155';
          if (ch.role?.toUpperCase() === 'PROTAGONIST') roleColor = '#0284c7';
          else if (ch.role?.toUpperCase() === 'ANTAGONIST') roleColor = '#b91c1c';

          return (
            <div key={ch.character_id ?? ch.name} style={{ border: '1px solid #334155', borderRadius: 8, padding: 12, background: '#1e293b' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <b style={{ fontSize: 16, color: '#e2e8f0' }}>{ch.name}</b>
                {ch.role && <Badge color={roleColor}>{ch.role}</Badge>}
              </div>

              {ch.age_band && <div style={{ ...MUTED, fontSize: 12, marginBottom: 4 }}>Age: {ch.age_band}</div>}
              {ch.appearance && <div style={{ ...LONG_TEXT, fontSize: 13, marginBottom: 6 }}>{ch.appearance}</div>}
              {ch.goal && <div style={{ ...LONG_TEXT, fontSize: 13, color: '#7dd3fc', marginBottom: 4 }}>Goal: {ch.goal}</div>}
              {ch.voice && <div style={{ ...LONG_TEXT, fontSize: 13, color: '#cbd5e1', marginBottom: 4 }}>Voice: {ch.voice}</div>}

              {ch.traits && ch.traits.length > 0 && (
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', margin: '6px 0' }}>
                  {ch.traits.map((t, i) => <Badge key={i} color="#0f172a">{t}</Badge>)}
                </div>
              )}

              {ch.relationships && ch.relationships.length > 0 && (
                <div style={{ marginTop: 8, background: '#0f172a', padding: 8, borderRadius: 6, fontSize: 12 }}>
                  <b style={{ color: '#94a3b8' }}>Relationships:</b>
                  {ch.relationships.map((r, i) => (
                    <div key={i} style={{ ...LONG_TEXT, marginTop: 2, color: '#e2e8f0' }}>
                      {r.description ?? `${r.from_id ?? '—'} → ${r.to_id ?? '—'} (${r.kind ?? '—'})`}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function fmtSeconds(seconds?: number): string {
  if (typeof seconds !== 'number') return '—';
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export function BeatsView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = (artifact.content as BeatSheetContent) ?? {};
  const beats = c.beats ?? [];
  const total = beats.reduce((sum, b) => sum + (b.target_seconds ?? 0), 0);

  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      {beats.length === 0 && <div style={MUTED}>No beats.</div>}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
        {beats.map((b, idx) => (
          <div key={b.beat_id ?? b.order} style={{ borderLeft: '3px solid #7dd3fc', padding: '8px 12px', background: '#1e293b', borderRadius: '0 8px 8px 0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <Badge color="#0284c7">Beat #{b.order ?? idx + 1}</Badge>
                <span style={{ fontWeight: 600, fontSize: 13, color: '#e2e8f0' }}>
                  {b.role ?? 'beat'} · {fmtSeconds(b.target_seconds)}
                </span>
              </div>
            </div>
            <div style={{ ...LONG_TEXT, fontSize: 13, color: '#cbd5e1' }}>{b.description}</div>
            {b.emotional_beat && (
              <div style={{ ...MUTED, fontSize: 12, marginTop: 4 }}>
                Emotional Turn: <span style={{ color: '#fbbf24' }}>{b.emotional_beat}</span>
              </div>
            )}
            {b.character_ids && b.character_ids.length > 0 && (
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                {b.character_ids.map((cid) => (
                  <Badge key={cid} color="#0f172a">{cid}</Badge>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      {beats.length > 0 && (
        <div style={{ ...MUTED, marginTop: 12, fontWeight: 600, fontSize: 13 }}>
          Total: {fmtSeconds(total)}
        </div>
      )}
    </div>
  );
}

/** Story Sub-navigation container component for UI6.2 */
export function StoryTabContainer({ artifacts }: { artifacts: StudioArtifactEnvelope[] }) {
  const [subTab, setSubTab] = useState<'bible' | 'world' | 'characters' | 'beats'>('bible');

  const storyBible = artifacts.find((a) => a.artifact_type === 'StoryBible');
  const worldBible = artifacts.find((a) => a.artifact_type === 'WorldBible');
  const characterCanon = artifacts.find((a) => a.artifact_type === 'CharacterCanon');
  const beatSheet = artifacts.find((a) => a.artifact_type === 'BeatSheet');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Sub-nav tabs */}
      <div style={{ display: 'flex', gap: 8, borderBottom: '1px solid #334155', paddingBottom: 6 }}>
        <button
          onClick={() => setSubTab('bible')}
          style={{
            padding: '4px 12px',
            borderRadius: 6,
            border: 'none',
            background: subTab === 'bible' ? '#0284c7' : '#1e293b',
            color: subTab === 'bible' ? '#ffffff' : '#94a3b8',
            cursor: 'pointer',
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          Story Bible
        </button>
        <button
          onClick={() => setSubTab('world')}
          style={{
            padding: '4px 12px',
            borderRadius: 6,
            border: 'none',
            background: subTab === 'world' ? '#0284c7' : '#1e293b',
            color: subTab === 'world' ? '#ffffff' : '#94a3b8',
            cursor: 'pointer',
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          World
        </button>
        <button
          onClick={() => setSubTab('characters')}
          style={{
            padding: '4px 12px',
            borderRadius: 6,
            border: 'none',
            background: subTab === 'characters' ? '#0284c7' : '#1e293b',
            color: subTab === 'characters' ? '#ffffff' : '#94a3b8',
            cursor: 'pointer',
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          Characters
        </button>
        <button
          onClick={() => setSubTab('beats')}
          style={{
            padding: '4px 12px',
            borderRadius: 6,
            border: 'none',
            background: subTab === 'beats' ? '#0284c7' : '#1e293b',
            color: subTab === 'beats' ? '#ffffff' : '#94a3b8',
            cursor: 'pointer',
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          Beat Sheet
        </button>
      </div>

      {subTab === 'bible' && (
        storyBible ? <StoryBibleView artifact={storyBible} /> : <div style={MUTED}>No Story Bible artifact yet.</div>
      )}
      {subTab === 'world' && (
        worldBible ? <WorldBibleView artifact={worldBible} /> : <div style={MUTED}>No World Bible artifact yet.</div>
      )}
      {subTab === 'characters' && (
        characterCanon ? <CharacterCanonView artifact={characterCanon} /> : <div style={MUTED}>No Character Canon artifact yet.</div>
      )}
      {subTab === 'beats' && (
        beatSheet ? <BeatsView artifact={beatSheet} /> : <div style={MUTED}>No Beat Sheet artifact yet.</div>
      )}
    </div>
  );
}
