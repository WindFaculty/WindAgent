/**
 * TypeScript Contracts and Types for Code Video Studio UI.
 */

export type VisualMode =
  | 'CODE_STUDIO'
  | 'FULL_CODE'
  | 'FULL_TERMINAL'
  | 'DIAGRAM'
  | 'TITLE_CARD'
  | 'CHECKLIST'
  | 'ARCHITECTURE'
  | 'SPLIT'
  | 'OUTRO';

export type ActionType =
  | 'OPEN_WORKSPACE'
  | 'OPEN_FILE'
  | 'CREATE_FILE'
  | 'TYPE_TEXT'
  | 'REPLACE_TEXT'
  | 'SELECT_RANGE'
  | 'HIGHLIGHT'
  | 'SCROLL'
  | 'ZOOM'
  | 'RUN_TERMINAL'
  | 'WAIT'
  | 'SHOW_OUTPUT'
  | 'SHOW_DIAGRAM'
  | 'SHOW_TITLE'
  | 'SHOW_CHECKLIST'
  | 'SHOW_ARCHITECTURE'
  | 'SWITCH_LAYOUT'
  | 'RESET_VIEW';

export interface Action {
  action_id: string;
  action_type: ActionType;
  start_ms: number;
  duration_ms: number;
  params?: Record<string, any>;
}

export interface Annotation {
  annotation_id: string;
  kind: string;
  text?: string;
  start_ms?: number;
  duration_ms?: number;
  target_symbol?: string;
  target_line?: number;
  params?: Record<string, any>;
}

export interface Scene {
  scene_id: string;
  title: string;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  visual_mode: VisualMode;
  actions: Action[];
  expected_state?: Record<string, any>;
  annotations?: Annotation[];
  voice_cue_id?: string;
}

export interface CodeVideoPlan {
  video_id: string;
  schema_version: string;
  title: string;
  duration_ms: number;
  fps: number;
  resolution: { width: number; height: number };
  scenes: Scene[];
  source_hash: string;
  metadata?: Record<string, any>;
}

export interface FileTreeItem {
  path: string;
  name: string;
  is_dir: boolean;
  children?: FileTreeItem[];
  is_open?: boolean;
  is_active?: boolean;
}

export interface CodeEditorState {
  active_file: string;
  content: string;
  cursor_line: number;
  cursor_col: number;
  selection?: [number, number, number, number] | null;
  highlighted_symbol?: string | null;
  highlighted_lines?: number[];
  zoom_level: number;
  scroll_top_line: number;
  focus_mode: boolean;
}

export interface TerminalLine {
  type: 'prompt' | 'command' | 'stdout' | 'stderr' | 'exit_code' | 'system';
  text: string;
  timestamp_ms?: number;
}

export interface TerminalState {
  working_dir: string;
  prompt_prefix: string;
  history: TerminalLine[];
  current_input: string;
  is_running: boolean;
  last_command?: string | null;
  last_exit_code?: number | null;
}

export interface DiagramNode {
  id: string;
  label: string;
  subtext?: string;
  category: 'user' | 'domain' | 'infrastructure' | 'output' | 'concept';
  highlighted?: boolean;
}

export interface DiagramEdge {
  source_id: string;
  target_id: string;
  label?: string;
  style?: 'solid' | 'dashed' | 'animated';
}

export interface DiagramState {
  diagram_id: string;
  title: string;
  subtitle: string;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  highlighted_nodes: string[];
}

export interface TitleCardState {
  title: string;
  subtitle: string;
  badge: string;
  version_tag: string;
}

export interface ChecklistItem {
  text: string;
  status: 'INCLUDED' | 'EXCLUDED' | 'NEXT_EPISODE' | 'DONE';
  tag?: string;
}

export interface ChecklistState {
  title: string;
  subtitle: string;
  items: ChecklistItem[];
}

export interface OutroCardState {
  title: string;
  current_milestone: string;
  next_episode_title: string;
  next_episode_topics: string[];
}
