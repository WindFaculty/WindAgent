import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StudioPage } from '../pages/StudioPage';
import {
  ArtifactContentView,
  IdeaSetView,
  StoryBibleView,
  WorldBibleView,
  CharacterCanonView,
  BeatsView,
  OutlineView,
  UnsupportedArtifactView,
} from '../components/studio/ArtifactViews';
import { RunProgress } from '../components/studio/RunProgress';
import { ApprovalBar } from '../components/studio/ApprovalBar';
import { HttpStudioApiClient } from '@windagent/studio-client';
import { StudioStore } from '@windagent/studio-state';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';

type FetchFn = (input: string | URL, init?: RequestInit) => Promise<Response>;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const HASH = 'a'.repeat(64);
const REV_HASH = 'b'.repeat(64);

function envelope(overrides: Partial<StudioArtifactEnvelope> & { artifact_type: string }): StudioArtifactEnvelope {
  return {
    artifact_id: 'art_1',
    artifact_type: overrides.artifact_type,
    schema_version: 'studio.artifact/v1alpha1',
    series_id: 'srs_1',
    episode_id: 'ep_1',
    revision_id: 'rev_1',
    content_hash: HASH,
    status: 'DRAFT',
    created_at: '2026-01-01T00:00:00Z',
    content: {},
    ...overrides,
  } as StudioArtifactEnvelope;
}

