import React from 'react';
import {
  Annotation,
  ChecklistState,
  CodeEditorState,
  DiagramState,
  FileTreeItem,
  OutroCardState,
  TerminalState,
  TitleCardState,
  VisualMode,
} from './types';
import { CodeEditor } from './CodeEditor';
import { Terminal } from './Terminal';
import { FileTree } from './FileTree';
import { DiagramStage } from './DiagramStage';
import { TitleCard } from './TitleCard';
import { ChecklistStage } from './ChecklistStage';
import { Overlay } from './Overlay';

export interface CodeStudioProps {
  visualMode: VisualMode;
  projectName?: string;
  episodeBadge?: string;
  fileTreeItems?: FileTreeItem[];
  activeFilePath?: string;
  editorState: CodeEditorState;
  terminalState: TerminalState;
  diagramState: DiagramState;
  titleCardState: TitleCardState;
  checklistState: ChecklistState;
  outroState?: OutroCardState;
  annotations?: Annotation[];
  onSelectFile?: (path: string) => void;
}

export const CodeStudio: React.FC<CodeStudioProps> = ({
  visualMode,
  projectName = 'agentic-studio',
  episodeBadge = 'VIDEO 02',
  fileTreeItems = [],
  activeFilePath = 'src/agent.py',
  editorState,
  terminalState,
  diagramState,
  titleCardState,
  checklistState,
  outroState,
  annotations,
  onSelectFile,
}) => {
  return (
    <div className="studio-root" data-visual-mode={visualMode}>
      {/* Recording Safe Header */}
      <header className="studio-header">
        <div className="studio-header-left">
          <span className="app-logo">⚡ WindAgent Code Studio</span>
          <span className="project-pill">{projectName}</span>
        </div>
        <div className="studio-header-right">
          <span className="rec-badge">REC SAFE</span>
          <span className="episode-pill">{episodeBadge}</span>
        </div>
      </header>

      {/* Main Mode Viewport */}
      {visualMode === 'CODE_STUDIO' && (
        <main className="studio-main layout-code-studio">
          <aside className="pane-file-tree">
            <FileTree
              rootName={projectName}
              items={fileTreeItems}
              activePath={activeFilePath}
              onSelectFile={onSelectFile}
            />
          </aside>
          <section className="pane-editor-and-terminal">
            <div className="pane-editor">
              <CodeEditor state={editorState} />
            </div>
            <div className="pane-terminal">
              <Terminal state={terminalState} />
            </div>
          </section>
        </main>
      )}

      {visualMode === 'FULL_CODE' && (
        <main className="studio-main layout-full-code">
          <div className="pane-editor full-view">
            <CodeEditor state={editorState} />
          </div>
        </main>
      )}

      {visualMode === 'FULL_TERMINAL' && (
        <main className="studio-main layout-full-terminal">
          <div className="pane-terminal full-view">
            <Terminal state={terminalState} />
          </div>
        </main>
      )}

      {(visualMode === 'DIAGRAM' || visualMode === 'ARCHITECTURE') && (
        <main className="studio-main layout-diagram">
          <DiagramStage state={diagramState} />
        </main>
      )}

      {visualMode === 'TITLE_CARD' && (
        <main className="studio-main layout-title">
          <TitleCard state={titleCardState} />
        </main>
      )}

      {visualMode === 'CHECKLIST' && (
        <main className="studio-main layout-checklist">
          <ChecklistStage state={checklistState} />
        </main>
      )}

      {visualMode === 'SPLIT' && (
        <main className="studio-main layout-split">
          <div className="pane-editor">
            <CodeEditor state={editorState} />
          </div>
          <div className="pane-terminal">
            <Terminal state={terminalState} />
          </div>
        </main>
      )}

      {visualMode === 'OUTRO' && (
        <main className="studio-main layout-outro">
          <div className="title-card-container">
            <div className="title-badge-row">
              <span className="badge-pill ep-badge">OUTRO</span>
              <span className="badge-pill ver-badge">{episodeBadge}</span>
            </div>
            <h1 className="title-card-heading">
              {outroState?.title || 'TỔNG KẾT & BƯỚC TIẾP THEO'}
            </h1>
            <p className="title-card-subheading">
              {outroState?.next_episode_title || 'VIDEO 03: TOOL CALLING & FUNCTION RUNTIME'}
            </p>
          </div>
        </main>
      )}

      {/* Floating Annotations / Overlays */}
      <Overlay annotations={annotations} />
    </div>
  );
};
