import React from 'react';
import { TerminalState } from './types';

export interface TerminalProps {
  state: TerminalState;
}

export const Terminal: React.FC<TerminalProps> = ({ state }) => {
  return (
    <div className="terminal-container" data-working-dir={state.working_dir}>
      <div className="terminal-header">
        <span className="terminal-title">TERMINAL — PowerShell ({state.working_dir})</span>
        <span className={`terminal-status ${state.is_running ? 'running' : 'ready'}`}>
          {state.is_running ? 'RUNNING...' : 'READY'}
        </span>
      </div>
      <div className="terminal-body">
        {state.history.map((line, idx) => {
          if (line.type === 'command') {
            return (
              <div key={idx} className="term-row term-command">
                <span className="term-prompt">{state.prompt_prefix}</span>
                <span className="term-cmd-text">{line.text}</span>
              </div>
            );
          }
          if (line.type === 'exit_code') {
            const isPass = line.text.endsWith('0') || line.text.includes('PASS');
            return (
              <div key={idx} className={`term-row term-exit_code ${isPass ? 'pass' : 'fail'}`}>
                <span className="term-badge">{line.text}</span>
              </div>
            );
          }
          return (
            <div key={idx} className={`term-row term-${line.type}`}>
              {line.text || '\u00A0'}
            </div>
          );
        })}

        {!state.is_running && (
          <div className="term-row term-active-prompt">
            <span className="term-prompt">{state.prompt_prefix}</span>
            <span className="term-input-text">{state.current_input}</span>
            <span className="term-cursor-caret" />
          </div>
        )}
      </div>
    </div>
  );
};
