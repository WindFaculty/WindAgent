/**
 * Client-Side Replay Controller for deterministic video timeline playback.
 */

import {
  Action,
  CodeEditorState,
  CodeVideoPlan,
  DiagramState,
  FileTreeItem,
  Scene,
  TerminalState,
  VisualMode,
} from './types';

export interface ReplayFrameState {
  current_time_ms: number;
  active_scene: Scene;
  visual_mode: VisualMode;
  editor: CodeEditorState;
  terminal: TerminalState;
  diagram: DiagramState;
}

export class ReplayController {
  private plan: CodeVideoPlan;
  private currentMs: number = 0;

  constructor(plan: CodeVideoPlan) {
    this.plan = plan;
  }

  public getDurationMs(): number {
    return this.plan.duration_ms;
  }

  public getCurrentTimeMs(): number {
    return this.currentMs;
  }

  public getSceneAt(timestampMs: number): Scene {
    for (const scene of this.plan.scenes) {
      if (timestampMs >= scene.start_ms && timestampMs < scene.end_ms) {
        return scene;
      }
    }
    return this.plan.scenes[this.plan.scenes.length - 1];
  }

  public seek(timestampMs: number): Scene {
    this.currentMs = Math.max(0, Math.min(timestampMs, this.plan.duration_ms));
    return this.getSceneAt(this.currentMs);
  }

  public getActionsUpTo(timestampMs: number): Action[] {
    const executed: Action[] = [];
    for (const scene of this.plan.scenes) {
      if (scene.start_ms > timestampMs) break;
      for (const action of scene.actions) {
        if (action.start_ms <= timestampMs) {
          executed.push(action);
        }
      }
    }
    return executed;
  }
}
