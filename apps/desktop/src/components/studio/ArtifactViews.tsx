/**
 * Studio story artifact views (Plan C4) — read-only presentational renderers
 * for idea candidates, bibles/canon, beat sheet, and timed episode outline.
 *
 * Contract rules honored here:
 * - Server artifact content is the authority; views never synthesize or
 *   locally advance state.
 * - Unknown artifact types/schemas render an explicit unsupported state.
 * - Unknown optional fields are ignored safely; long Vietnamese text wraps.
 */

import React from 'react';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';

const LONG_TEXT: React.CSSProperties = {
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

const MUTED = { color: '#94a3b8' } as const;

// -- content shapes (optional fields; unknown extras ignored) --------------

interface IdeaCandidateContent {
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

interface IdeaSetContent {
  candidates?: IdeaCandidateContent[];
  evaluated?: boolean;
  recommended_candidate_id?: string | null;
  scoring_rubric_version?: string | null;
}

interface SelectedIdeaContent {
  title?: string;
  summary?: string;
  rationale?: string;
  candidate_id?: string;
  source_set_id?: string;
  selection_policy?: string;
  score?: number | null;
  score_dimensions?: Record<string, number>;
}

interface StoryBibleContent {
  title?: string;
  premise?: string;
  theme?: string;
  tone?: string;
  arc_summary?: string;
  stakes?: string;
  story_rules?: string[];
}

interface WorldRule {
  rule_id?: string;
  kind?: string;
  statement?: string;
}
interface RecurringLocation {
  location_id?: string;
  name?: string;
  description?: string;
  atmosphere?: string;
  lighting?: string;
}
interface RecurringObject {
  prop_id?: string;
  name?: string;
  description?: string;
  significance?: string;
}
interface WorldBibleContent {
  physical_rules?: WorldRule[];
  story_rules?: WorldRule[];
  recurring_locations?: RecurringLocation[];
  recurring_objects?: RecurringObject[];
}

interface CharacterEntry {
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
interface CharacterCanonContent {
  characters?: CharacterEntry[];
}

interface Beat {
  beat_id?: string;
  order?: number;
  description?: string;
  emotional_beat?: string;
  role?: string;
  target_seconds?: number;
  character_ids?: string[];
}
interface BeatSheetContent {
  beats?: Beat[];
  total_target_seconds?: number;
  target_duration_seconds?: number;
  tolerance_seconds?: number;
}

interface OutlineScene {
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
interface EpisodeOutlineContent {
  title?: string;
  scenes?: OutlineScene[];
  target_duration_seconds?: number;
  tolerance_seconds?: number;
  audience_band?: string;
  language?: string;
  duration_formula_version?: string;
}

// -- small presentational helpers ------------------------------------------

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontWeight: 600, marginBottom: 2 }}>{title}</div>
      {children}
    </div>
  );
}