function episode(overrides: Record<string, unknown> = {}) {
  return {
    id: 'ep_1', series_id: 'srs_1', title: 'Ep ep_1', episode_number: 1,
    state: 'IDEA_REVIEW', version: 3, optimistic_version: 3,
    current_revision_id: 'rev_1', current_revision: { revision_id: 'rev_1', content_hash: REV_HASH, status: 'DRAFT' },
    active_run_id: null, awaiting_checkpoint: null,
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

const CAPABILITIES = {
  capabilities: [
    { name: 'durable_db', status: 'AVAILABLE', reason: 'db' },
    { name: 'studio_orchestration', status: 'AVAILABLE', reason: 'seam' },
    { name: 'story_engine', status: 'AVAILABLE', reason: 'B5' },
    { name: 'worker', status: 'AVAILABLE', reason: 'A5' },
    { name: 'model_route', status: 'AVAILABLE', reason: 'route' },
  ],
  fail_closed_flags: [],
  certification_mode: false,
};

const IDEA_SET = envelope({
  artifact_type: 'IdeaCandidateSet',
  content: {
    evaluated: true,
    recommended_candidate_id: 'c_rabbit_kite',
    scoring_rubric_version: 'rubric/v1',
    candidates: [
      {
        candidate_id: 'c_rabbit_kite', title: 'Chú thỏ và cánh diều giấy',
        logline: 'Một chú thỏ ham chơi học cách kiên nhẫn để thả cánh diều bay cao cùng bạn bè.',
        summary: 'Thỏ con muốn thả diều nhưng gió cứ chê cậu vội vàng; chỉ khi kiên nhẫn cậu mới đưa diều bay cao.',
        score: 0.718, safety_ok: true,
        score_dimensions: { AGE_FIT: 0.95, DURATION_FIT: 1.0, ORIGINALITY: 0.6 },
        themes: ['kiên nhẫn', 'tình bạn'],
      },
      {
        candidate_id: 'c_kite_over_river', title: 'Cánh diều bay qua sông',
        summary: 'Cánh diều của Thỏ mắc vào cây bên kia sông; Thỏ cùng Gió và chim Sẻ tìm cách gỡ diều.',
        score: 0.705,
        score_dimensions: { AGE_FIT: 0.9, DURATION_FIT: 1.0, ORIGINALITY: 0.6 },
      },
      {
        candidate_id: 'c_kite_school', title: 'Thỏ con học thả diều',
        summary: 'Ông Gió dạy Thỏ con từng bước thả diều: chọn nơi thoáng, đợi gió, chạy đà và giữ dây vừa phải.',
        score: 0.709,
        score_dimensions: { AGE_FIT: 0.92, DURATION_FIT: 1.0, ORIGINALITY: 0.6 },
      },
    ],
  },
});

const STORY_BIBLE = envelope({
  artifact_type: 'StoryBible',
  content: {
    title: 'Con thỏ và cánh diều', bible_id: 'bible_1',
    premise: 'Một chú thỏ con ham chơi ở bờ sông nhặt được cánh diều giấy và học cách kiên nhẫn để thả nó bay cao giữa trời chiều.',
    theme: 'kiên nhẫn và tình bạn', tone: 'ấm áp, nhẹ nhàng',
    arc_summary: 'Từ tò mò đến kiên trì, cuối cùng thỏ đạt được mục tiêu và chia sẻ niềm vui với bạn bè.',
    stakes: 'Cánh diều có thể bay mất nếu thỏ vội vàng.',
    story_rules: ['Gió chỉ giúp ai kiên nhẫn.', 'Cánh diều không bao giờ bị hỏng vĩnh viễn trong câu chuyện.'],
  },
});

const WORLD_BIBLE = envelope({
  artifact_type: 'WorldBible',
  content: {
    physical_rules: [{ rule_id: 'rule_wind', kind: 'physics', statement: 'Gió thổi mạnh hơn khi trời quang và chiều muộn.' }],
    recurring_locations: [{ location_id: 'loc_river', name: 'Bờ sông', description: 'Bờ cỏ mềm ven sông, nơi thỏ nhặt được diều.', atmosphere: 'yên bình' }],
    recurring_objects: [{ prop_id: 'prop_kite', name: 'Cánh diều giấy', description: 'Diều hình con chim, giấy màu xanh và vàng.', significance: 'Vật kết nối thỏ với bạn mới.' }],
  },
});

const CHARACTER_CANON = envelope({
  artifact_type: 'CharacterCanon',
  content: {
    canon_id: 'canon_1',
    characters: [
      {
        character_id: 'ch_rabbit', name: 'Thỏ con', role: 'protagonist', age_band: '5-8',
        appearance: 'Thỏ trắng, đeo chiếc khăn nhỏ màu cam',
        goal: 'Học cách thả diều thật cao',
        voice: 'giọng nhẹ nhàng, hồn nhiên',
        traits: ['kiên nhẫn', 'tò mò'],
        relationships: [{ from_id: 'ch_rabbit', to_id: 'ch_kite', kind: 'friend', description: 'Bạn thân mới quen' }],
      },
      { character_id: 'ch_kite', name: 'Cánh diều giấy', role: 'deuteragonist', appearance: 'Diều hình con chim, giấy màu xanh và vàng', traits: ['vui vẻ'] },
    ],
  },
});

const BEATS = envelope({
  artifact_type: 'BeatSheet',
  content: {
    beat_sheet_id: 'bs_1',
    beats: [
      { beat_id: 'b1', order: 1, description: 'Thỏ nhặt cánh diều rơi bên bờ sông', emotional_beat: 'tò mò', role: 'hook', target_seconds: 40 },
      { beat_id: 'b2', order: 2, description: 'Thỏ tập thả diều, gặp trở ngại vì chưa biết cách', emotional_beat: 'kiên trì', role: 'rising', target_seconds: 80 },
      { beat_id: 'b3', order: 3, description: 'Cơn gió lớn, cánh diều suýt bay mất', emotional_beat: 'lo lắng', role: 'climax', target_seconds: 60 },
      { beat_id: 'b4', order: 4, description: 'Thỏ giữ được dây, diều bay cao, cả hai vui mừng', emotional_beat: 'vui sướng', role: 'resolution', target_seconds: 60 },
    ],
  },
});

const OUTLINE = envelope({
  artifact_type: 'EpisodeOutline',
  content: {
    outline_id: 'ol_1', title: 'Con thỏ và cánh diều',
    target_duration_seconds: 240, tolerance_seconds: 15,
    audience_band: '5-8', language: 'vi',
    scenes: [
      { scene_id: 's1', order: 1, intent: 'Thỏ nhặt diều bên bờ sông', location_id: 'loc_river', estimated_seconds: 40, dialogue_budget_seconds: 10, beat_refs: ['b1'] },
      { scene_id: 's2', order: 2, intent: 'Thỏ tập thả diều cùng Gió', location_id: 'loc_field', estimated_seconds: 80, dialogue_budget_seconds: 30, beat_refs: ['b2'] },
      { scene_id: 's3', order: 3, intent: 'Cơn gió lớn, diều suýt mất', location_id: 'loc_field', estimated_seconds: 60, beat_refs: ['b3'] },
      { scene_id: 's4', order: 4, intent: 'Thỏ giữ dây, diều bay cao', location_id: 'loc_field', estimated_seconds: 60, beat_refs: ['b4'] },
    ],
  },
});

// -- component-level: artifact views ----------------------------------------

describe('ArtifactViews (C4)', () => {
  it('renders idea candidates with score dimensions, provenance, and selection callback', () => {
    const onSelect = vi.fn();
    render(<IdeaSetView artifact={IDEA_SET} onSelect={onSelect} />);
    expect(screen.getByText('Chú thỏ và cánh diều giấy')).toBeInTheDocument();
    expect(screen.getByText('Score: 0.718')).toBeInTheDocument();
    expect(screen.getAllByText('AGE_FIT').length).toBeGreaterThan(0);
    expect(screen.getByText('0.950')).toBeInTheDocument();
    expect(screen.getByText(/recommended/)).toBeInTheDocument();
    const buttons = screen.getAllByRole('button', { name: 'Select this idea' });
    expect(buttons).toHaveLength(3);
    fireEvent.click(buttons[0]);
    expect(onSelect).toHaveBeenCalledWith('c_rabbit_kite');
  });

  it('wraps long Vietnamese text safely in bible views', () => {
    render(<StoryBibleView artifact={STORY_BIBLE} />);
    const premise = screen.getByText(/Một chú thỏ con ham chơi ở bờ sông nhặt được cánh diều giấy và học cách kiên nhẫn để thả nó bay cao giữa trời chiều\./);
    expect(premise).toBeInTheDocument();
    expect(premise.style.whiteSpace).toBe('pre-wrap');
    expect(screen.getByText(/Gió chỉ giúp ai kiên nhẫn\./)).toBeInTheDocument();
  });

  it('renders world bible rules, locations, and objects', () => {
    render(<WorldBibleView artifact={WORLD_BIBLE} />);
    expect(screen.getByText('World rules')).toBeInTheDocument();
    expect(screen.getByText(/Gió thổi mạnh hơn khi trời quang/)).toBeInTheDocument();
    expect(screen.getByText('Bờ sông')).toBeInTheDocument();
    expect(screen.getByText('Cánh diều giấy')).toBeInTheDocument();
  });

  it('renders character canon with roles, traits, and relationships', () => {
    render(<CharacterCanonView artifact={CHARACTER_CANON} />);
    expect(screen.getByText('Thỏ con')).toBeInTheDocument();
    expect(screen.getByText(/protagonist/)).toBeInTheDocument();
    expect(screen.getByText(/Bạn thân mới quen/)).toBeInTheDocument();
  });

  it('renders timed beats with cumulative total', () => {
    render(<BeatsView artifact={BEATS} />);
    expect(screen.getByText(/Thỏ nhặt cánh diều rơi bên bờ sông/)).toBeInTheDocument();
    expect(screen.getByText(/climax · 1:00/)).toBeInTheDocument();
    expect(screen.getByText('Total: 4:00')).toBeInTheDocument();
  });

  it('renders timed outline scenes with duration budget indicator', () => {
    render(<OutlineView artifact={OUTLINE} />);
    expect(screen.getByText(/Scene 2: Thỏ tập thả diều cùng Gió/)).toBeInTheDocument();
    expect(screen.getByText(/vs target 4:00/)).toBeInTheDocument();
    expect(screen.getByText('Scene total: 4:00')).toBeInTheDocument();
  });

  it('renders unsupported schema as explicit state, never blank', () => {
    render(<UnsupportedArtifactView artifact={envelope({ artifact_type: 'MysteryThing', schema_version: 'studio.artifact/v2' })} />);
    expect(screen.getByText(/unsupported schema studio.artifact\/v2/)).toBeInTheDocument();
  });

  it('dispatches unknown v1alpha1 types to a generic read-only view', () => {
    render(<ArtifactContentView artifact={envelope({ artifact_type: 'ScreenplayDraft', content: { scenes: [] } })} />);
    expect(screen.getByText(/ScreenplayDraft persisted/)).toBeInTheDocument();
  });
});

// -- component-level: approval bar ------------------------------------------

describe('ApprovalBar (C4)', () => {
  it('submits APPROVED with reason only when typed', () => {
    const onSubmit = vi.fn();
    render(<ApprovalBar checkpoint="IDEA" artifactTitle="Chú thỏ và cánh diều" revisionId="rev_1" revisionHash={REV_HASH} expectedVersion={3} onSubmit={onSubmit} />);
    fireEvent.click(screen.getByRole('button', { name: 'Approve IDEA' }));
    expect(onSubmit).toHaveBeenCalledWith('APPROVED', '');
  });

  it('submits REQUEST_REVISION with the typed reason', () => {
    const onSubmit = vi.fn();
    render(<ApprovalBar checkpoint="STORY_BIBLE" artifactTitle={null} revisionId="rev_1" revisionHash={REV_HASH} expectedVersion={3} onSubmit={onSubmit} />);
    fireEvent.change(screen.getByLabelText('Approval reason'), { target: { value: 'Cần cao trào rõ hơn' } });
    fireEvent.click(screen.getByRole('button', { name: 'Request revision at STORY_BIBLE' }));
    expect(onSubmit).toHaveBeenCalledWith('REQUEST_REVISION', 'Cần cao trào rõ hơn');
  });

  it('submits REJECTED', () => {
    const onSubmit = vi.fn();
    render(<ApprovalBar checkpoint="OUTLINE" artifactTitle={null} revisionId="rev_1" revisionHash={REV_HASH} expectedVersion={3} onSubmit={onSubmit} />);
    fireEvent.click(screen.getByRole('button', { name: 'Reject OUTLINE' }));
    expect(onSubmit).toHaveBeenCalledWith('REJECTED', '');
  });
});

// -- component-level: run progress ------------------------------------------

function makeStore(fetchImpl: FetchFn): StudioStore {
  return new StudioStore(new HttpStudioApiClient({ baseUrl: 'http://localhost:8000', fetchImpl }));
}

function runResource(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 'run_1', status: 'RUNNING', episode_id: 'ep_1',
    command_type: 'START_STORY_RUN', started_at: '2026-01-01T00:00:00Z',
    finished_at: null, wait_reason: null, result_uri: null,
    ...overrides,
  };
}

describe('RunProgress (C4)', () => {
  it('shows status, wait reason, and deduplicated events', async () => {
    let eventCalls = 0;
    const fetchImpl: FetchFn = async (input) => {
      const url = String(input);
      if (url.includes('/runs/run_1/events')) {
        eventCalls += 1;
        return jsonResponse(200, {
          events: [
            { sequence: 1, event_type: 'studio.idea.candidates_generated' },
            { sequence: 2, event_type: 'studio.approval.requested' },
          ],
          next_after: 2,
        });
      }
      return jsonResponse(200, runResource({ status: 'WAITING_FOR_APPROVAL', wait_reason: 'APPROVAL_REQUIRED' }));
    };
    const store = makeStore(fetchImpl);
    render(<RunProgress runId="run_1" store={store} intervalMs={20} onDurableChange={() => undefined} />);
    expect(await screen.findByText('WAITING_FOR_APPROVAL')).toBeInTheDocument();
    expect(screen.getByText('wait: APPROVAL_REQUIRED')).toBeInTheDocument();
    expect(screen.getByText(/Waiting for human approval at a checkpoint\./)).toBeInTheDocument();
    expect(screen.getByText('Idea candidates generated')).toBeInTheDocument();
    expect(screen.getByText('Approval requested')).toBeInTheDocument();
    // second poll tick returns the same page: no duplicates
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(screen.getAllByText('Idea candidates generated')).toHaveLength(1);
    expect(eventCalls).toBeGreaterThanOrEqual(2);
  });

  it('stops polling on terminal status', async () => {
    let runCalls = 0;
    const fetchImpl: FetchFn = async (input) => {
      const url = String(input);
      if (url.includes('/runs/run_1/events')) {
        return jsonResponse(200, { events: [], next_after: 0 });
      }
      runCalls += 1;
      return jsonResponse(200, runResource({ status: 'COMPLETED' }));
    };
    const store = makeStore(fetchImpl);
    render(<RunProgress runId="run_1" store={store} intervalMs={20} onDurableChange={() => undefined} />);
    expect(await screen.findByText('COMPLETED')).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 80));
    const callsAtTerminal = runCalls;
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(runCalls).toBe(callsAtTerminal);
  });
});

