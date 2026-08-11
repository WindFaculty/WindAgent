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

interface ScreenplayDialogue {
  dialogue_id?: string;
  scene_id?: string;
  character_id?: string;
  order?: number;
  text?: string;
  delivery?: string;
  estimated_seconds?: number;
}
interface ScreenplayScene {
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

interface ReviewFinding {
  code?: string;
  dimension?: string | null;
  severity?: string;
  location?: string;
  evidence?: string;
  remediation?: string;
  source?: string;
}
interface ReviewReportContent {
  report_id?: string;
  draft_id?: string;
  verdict?: string;
  quality_summary?: string;
  review_iteration?: number;
  maximum_iterations?: number;
  dimensions?: Array<{ dimension?: string; score?: number; blocking?: boolean; note?: string }>;
  findings?: ReviewFinding[];
}

interface RevisionProposalContent {
  proposal_id?: string;
  draft_id?: string;
  review_report_id?: string;
  revision_reason?: string;
  accepted_finding_codes?: string[];
  iteration_number?: number;
  maximum_iterations?: number;
}

interface LockReceiptContent {
  receipt_id?: string;
  draft_id?: string;
  state?: string;
  issued_at?: string;
  policy_id?: string;
  approval_mode?: string;
}
interface LockPackageContent {
  package_id?: string;
  receipt_id?: string;
  assembled_at?: string;
  manifest?: Array<{ artifact_type?: string; artifact_id?: string; content_hash?: string; revision_id?: string | null }>;
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

// -- screenplay, review, revision, lock -------------------------------------

const SEVERITY_COLOR: Record<string, string> = {
  INFO: '#94a3b8',
  WARNING: '#fbbf24',
  BLOCKING: '#fca5a5',
};

export function ScreenplayView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = artifact.content as ScreenplayDraftContent;
  const scenes = c.scenes ?? [];
  const total = scenes.reduce((sum, s) => sum + (s.estimated_seconds ?? 0), 0);
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      <div style={{ fontWeight: 600 }}>{c.title ?? 'Screenplay draft'}</div>
      {c.logline && <div style={{ ...LONG_TEXT, ...MUTED }}>{c.logline}</div>}
      {c.audience_band && <div style={MUTED}>Audience {c.audience_band}{c.language ? ` · ${c.language}` : ''}</div>}
      <ol style={{ margin: '8px 0 0', paddingLeft: 20 }}>
        {scenes.map((s) => (
          <li key={s.scene_id ?? s.order} style={{ marginBottom: 12 }}>
            <div style={{ fontWeight: 600, fontSize: 13 }}>
              Scene {s.order}: {s.location_id ?? '—'} · {fmtSeconds(s.estimated_seconds)}
            </div>
            <div style={{ ...MUTED, fontSize: 12 }}>
              outline {s.outline_scene_id ?? '—'}
              {s.source_beat_ids && s.source_beat_ids.length > 0 ? ` · beats ${s.source_beat_ids.join(', ')}` : ''}
              {s.character_ids && s.character_ids.length > 0 ? ` · chars ${s.character_ids.join(', ')}` : ''}
            </div>
            {s.action_description && <div style={LONG_TEXT}>{s.action_description}</div>}
            {s.narration && <div style={{ ...LONG_TEXT, ...MUTED }}>{s.narration}</div>}
            {(s.dialogue ?? []).map((d) => (
              <div key={d.dialogue_id ?? d.order} style={{ marginTop: 6, paddingLeft: 12, borderLeft: '2px solid #334155' }}>
                <div style={{ fontSize: 12 }}>
                  <b>{d.character_id ?? '—'}</b>
                  {d.delivery ? <span style={MUTED}> ({d.delivery})</span> : null}
                  <span style={MUTED}> · {fmtSeconds(d.estimated_seconds)}</span>
                </div>
                <div style={LONG_TEXT}>{d.text}</div>
              </div>
            ))}
            {s.transition && <div style={{ ...MUTED, fontSize: 12, marginTop: 4 }}>{s.transition}</div>}
          </li>
        ))}
      </ol>
      {scenes.length > 0 && <div style={MUTED}>Scene total: {fmtSeconds(total)}</div>}
    </div>
  );
}

