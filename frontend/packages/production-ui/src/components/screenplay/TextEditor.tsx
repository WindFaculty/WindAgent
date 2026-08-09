import React, { useState } from 'react';

interface TextEditorProps {
  initialText: string;
  onApplyParsedText: (text: string) => void;
  isReadOnly?: boolean;
}

export const TextEditor: React.FC<TextEditorProps> = ({
  initialText,
  onApplyParsedText,
  isReadOnly = false,
}) => {
  const [text, setText] = useState<string>(initialText);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: '#181825',
        color: '#CDD6F4',
        fontFamily: 'Courier New, monospace',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.5rem 1rem',
          backgroundColor: '#11111B',
          borderBottom: '1px solid #313244',
          fontFamily: 'Inter, system-ui, sans-serif',
        }}
      >
        <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#F38BA8' }}>
          FOUNTAIN TEXT EDITOR {isReadOnly ? '(READ-ONLY)' : ''}
        </div>
        {!isReadOnly && (
          <button
            onClick={() => onApplyParsedText(text)}
            style={{
              padding: '0.3rem 0.75rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: '#89B4FA',
              color: '#11111B',
              fontWeight: 700,
              fontSize: '0.75rem',
              cursor: 'pointer',
            }}
          >
            ⚡ Parse & Apply to Candidate
          </button>
        )}
      </div>

      <div style={{ flex: 1, padding: '1rem', display: 'flex', flexDirection: 'column' }}>
        <textarea
          value={text}
          disabled={isReadOnly}
          onChange={(e) => setText(e.target.value)}
          style={{
            flex: 1,
            width: '100%',
            backgroundColor: '#1E1E2E',
            color: '#F5E0DC',
            border: '1px solid #313244',
            borderRadius: '6px',
            padding: '1rem',
            fontFamily: 'Courier New, monospace',
            fontSize: '0.9rem',
            lineHeight: 1.6,
            resize: 'none',
          }}
        />
      </div>
    </div>
  );
};
