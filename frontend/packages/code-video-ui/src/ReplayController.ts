/**
 * Client-Side Replay Controller for deterministic video timeline playback.
 */

import {
  Action,
  ChecklistState,
  CodeEditorState,
  CodeVideoPlan,
  DiagramState,
  FileTreeItem,
  OutroCardState,
  Scene,
  TerminalState,
  TitleCardState,
  VisualMode,
} from './types';

export interface ReplayFrameState {
  current_time_ms: number;
  active_scene: Scene;
  visual_mode: VisualMode;
  editor: CodeEditorState;
  terminal: TerminalState;
  diagram: DiagramState;
  title_card?: TitleCardState;
  checklist?: ChecklistState;
  outro?: OutroCardState;
  progress_pct: number;
}

export type FrameListener = (state: ReplayFrameState) => void;

export class ReplayController {
  private plan: CodeVideoPlan;
  private currentMs: number = 0;
  private listeners: Set<FrameListener> = new Set();

  constructor(plan: CodeVideoPlan) {
    this.plan = plan;
  }

  public getPlan(): CodeVideoPlan {
    return this.plan;
  }

  public getDurationMs(): number {
    return this.plan.duration_ms;
  }

  public getCurrentTimeMs(): number {
    return this.currentMs;
  }

  public subscribe(listener: FrameListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  public getSceneAt(timestampMs: number): Scene {
    const clamped = Math.max(0, Math.min(timestampMs, this.plan.duration_ms));
    for (const scene of this.plan.scenes) {
      if (clamped >= scene.start_ms && clamped < scene.end_ms) {
        return scene;
      }
    }
    return this.plan.scenes[this.plan.scenes.length - 1];
  }

  public seek(timestampMs: number): ReplayFrameState {
    this.currentMs = Math.max(0, Math.min(timestampMs, this.plan.duration_ms));
    const state = this.getFrameStateAt(this.currentMs);
    this.notifyListeners(state);
    return state;
  }

  public resumeFrom(sceneId: string, actionId?: string): ReplayFrameState {
    const scene = this.plan.scenes.find((s) => s.scene_id === sceneId);
    if (!scene) {
      throw new Error(`Scene '${sceneId}' not found in plan.`);
    }

    let targetMs = scene.start_ms;
    if (actionId) {
      const action = scene.actions.find((a) => a.action_id === actionId);
      if (action) {
        targetMs = action.start_ms;
      }
    }

    return this.seek(targetMs);
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

  public getFrameStateAt(timestampMs: number): ReplayFrameState {
    const clamped = Math.max(0, Math.min(timestampMs, this.plan.duration_ms));
    const activeScene = this.getSceneAt(clamped);

    // Initial state templates
    const editor: CodeEditorState = {
      active_file: 'src/agent.py',
      content: '',
      cursor_line: 1,
      cursor_col: 1,
      selection: null,
      highlighted_symbol: null,
      highlighted_lines: [],
      zoom_level: 1.0,
      scroll_top_line: 1,
      focus_mode: false,
    };

    const terminal: TerminalState = {
      working_dir: 'agentic-studio',
      prompt_prefix: 'PS D:\\code_video\\workspace\\agentic-studio> ',
      history: [],
      current_input: '',
      is_running: false,
      last_command: null,
      last_exit_code: null,
    };

    const diagram: DiagramState = {
      diagram_id: 'diagram_default',
      title: 'Architecture View',
      subtitle: '',
      nodes: [],
      edges: [],
      highlighted_nodes: [],
    };

    // Apply previous scenes and current actions up to timestamp
    for (const scene of this.plan.scenes) {
      if (scene.end_ms <= clamped) {
        for (const act of scene.actions) {
          this.applyActionState(act, editor, terminal, diagram, null);
        }
      } else if (scene.scene_id === activeScene.scene_id) {
        for (const act of scene.actions) {
          if (act.start_ms <= clamped) {
            const elapsed = clamped < act.end_ms ? clamped - act.start_ms : null;
            this.applyActionState(act, editor, terminal, diagram, elapsed);
          }
        }
        break;
      }
    }

    const progress_pct = (clamped / Math.max(1, this.plan.duration_ms)) * 100;

    return {
      current_time_ms: clamped,
      active_scene: activeScene,
      visual_mode: activeScene.visual_mode,
      editor,
      terminal,
      diagram,
      progress_pct,
    };
  }

  private applyActionState(
    action: Action,
    editor: CodeEditorState,
    terminal: TerminalState,
    diagram: DiagramState,
    elapsedInActionMs: number | null
  ): void {
    const p = action.params || {};

    switch (action.action_type) {
      case 'OPEN_FILE':
        if (p.path) editor.active_file = p.path;
        if (p.content) editor.content = p.content;
        break;

      case 'TYPE_TEXT': {
        const fullText = p.text || p.source || '';
        if (elapsedInActionMs !== null && action.duration_ms > 0) {
          const ratio = Math.min(1.0, elapsedInActionMs / action.duration_ms);
          const charsToShow = Math.floor(fullText.length * ratio);
          const visible = fullText.substring(0, charsToShow);
          editor.content = visible;
          const lines = visible.split('\n');
          editor.cursor_line = lines.length;
          editor.cursor_col = lines[lines.length - 1].length + 1;
        } else {
          editor.content = fullText;
          const lines = fullText.split('\n');
          editor.cursor_line = lines.length;
          editor.cursor_col = lines[lines.length - 1].length + 1;
        }
        break;
      }

      case 'HIGHLIGHT':
        if (p.symbol) editor.highlighted_symbol = p.symbol;
        if (p.lines && Array.isArray(p.lines)) {
          editor.highlighted_lines = p.lines;
        }
        break;

      case 'ZOOM':
        if (p.zoom_level || p.level) {
          editor.zoom_level = Number(p.zoom_level || p.level);
        }
        break;

      case 'RUN_TERMINAL':
        if (p.command) {
          terminal.last_command = p.command;
          terminal.history.push({
            type: 'command',
            text: p.command,
            timestamp_ms: action.start_ms,
          });
        }
        break;

      case 'RESET_VIEW':
        editor.highlighted_symbol = null;
        editor.highlighted_lines = [];
        editor.zoom_level = 1.0;
        break;
    }
  }

  private notifyListeners(state: ReplayFrameState): void {
    for (const listener of this.listeners) {
      try {
        listener(state);
      } catch (err) {
        console.error('Error in replay listener:', err);
      }
    }
  }
}
