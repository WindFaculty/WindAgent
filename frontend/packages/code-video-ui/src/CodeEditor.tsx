import React from 'react';
import { CodeEditorState } from './types';

export interface CodeEditorProps {
  state: CodeEditorState;
  onLineClick?: (lineIndex: number) => void;
}

export const CodeEditor: React.FC<CodeEditorProps> = ({ state, onLineClick }) => {
  const lines = state.content ? state.content.split('\n') : [''];

  return (
    <div
      className="code-editor"
      data-file={state.active_file}
      data-zoom={state.zoom_level}
      style={{
        transform: `scale(${state.zoom_level})`,
        transformOrigin: 'top left',
      }}
    >
      <div className="editor-header">
        <span className="tab active">{state.active_file}</span>
      </div>
      <div className="editor-body">
        {lines.map((lineText, idx) => {
          const lineNum = idx + 1;
          const isCursorLine = lineNum === state.cursor_line;
          const isHighlighted = state.highlighted_lines?.includes(lineNum);

          const classNames = ['editor-line'];
          if (isCursorLine) classNames.push('cursor-line');
          if (isHighlighted) classNames.push('highlighted-line');

          return (
            <div
              key={lineNum}
              className={classNames.join(' ')}
              onClick={() => onLineClick?.(lineNum)}
            >
              <span className="line-num">{lineNum}</span>
              <span className="line-code">
                {lineText || ' '}
                {isCursorLine && <span className="cursor-caret" />}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