export function ReviewReportView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = artifact.content as ReviewReportContent;
  const findings = c.findings ?? [];
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      <Provenance artifact={artifact} />
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <b>{c.verdict ?? 'REVIEW_REQUIRED'}</b>
        {typeof c.review_iteration === 'number' && typeof c.maximum_iterations === 'number' && (
          <span style={MUTED}>Iteration {c.review_iteration}/{c.maximum_iterations}</span>
        )}
      </div>
      {c.quality_summary && <div style={LONG_TEXT}>{c.quality_summary}</div>}
      {c.dimensions && c.dimensions.length > 0 && (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', margin: '8px 0' }}>
          {c.dimensions.map((d) => (
            <span key={d.dimension} style={{ fontSize: 13, color: d.blocking ? '#fca5a5' : '#94a3b8' }}>
              {d.dimension}: {typeof d.score === 'number' ? d.score.toFixed(2) : '—'}
              {d.blocking ? ' (blocking)' : ''}
            </span>
          ))}
        </div>
      )}
      {findings.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: '8px 0 0' }}>
          {findings.map((f, i) => (
            <li key={f.code ?? i} style={{ border: '1px solid #334155', borderRadius: 6, padding: 8, marginBottom: 6 }}>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', fontSize: 13 }}>
                <b>{f.code}</b>
                <span style={{ color: SEVERITY_COLOR[f.severity ?? 'INFO'] ?? '#94a3b8' }}>{f.severity ?? 'INFO'}</span>
                {f.dimension && <span style={MUTED}>{f.dimension}</span>}
                {f.location && <span style={MUTED}>at {f.location}</span>}
                {f.source && f.source !== 'deterministic' && <span style={MUTED}>source {f.source}</span>}
              </div>
              {f.evidence && <div style={{ ...LONG_TEXT, fontSize: 13 }}>{f.evidence}</div>}
              {f.remediation && <div style={{ ...LONG_TEXT, ...MUTED, fontSize: 13 }}>Fix: {f.remediation}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function RevisionProposalView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = artifact.content as RevisionProposalContent;
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      <div style={{ fontWeight: 600 }}>Revision proposal</div>
      {c.revision_reason && <div style={LONG_TEXT}>{c.revision_reason}</div>}
      {c.accepted_finding_codes && c.accepted_finding_codes.length > 0 && (
        <div style={MUTED}>Addresses: {c.accepted_finding_codes.join(', ')}</div>
      )}
      {typeof c.iteration_number === 'number' && typeof c.maximum_iterations === 'number' && (
        <div style={MUTED}>Iteration {c.iteration_number}/{c.maximum_iterations}</div>
      )}
    </div>
  );
}

export function LockReceiptView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = artifact.content as LockReceiptContent;
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      <div style={{ color: '#4ade80', fontWeight: 600 }}>{c.state ?? 'READY_FOR_PRODUCTION'}</div>
      <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '2px 12px', margin: '6px 0 0', fontSize: 13 }}>
        <dt style={{ color: '#94a3b8' }}>Receipt</dt><dd style={{ margin: 0 }}>{c.receipt_id}</dd>
        <dt style={{ color: '#94a3b8' }}>Draft</dt><dd style={{ margin: 0 }}>{c.draft_id}</dd>
        {c.issued_at && <><dt style={{ color: '#94a3b8' }}>Issued</dt><dd style={{ margin: 0 }}>{c.issued_at}</dd></>}
        {c.policy_id && <><dt style={{ color: '#94a3b8' }}>Policy</dt><dd style={{ margin: 0 }}>{c.policy_id}</dd></>}
        {c.approval_mode && <><dt style={{ color: '#94a3b8' }}>Approval mode</dt><dd style={{ margin: 0 }}>{c.approval_mode}</dd></>}
      </dl>
    </div>
  );
}

export function LockPackageView({ artifact }: { artifact: StudioArtifactEnvelope }) {
  const c = artifact.content as LockPackageContent;
  const manifest = c.manifest ?? [];
  return (
    <div>
      <ArtifactHeader artifact={artifact} />
      <div style={{ fontWeight: 600 }}>Locked package — lineage &amp; checksums</div>
      {c.package_id && <div style={MUTED}>package {c.package_id}{c.assembled_at ? ` · assembled ${c.assembled_at}` : ''}</div>}
      <ul style={{ listStyle: 'none', padding: 0, margin: '6px 0 0', fontSize: 13 }}>
        {manifest.map((m) => (
          <li key={m.artifact_id ?? m.artifact_type} style={{ marginBottom: 4 }}>
            {m.artifact_type} <span style={MUTED}>({m.artifact_id})</span> hash {m.content_hash?.slice(0, 12)}…
            {m.revision_id ? <span style={MUTED}> · rev {m.revision_id}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

interface SceneDiff {
  change_type: 'ADDED' | 'DELETED' | 'MODIFIED';
  title: string;
  changes: Array<{ field_name: string; old_value: string; new_value: string }>;
}

/** Minimal before/after diff between two structured drafts (scene + dialogue level). */
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
    case 'ScreenplayDraft':
      return <ScreenplayView artifact={safe} />;
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
