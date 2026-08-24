/**
 * useLiveDirectorPlan — Phase 10 cutover (ban_ke_hoach_v1.md Sections 20-21)
 *
 * Loads the frozen LiveExecutionPlan that drives this recording session and
 * projects it onto the UI shapes:
 *   /live-record?plan=<plan_id>&episode=<episode_id>  → explicit handoff from
 *     the Episode workspace "Chuẩn bị ghi hình" flow;
 *   no params → most recent FROZEN plan (direct navigation).
 *
 * Principle A: scenes shown in Scene List / teleprompter come from
 * `LiveExecutionPlan.scenes` — never from a local mock script.
 */

import { useCallback, useEffect, useState } from 'react';
import type { LiveExecutionPlan, RecordingScene, SceneItem } from '../domain/types';
import { useApiClient } from '../../../api/ApiProvider';

export type PlanLoadPhase = 'IDLE' | 'LOADING' | 'READY' | 'ERROR';

export interface UseLiveDirectorPlanResult {
  readonly plan: LiveExecutionPlan | null;
  readonly phase: PlanLoadPhase;
  readonly error: string | null;
  /** Project plan scenes onto SceneListPanel items at a given active position. */
  projectSceneItems(activePosition: number): readonly SceneItem[];
  reload(): void;
}

function readHandoffParams(): { planId: string | null; episodeId: string | null } {
  if (typeof window === 'undefined') return { planId: null, episodeId: null };
  const q = new URLSearchParams(window.location.search);
  return {
    planId: q.get('plan') || q.get('plan_id'),
    episodeId: q.get('episode') || q.get('episode_id'),
  };
}

/** Project one frozen scene onto the SceneListPanel item shape (1-based). */
export function projectScene(scene: RecordingScene, position: number, activePosition: number): SceneItem {
  const totalSec = Math.max(0, Math.round(scene.duration_sec ?? 0));
  const hh = String(Math.floor(totalSec / 3600)).padStart(2, '0');
  const mm = String(Math.floor((totalSec % 3600) / 60)).padStart(2, '0');
  const ss = String(totalSec % 60).padStart(2, '0');
  return {
    id: scene.scene_id,
    index: position + 1,
    title: scene.title,
    duration: `${hh}:${mm}:${ss}`,
    durationSec: totalSec,
    status: position < activePosition ? 'completed' : position === activePosition ? 'active' : 'pending',
    // Narration source of truth: the plan scene's own narration text (Section 20).
    script: scene.narration_text ?? scene.narration_source ?? scene.title,
    scene_id: scene.scene_id,
    cue_id: scene.cues[0]?.cue_id,
  };
}

export function useLiveDirectorPlan(): UseLiveDirectorPlanResult {
  const client = useApiClient();
  const [plan, setPlan] = useState<LiveExecutionPlan | null>(null);
  const [phase, setPhase] = useState<PlanLoadPhase>('IDLE');
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  const reload = useCallback(() => setReloadTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    const load = async (): Promise<void> => {
      setPhase('LOADING');
      setError(null);
      try {
        const { planId, episodeId } = readHandoffParams();
        let targetId = planId;
        if (!targetId) {
          const listed = (await client.liveRecord.listPlans({
            ...(episodeId ? { episode_id: episodeId } : {}),
            limit: 20,
          })) as { items?: Array<Record<string, unknown>> };
          const items = listed.items ?? [];
          const frozen = items.find((p) => p['status'] === 'FROZEN') ?? items[0];
          targetId = frozen ? (String(frozen['id'] ?? frozen['plan_id'] ?? '') || null) : null;
        }
        if (!targetId) {
          if (!cancelled) {
            setPlan(null);
            setPhase('READY'); // no plan yet — page stays in dev/mock mode
          }
          return;
        }
        const raw = await client.liveRecord.getPlan(targetId);
        if (cancelled) return;
        setPlan(raw as unknown as LiveExecutionPlan);
        setPhase('READY');
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setPhase('ERROR');
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [client, reloadTick]);

  const projectSceneItems = useCallback(
    (activePosition: number): readonly SceneItem[] =>
      (plan?.scenes ?? []).map((scene, position) => projectScene(scene, position, activePosition)),
    [plan],
  );

  return { plan, phase, error, projectSceneItems, reload };
}
