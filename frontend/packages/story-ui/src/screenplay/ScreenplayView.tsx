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

export interface ScreenplayDialogue {
  dialogue_id?: string;
  scene_id?: string;
  character_id?: string;
  order?: number;
  text?: string;
  delivery?: string;
  estimated_seconds?: number;
}

export interface ScreenplayScene {
  scene_id?: string;
  order?: number;
  outline_scene_id?: string;
  location_id?: string;
  estimated_seconds?: number;
  action_description?: string;
  narration?: string;
  transition?: string;
  character_ids?: string[];
  source_beat_ids?: string[];
  dialogue?: ScreenplayDialogue[];
}

export interface ScreenplayDraftContent {
  title?: string;
  logline?: string;
  scenes?: ScreenplayScene[];
  target_duration_seconds?: number;
  tolerance_seconds?: number;
  audience_band?: string;
  language?: string;
}

export function ScreenplayView({ artifact, isLocked }: { artifact: StudioArtifactEnvelope; isLocked?: boolean }) {
  const c = (artifact.content as ScreenplayDraftContent) ?? {};
  const scenes = c.scenes ?? [];
  const total = scenes.reduce((sum, s) => sum + (s.estimated_seconds ?? 0), 0);
  const [activeSceneId, setActiveSceneId] = useState<string | null>(scenes[0]?.scene_id ?? null);

  const activeScene = scenes.find((s) => (s.scene_id ?? `${s.order}`) === activeSceneId) ?? scenes[0];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <ArtifactHeader artifact={artifact} />

      {isLocked && (
        <div style={{ background: '#14532d', color: '#4ade80', padding: '6px 12px', borderRadius: 6, fontSize: 13, fontWeight: 600 }}>
          🔒 READ ONLY — Screenplay is locked for production.
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontWeight: 700, fontSize: 20, color: '#e2e8f0' }}>{c.title ?? 'Screenplay draft'}</div>
        {c.audience_band && (
          <Badge color="#0f172a">Audience {c.audience_band}{c.language ? ` · ${c.language}` : ''}</Badge>
        )}
      </div>
      {c.logline && <div style={{ ...LONG_TEXT, ...MUTED, fontSize: 13 }}>{c.logline}</div>}

      {/* 3-Pane Screenplay Reader Workspace */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '220px 1fr 240px',
          gap: 16,
          border: '1px solid #334155',
          borderRadius: 8,
          background: '#0f172a',
          minHeight: 450,
          overflow: 'hidden',
        }}
      >
        {/* Left Rail: Scene List Jump */}
        <nav
          aria-label="Scene navigation"
          style={{
            borderRight: '1px solid #334155',
            padding: 12,
            background: '#1e293b',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            overflowY: 'auto',
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', marginBottom: 4 }}>
            Scenes ({scenes.length})
          </div>
          {scenes.map((s) => {
            const id = s.scene_id ?? `${s.order}`;
            const isActive = activeSceneId === id || (!activeSceneId && s.order === 1);
            return (
              <button
                key={id}
                onClick={() => setActiveSceneId(id)}
                style={{
                  textAlign: 'left',
                  padding: '8px 10px',
                  borderRadius: 6,
                  border: 'none',
                  background: isActive ? '#0284c7' : 'transparent',
                  color: isActive ? '#ffffff' : '#cbd5e1',
                  cursor: 'pointer',
                  fontSize: 12,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 2,
                }}
              >
                <div style={{ fontWeight: 600 }}>Scene {s.order}</div>
                <div style={{ opacity: 0.8, fontSize: 11 }}>{s.location_id ?? '—'} · {fmtSeconds(s.estimated_seconds)}</div>
              </button>
            );
          })}
        </nav>

        {/* Center Pane: Industry Formatted Screenplay Document */}
        <div
          style={{
            padding: 24,
            background: '#090d16',
            overflowY: 'auto',
            fontFamily: "'Courier New', Courier, monospace",
            lineHeight: 1.6,
            color: '#f1f5f9',
          }}
        >
          {scenes.map((s) => {
            const id = s.scene_id ?? `${s.order}`;
            const isHighlighted = activeSceneId === id;
            return (
              <div
                key={id}
                id={`scene-${id}`}
                style={{
                  marginBottom: 28,
                  padding: 12,
                  borderRadius: 6,
                  background: isHighlighted ? 'rgba(2, 132, 199, 0.08)' : 'transparent',
                  borderLeft: isHighlighted ? '3px solid #0284c7' : '3px solid transparent',
                }}
              >
                {/* Scene Header / Slugline */}
                <div style={{ fontWeight: 700, fontSize: 14, textTransform: 'uppercase', color: '#7dd3fc', marginBottom: 8 }}>
                  Scene {s.order}: {s.location_id ?? '—'} · {fmtSeconds(s.estimated_seconds)}
                </div>

                <div style={{ fontSize: 11, fontFamily: 'inherit', color: '#94a3b8', marginBottom: 8 }}>
                  outline {s.outline_scene_id ?? '—'}
                  {s.source_beat_ids && s.source_beat_ids.length > 0 ? ` · beats ${s.source_beat_ids.join(', ')}` : ''}
                  {s.character_ids && s.character_ids.length > 0 ? ` · chars ${s.character_ids.join(', ')}` : ''}
                </div>

                {/* Action Description */}
                {s.action_description && (
                  <div style={{ ...LONG_TEXT, fontSize: 13, marginBottom: 12 }}>
                    {s.action_description}
                  </div>
                )}

                {/* Narration */}
                {s.narration && (
                  <div style={{ ...LONG_TEXT, fontSize: 13, color: '#94a3b8', fontStyle: 'italic', marginBottom: 12 }}>
                    [Narration]: {s.narration}
                  </div>
                )}

                {/* Dialogue Blocks */}
                {(s.dialogue ?? []).map((d) => (
                  <div key={d.dialogue_id ?? d.order} style={{ margin: '12px auto', maxWidth: 380, textAlign: 'left' }}>
                    {/* Character Name centered */}
                    <div style={{ fontWeight: 700, textTransform: 'uppercase', textAlign: 'center', fontSize: 13, color: '#fbbf24' }}>
                      {d.character_id ?? '—'}
                    </div>

                    {/* Delivery / Parenthetical */}
                    {d.delivery && (
                      <div style={{ textAlign: 'center', fontSize: 12, color: '#94a3b8', fontStyle: 'italic' }}>
                        ({d.delivery})
                      </div>
                    )}

                    {/* Dialogue Text */}
                    <div style={{ ...LONG_TEXT, fontSize: 13, marginTop: 2, paddingLeft: 12 }}>
                      {d.text}
                    </div>
                  </div>
                ))}

                {/* Transition */}
                {s.transition && (
                  <div style={{ textAlign: 'right', textTransform: 'uppercase', fontSize: 12, fontWeight: 700, color: '#94a3b8', marginTop: 12 }}>
                    {s.transition}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Right Inspector Panel */}
        <aside
          role="region"
          aria-label="Screenplay inspector"
          style={{
            borderLeft: '1px solid #334155',
            padding: 12,
            background: '#1e293b',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            overflowY: 'auto',
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase' }}>
            Inspector &amp; Lineage
          </div>

          <div style={{ background: '#0f172a', padding: 10, borderRadius: 6, fontSize: 12 }}>
            <div style={{ color: '#94a3b8' }}>Total Duration</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: '#4ade80', marginTop: 2 }}>{fmtSeconds(total)}</div>
            {c.target_duration_seconds && (
              <div style={{ color: '#94a3b8', marginTop: 2 }}>Target: {fmtSeconds(c.target_duration_seconds)}</div>
            )}
          </div>

          {activeScene && (
            <div style={{ background: '#0f172a', padding: 10, borderRadius: 6, fontSize: 12 }}>
              <div style={{ color: '#94a3b8', fontWeight: 600, marginBottom: 4 }}>
                Active Scene #{activeScene.order}
              </div>
              <div style={{ color: '#e2e8f0', marginBottom: 2 }}>
                <b>Location:</b> {activeScene.location_id ?? '—'}
              </div>
              <div style={{ color: '#e2e8f0', marginBottom: 2 }}>
                <b>Duration:</b> {fmtSeconds(activeScene.estimated_seconds)}
              </div>
              {activeScene.outline_scene_id && (
                <div style={{ color: '#94a3b8', marginTop: 4 }}>
                  Linked Outline: {activeScene.outline_scene_id}
                </div>
              )}
            </div>
          )}

          <div style={{ background: '#0f172a', padding: 10, borderRadius: 6, fontSize: 12 }}>
            <div style={{ color: '#94a3b8', fontWeight: 600, marginBottom: 4 }}>Artifact Lineage</div>
            <div style={{ color: '#cbd5e1' }}>Revision: {artifact.revision_id ?? '—'}</div>
            <div style={{ color: '#cbd5e1', wordBreak: 'break-all' }}>Hash: {artifact.content_hash?.slice(0, 16)}…</div>
          </div>
        </aside>
      </div>

      {scenes.length > 0 && <div style={MUTED}>Scene total: {fmtSeconds(total)}</div>}
    </div>
  );
}

export interface SceneDiff {
  change_type: 'ADDED' | 'DELETED' | 'MODIFIED';
  title: string;
  changes: Array<{ field_name: string; old_value: string; new_value: string }>;
}

export function diffScreenplays(before: ScreenplayDraftContent, after: ScreenplayDraftContent): SceneDiff[] {
  const beforeScenes = before.scenes ?? [];
  const afterScenes = after.scenes ?? [];
  const byId = (scenes: ScreenplayScene[]) => new Map(scenes.map((s) => [s.scene_id ?? `${s.order}`, s]));
  const bMap = byId(beforeScenes);
  const aMap = byId(afterScenes);
  const diffs: SceneDiff[] = [];
  for (const [id, a] of aMap) {
    const b = bMap.get(id);
    if (!b) {
      diffs.push({ change_type: 'ADDED', title: `Scene ${a.order}: ${a.location_id ?? id}`, changes: [] });
      continue;
    }
    const changes: SceneDiff['changes'] = [];
    const pair = (field: string, oldV: unknown, newV: unknown) => {
      const o = String(oldV ?? '');
      const n = String(newV ?? '');
      if (o !== n) changes.push({ field_name: field, old_value: o, new_value: n });
    };
    pair('action_description', b.action_description, a.action_description);
    pair('narration', b.narration, a.narration);
    const bD = new Map((b.dialogue ?? []).map((d) => [d.dialogue_id ?? `${d.order}`, d]));
    for (const d of a.dialogue ?? []) {
      const key = d.dialogue_id ?? `${d.order}`;
      if (!bD.has(key)) {
        changes.push({ field_name: `dialogue[${key}]`, old_value: '', new_value: d.text ?? '' });
      } else {
        pair(`dialogue[${key}].text`, bD.get(key)?.text, d.text);
        pair(`dialogue[${key}].delivery`, bD.get(key)?.delivery, d.delivery);
      }
    }
    for (const [key, d] of bD) {
      if (!(a.dialogue ?? []).some((x) => (x.dialogue_id ?? `${x.order}`) === key)) {
        changes.push({ field_name: `dialogue[${key}]`, old_value: d.text ?? '', new_value: '' });
      }
    }
    if (changes.length > 0) {
      diffs.push({ change_type: 'MODIFIED', title: `Scene ${a.order}: ${a.location_id ?? id}`, changes });
    }
  }
  for (const [id, b] of bMap) {
    if (!aMap.has(id)) {
      diffs.push({ change_type: 'DELETED', title: `Scene ${b.order}: ${b.location_id ?? id}`, changes: [] });
    }
  }
  return diffs;
}

export function ScreenplayDiffView({ before, after }: { before: ScreenplayDraftContent; after: ScreenplayDraftContent }) {
  const diffs = diffScreenplays(before, after);
  const color = (t: SceneDiff['change_type']) => (t === 'ADDED' ? '#4ade80' : t === 'DELETED' ? '#fca5a5' : '#fbbf24');
  return (
    <div>
      <div style={{ ...MUTED, fontSize: 12, marginBottom: 6 }}>
        Revision diff — before/after (immutable server drafts)
      </div>
      {diffs.length === 0 && <div style={MUTED}>No structural differences between the two drafts.</div>}
      {diffs.map((d, i) => (
        <div key={i} style={{ borderLeft: `3px solid ${color(d.change_type)}`, padding: '4px 10px', marginBottom: 6 }}>
          <span style={{ fontWeight: 600, fontSize: 13 }}>{d.change_type}</span>{' '}
          <span style={MUTED}>{d.title}</span>
          {d.changes.map((c, j) => (
            <div key={j} style={{ fontSize: 12, marginTop: 2 }}>
              <code>{c.field_name}</code>: <span style={{ color: '#fca5a5' }}>{c.old_value || '∅'}</span> →{' '}
              <span style={{ color: '#4ade80' }}>{c.new_value || '∅'}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