// -- page-level integration -------------------------------------------------

let fetchMock: ReturnType<typeof vi.fn<FetchFn>>;

beforeEach(() => {
  window.location.hash = '#/studio';
  sessionStorage.clear();
  fetchMock = vi.fn<FetchFn>(async (input: string | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith('/api/v3/studio/capabilities')) return jsonResponse(200, CAPABILITIES);
    if (url.endsWith('/api/v3/studio/series')) return jsonResponse(200, { items: [{ id: 'srs_1', title: 'S', episode_count: 1 }] });
    if (url.includes('/idea-selection')) return jsonResponse(201, { episode_id: 'ep_1', candidate_id: 'c_rabbit_kite', revision_id: 'rev_1' });
    if (url.includes('/approvals')) return jsonResponse(200, { episode_id: 'ep_1', checkpoint: 'IDEA', next_state: 'STORY_BIBLE_REVIEW', awaiting_approval: false });
    if (url.includes('/series/srs_1/episodes')) return jsonResponse(200, { items: [episode()] });
    if (url.includes('/episodes/ep_1/artifacts')) return jsonResponse(200, { items: [IDEA_SET] });
    if (url.includes('/api/v3/studio/episodes/ep_1')) return jsonResponse(200, episode());
    throw new Error(`unmocked URL: ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = '';
  sessionStorage.clear();
});

async function openEpisode() {
  render(<StudioPage />);
  const link = await screen.findByRole('link', { name: /^S \(1/ });
  fireEvent.click(link);
  const epLink = await screen.findByRole('link', { name: /Ep ep_1/ });
  fireEvent.click(epLink);
  await screen.findByText('Start / resume run');
}

describe('StudioPage story workflow (C4)', () => {
  it('renders idea cards from the server set', async () => {
    await openEpisode();
    expect(await screen.findByText('Chú thỏ và cánh diều giấy')).toBeInTheDocument();
    expect(screen.getByText('Cánh diều bay qua sông')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Select this idea' })).toHaveLength(3);
  });

  it('submits idea selection with exact set hash, revision, and version', async () => {
    await openEpisode();
    const buttons = await screen.findAllByRole('button', { name: 'Select this idea' });
    fireEvent.click(buttons[0]);
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) => String(u).includes('/idea-selection'));
      expect(call).toBeTruthy();
      const [, init] = call as unknown as [string | URL, RequestInit];
      expect(init.method).toBe('POST');
      expect(init.headers).toMatchObject({ 'X-Idempotency-Key': expect.any(String) });
      const body = JSON.parse(String(init.body));
      expect(body).toMatchObject({
        episode_id: 'ep_1',
        revision_id: 'rev_1',
        candidate_id: 'c_rabbit_kite',
        expected_content_hash: HASH,
        expected_optimistic_version: 3,
      });
    });
  });

  it('shows approval controls at a checkpoint and submits the server revision hash', async () => {
    fetchMock.mockImplementation(async (input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v3/studio/capabilities')) return jsonResponse(200, CAPABILITIES);
      if (url.endsWith('/api/v3/studio/series')) return jsonResponse(200, { items: [{ id: 'srs_1', title: 'S', episode_count: 1 }] });
      if (url.includes('/approvals')) return jsonResponse(200, { episode_id: 'ep_1', checkpoint: 'IDEA', next_state: 'STORY_BIBLE_REVIEW', awaiting_approval: false });
      if (url.includes('/series/srs_1/episodes')) return jsonResponse(200, { items: [episode()] });
      if (url.includes('/episodes/ep_1/artifacts')) return jsonResponse(200, { items: [IDEA_SET] });
      if (url.includes('/api/v3/studio/episodes/ep_1')) {
        return jsonResponse(200, episode({ state: 'IDEA_REVIEW', awaiting_checkpoint: 'IDEA' }));
      }
      throw new Error(`unmocked URL: ${url}`);
    });
    await openEpisode();
    expect(await screen.findByRole('button', { name: 'Approve IDEA' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Approve IDEA' }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) => String(u).includes('/approvals'));
      expect(call).toBeTruthy();
      const [, init] = call as unknown as [string | URL, RequestInit];
      const body = JSON.parse(String(init.body));
      expect(body).toMatchObject({
        episode_id: 'ep_1',
        revision_id: 'rev_1',
        checkpoint: 'IDEA',
        artifact_hash: REV_HASH,
        decision: 'APPROVED',
        expected_optimistic_version: 3,
      });
    });
  });

  it('hides approval controls when no checkpoint is awaiting', async () => {
    await openEpisode();
    await screen.findByText('Chú thỏ và cánh diều giấy');
    expect(screen.queryByRole('button', { name: /Approve/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Request revision/ })).not.toBeInTheDocument();
  });

  it('refetches server truth on stale conflict and shows the conflict alert', async () => {
    let selectionAttempts = 0;
    fetchMock.mockImplementation(async (input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v3/studio/capabilities')) return jsonResponse(200, CAPABILITIES);
      if (url.endsWith('/api/v3/studio/series')) return jsonResponse(200, { items: [{ id: 'srs_1', title: 'S', episode_count: 1 }] });
      if (url.includes('/idea-selection')) {
        selectionAttempts += 1;
        return jsonResponse(409, {
          type: 'https://windagent.io/errors/stale-revision', title: 'Stale Revision',
          status: 409, detail: 'Expected revision/version does not match current state.',
          code: 'STALE_REVISION', retryable: false,
          details: { episode_id: 'ep_1', current_revision: 'rev_2' },
        });
      }
      if (url.includes('/series/srs_1/episodes')) return jsonResponse(200, { items: [episode()] });
      if (url.includes('/episodes/ep_1/artifacts')) return jsonResponse(200, { items: [IDEA_SET] });
      if (url.includes('/api/v3/studio/episodes/ep_1')) {
        return jsonResponse(200, episode({ state: 'IDEA_REVIEW', awaiting_checkpoint: 'IDEA' }));
      }
      throw new Error(`unmocked URL: ${url}`);
    });
    await openEpisode();
    const buttons = await screen.findAllByRole('button', { name: 'Select this idea' });
    fireEvent.click(buttons[0]);
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Stale revision conflict');
    });
    expect(selectionAttempts).toBe(1);
  });

  it('renders bibles, beats, and outline artifacts in the episode view', async () => {
    fetchMock.mockImplementation(async (input: string | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v3/studio/capabilities')) return jsonResponse(200, CAPABILITIES);
      if (url.endsWith('/api/v3/studio/series')) return jsonResponse(200, { items: [{ id: 'srs_1', title: 'S', episode_count: 1 }] });
      if (url.includes('/series/srs_1/episodes')) return jsonResponse(200, { items: [episode()] });
      if (url.includes('/episodes/ep_1/artifacts')) {
        return jsonResponse(200, { items: [STORY_BIBLE, WORLD_BIBLE, CHARACTER_CANON, BEATS, OUTLINE] });
      }
      if (url.includes('/api/v3/studio/episodes/ep_1')) return jsonResponse(200, episode());
      throw new Error(`unmocked URL: ${url}`);
    });
    await openEpisode();
    expect(await screen.findByText(/Một chú thỏ con ham chơi ở bờ sông/)).toBeInTheDocument();
    expect(screen.getByText(/Gió thổi mạnh hơn/)).toBeInTheDocument();
    expect(screen.getByText('Thỏ con')).toBeInTheDocument();
    expect(screen.getByText('Total: 4:00')).toBeInTheDocument();
    expect(screen.getByText(/vs target 4:00/)).toBeInTheDocument();
  });
  it('persists the event cursor across restart via sessionStorage', async () => {
    fetchMock.mockImplementation(async (input: string | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v3/studio/capabilities')) return jsonResponse(200, CAPABILITIES);
      if (url.endsWith('/api/v3/studio/series')) return jsonResponse(200, { items: [{ id: 'srs_1', title: 'S', episode_count: 1 }] });
      if (url.includes('/series/srs_1/episodes')) return jsonResponse(200, { items: [episode({ active_run_id: 'run_1' })] });
      if (url.includes('/episodes/ep_1/artifacts')) return jsonResponse(200, { items: [] });
      if (url.includes('/runs/run_1/events')) return jsonResponse(200, { events: [{ sequence: 1, event_type: 'studio.idea.candidates_generated' }], next_after: 1 });
      if (url.includes('/api/v3/studio/episodes/ep_1')) return jsonResponse(200, episode({ active_run_id: 'run_1', state: 'IDEA_REVIEW' }));
      if (url.includes('/api/v3/studio/runs/run_1')) return jsonResponse(200, runResource({ status: 'RUNNING' }));
      throw new Error(`unmocked URL: ${url}`);
    });
    await openEpisode();
    expect(await screen.findByText('Idea candidates generated')).toBeInTheDocument();
    window.dispatchEvent(new Event('beforeunload'));
    const saved = sessionStorage.getItem('studio.eventCursors');
    expect(saved).toBeTruthy();
    expect(JSON.parse(String(saved))).toEqual({ eventCursors: { run_1: 1 } });
  });
});