function Provenance({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const parts: string[] = [];
  if (artifact.provider_id) parts.push(`provider ${artifact.provider_id}`);
  if (artifact.model_id) parts.push(`model ${artifact.model_id}`);
  if (artifact.model_route_id) parts.push(`route ${artifact.model_route_id}`);
  if (artifact.prompt_id) parts.push(`prompt ${artifact.prompt_id}`);
  if (parts.length === 0) return null;
  return (
    <div style={{ ...MUTED, fontSize: 12, marginTop: 6 }}>
      Provenance: {parts.join(' · ')}
    </div>
  );
}

function ScoreRows({ dimensions }: { dimensions?: Record<string, number> }) {
  if (!dimensions || Object.keys(dimensions).length === 0) return null;
  const entries = Object.entries(dimensions).sort(([a], [b]) => a.localeCompare(b));
  return (
    <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '2px 10px', margin: '6px 0 0', fontSize: 13 }}>
      {entries.map(([name, value]) => (
        <React.Fragment key={name}>
          <dt style={{ color: '#94a3b8' }}>{name}</dt>
          <dd style={{ margin: 0 }}>{typeof value === 'number' ? value.toFixed(3) : String(value)}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

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

// -- idea candidate set -----------------------------------------------------

export function IdeaSetView({
  artifact,
  onSelect,
  disabled,
}: {
  artifact: StudioArtifactEnvelope;
  onSelect: (candidateId: string) => void;
  disabled?: boolean;
}) {
  const content = artifact.content as IdeaSetContent;
  const candidates = content.candidates ?? [];
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      {content.evaluated === false && (
        <div style={MUTED}>Candidates generated — awaiting evaluation.</div>
      )}
      {candidates.length === 0 && <div style={MUTED}>No candidates in this set.</div>}
      {content.scoring_rubric_version && (
        <div style={{ ...MUTED, fontSize: 12 }}>Rubric {content.scoring_rubric_version}</div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12, marginTop: 8 }}>
        {candidates.map((c) => {
          const recommended = content.recommended_candidate_id === c.candidate_id;
          return (
            <div
              key={c.candidate_id}
              style={{
                border: `1px solid ${recommended ? '#fbbf24' : '#334155'}`,
                borderRadius: 8,
                padding: 12,
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}
            >
              <div style={{ fontWeight: 600 }}>
                {c.title}
                {recommended && <span style={{ color: '#fbbf24', fontSize: 12 }}> — recommended</span>}
              </div>
              {c.logline && <div style={LONG_TEXT}>{c.logline}</div>}
              {c.premise && <div style={{ ...LONG_TEXT, ...MUTED, fontSize: 13 }}>{c.premise}</div>}
              {c.summary && <div style={{ ...LONG_TEXT, fontSize: 13 }}>{c.summary}</div>}
              {c.themes && c.themes.length > 0 && (
                <div style={{ ...MUTED, fontSize: 12 }}>Themes: {c.themes.join(', ')}</div>
              )}
              {c.safety_ok === false && <div style={{ color: '#fca5a5', fontSize: 12 }}>Safety flag — review before use.</div>}
              {typeof c.score === 'number' && <div>Score: {c.score.toFixed(3)}</div>}
              <ScoreRows dimensions={c.score_dimensions} />
              <button
                onClick={() => onSelect(c.candidate_id)}
                disabled={disabled}
                style={{ marginTop: 'auto', alignSelf: 'flex-start' }}
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
  const c = artifact.content as SelectedIdeaContent;
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      <div style={{ fontWeight: 600 }}>{c.title ?? 'Selected idea'}</div>
      {c.summary && <div style={LONG_TEXT}>{c.summary}</div>}
      {c.rationale && <div style={{ ...LONG_TEXT, ...MUTED }}>Rationale: {c.rationale}</div>}
      <div style={{ ...MUTED, fontSize: 12 }}>
        candidate {c.candidate_id ?? '—'} · set {c.source_set_id ?? '—'} · policy {c.selection_policy ?? '—'}
      </div>
      <ScoreRows dimensions={c.score_dimensions} />
    </div>
  );
}

// -- bibles and canon -------------------------------------------------------

export function StoryBibleView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = artifact.content as StoryBibleContent;
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      <div style={{ fontWeight: 600 }}>{c.title ?? 'Story bible'}</div>
      <Section title="Premise"><div style={LONG_TEXT}>{c.premise ?? '—'}</div></Section>
      <Section title="Theme"><div style={LONG_TEXT}>{c.theme || '—'}</div></Section>
      <Section title="Tone"><div style={LONG_TEXT}>{c.tone || '—'}</div></Section>
      <Section title="Arc"><div style={LONG_TEXT}>{c.arc_summary || '—'}</div></Section>
      <Section title="Stakes"><div style={LONG_TEXT}>{c.stakes || '—'}</div></Section>
      {c.story_rules && c.story_rules.length > 0 && (
        <Section title="Story rules">
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {c.story_rules.map((r, i) => <li key={i} style={LONG_TEXT}>{r}</li>)}
          </ul>
        </Section>
      )}
    </div>
  );
}

export function WorldBibleView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = artifact.content as WorldBibleContent;
  const rules = [...(c.physical_rules ?? []), ...(c.story_rules ?? [])];
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      {rules.length > 0 && (
        <Section title="World rules">
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {rules.map((r) => (
              <li key={`${r.kind ?? 'rule'}-${r.rule_id ?? rules.indexOf(r)}`} style={LONG_TEXT}>
                {r.statement ?? '—'}
                {r.kind ? <span style={MUTED}> ({r.kind})</span> : null}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {c.recurring_locations && c.recurring_locations.length > 0 && (
        <Section title="Recurring locations">
          {c.recurring_locations.map((l) => (
            <div key={l.location_id ?? l.name} style={{ marginBottom: 6 }}>
              <b>{l.name}</b>
              {l.description && <div style={LONG_TEXT}>{l.description}</div>}
              {l.atmosphere && <div style={MUTED}>Atmosphere: {l.atmosphere}</div>}
              {l.lighting && <div style={MUTED}>Lighting: {l.lighting}</div>}
            </div>
          ))}
        </Section>
      )}
      {c.recurring_objects && c.recurring_objects.length > 0 && (
        <Section title="Recurring objects">
          {c.recurring_objects.map((o) => (
            <div key={o.prop_id ?? o.name} style={{ marginBottom: 6 }}>
              <b>{o.name}</b>
              {o.description && <div style={LONG_TEXT}>{o.description}</div>}
              {o.significance && <div style={MUTED}>{o.significance}</div>}
            </div>
          ))}
        </Section>
      )}
    </div>
  );
}

export function CharacterCanonView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = artifact.content as CharacterCanonContent;
  const characters = c.characters ?? [];
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      {characters.length === 0 && <div style={MUTED}>No characters.</div>}
      {characters.map((ch) => (
        <div key={ch.character_id ?? ch.name} style={{ border: '1px solid #334155', borderRadius: 8, padding: 10, marginBottom: 8 }}>
          <div style={{ fontWeight: 600 }}>
            {ch.name}
            {ch.role ? <span style={MUTED}> · {ch.role}</span> : null}
            {ch.age_band ? <span style={MUTED}> · {ch.age_band}</span> : null}
          </div>
          {ch.appearance && <div style={LONG_TEXT}>{ch.appearance}</div>}
          {ch.goal && <div style={LONG_TEXT}>Goal: {ch.goal}</div>}
          {ch.voice && <div style={LONG_TEXT}>Voice: {ch.voice}</div>}
          {ch.traits && ch.traits.length > 0 && (
            <div style={MUTED}>Traits: {ch.traits.join(', ')}</div>
          )}
          {ch.relationships && ch.relationships.length > 0 && (
            <div style={{ fontSize: 13 }}>
              {ch.relationships.map((r, i) => (
                <div key={i} style={LONG_TEXT}>
                  {r.description ?? `${r.from_id ?? '—'} → ${r.to_id ?? '—'} (${r.kind ?? '—'})`}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// -- beat sheet and outline -------------------------------------------------

function fmtSeconds(seconds?: number): string {
  if (typeof seconds !== 'number') return '—';
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export function BeatsView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = artifact.content as BeatSheetContent;
  const beats = c.beats ?? [];
  const total = beats.reduce((sum, b) => sum + (b.target_seconds ?? 0), 0);
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      {beats.length === 0 && <div style={MUTED}>No beats.</div>}
      <ol style={{ margin: '8px 0 0', paddingLeft: 20 }}>
        {beats.map((b) => (
          <li key={b.beat_id ?? b.order} style={{ marginBottom: 6 }}>
            <div style={LONG_TEXT}>{b.description}</div>
            <div style={{ ...MUTED, fontSize: 13 }}>
              {b.role ?? 'beat'} · {fmtSeconds(b.target_seconds)}
              {b.emotional_beat ? ` · ${b.emotional_beat}` : ''}
              {b.character_ids && b.character_ids.length > 0 ? ` · ${b.character_ids.join(', ')}` : ''}
            </div>
          </li>
        ))}
      </ol>
      {beats.length > 0 && <div style={MUTED}>Total: {fmtSeconds(total)}</div>}
    </div>
  );
}

export function OutlineView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = artifact.content as EpisodeOutlineContent;
  const scenes = c.scenes ?? [];
  const total = scenes.reduce((sum, s) => sum + (s.estimated_seconds ?? 0), 0);
  const target = c.target_duration_seconds;
  const tolerance = c.tolerance_seconds ?? 15;
  const delta = typeof target === 'number' ? total - target : null;
  const withinBudget = delta !== null && Math.abs(delta) <= tolerance;
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      <div style={{ fontWeight: 600 }}>{c.title ?? 'Episode outline'}</div>
      {c.audience_band && <div style={MUTED}>Audience {c.audience_band}{c.language ? ` · ${c.language}` : ''}</div>}
      <ol style={{ margin: '8px 0 0', paddingLeft: 20 }}>
        {scenes.map((s) => (
          <li key={s.scene_id ?? s.order} style={{ marginBottom: 8 }}>
            <div style={{ fontWeight: 600, fontSize: 13 }}>
              Scene {s.order}: {s.intent ?? '—'}
              <span style={MUTED}> · {s.location_id ?? '—'} · {fmtSeconds(s.estimated_seconds)}</span>
            </div>
            {s.visual_action && <div style={LONG_TEXT}>{s.visual_action}</div>}
            {s.conflict_change && <div style={{ ...LONG_TEXT, ...MUTED }}>Conflict: {s.conflict_change}</div>}
            {s.dialogue_budget_seconds ? <div style={MUTED}>Dialogue budget {fmtSeconds(s.dialogue_budget_seconds)}</div> : null}
            {s.beat_refs && s.beat_refs.length > 0 && <div style={MUTED}>Beats: {s.beat_refs.join(', ')}</div>}
          </li>
        ))}
      </ol>
      {scenes.length > 0 && (
        <div>
          <span style={MUTED}>Scene total: {fmtSeconds(total)}</span>
          {typeof target === 'number' && (
            <span style={{ marginLeft: 10, color: withinBudget ? '#4ade80' : '#fca5a5' }} title={`tolerance ±${tolerance}s`}>
              vs target {fmtSeconds(target)} ({delta !== null && delta > 0 ? '+' : ''}{delta}s)
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// -- generic fallback for artifacts without a dedicated C4 view -------------

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

// -- dispatcher -------------------------------------------------------------

export function ArtifactContentView({
  artifact,
  onSelectIdea,
  selectDisabled,
}: {
  artifact: StudioArtifactEnvelope;
  onSelectIdea?: (candidateId: string) => void;
  selectDisabled?: boolean;
}) {
  if (!artifact.schema_version.startsWith('studio.artifact/v1alpha1')) {
    return <UnsupportedArtifactView artifact={artifact} />;
  }
  // Envelopes without content render empty-content views, never crash.
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
    default:
      return <GenericArtifactView artifact={safe} />;
  }
}
