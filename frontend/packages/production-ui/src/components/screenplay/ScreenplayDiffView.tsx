import React from 'react';
import { ScreenplayDiffResultDTO } from '@windagent/production-contracts';

interface ScreenplayDiffViewProps {
  diffResult: ScreenplayDiffResultDTO | null;
}

export const ScreenplayDiffView: React.FC<ScreenplayDiffViewProps> = ({ diffResult }) => {
  if (!diffResult) {
    return <div style={{ padding: '1rem', color: '#6C7086', fontSize: '0.85rem' }}>No active revision comparison to display.</div>;
  }

  return (
    <div style={{ padding: '1rem', fontFamily: 'Inter, system-ui, sans-serif', color: '#CDD6F4' }}>
      <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '1rem', fontSize: '0.8rem', fontWeight: 600 }}>
        <span>Base: <code style={{ color: '#F38BA8' }}>{diffResult.base_revision_id}</code></span>
        <span>Target: <code style={{ color: '#A6E3A1' }}>{diffResult.target_revision_id}</code></span>
        <span style={{ color: '#89B4FA' }}>Added: {diffResult.total_added}</span>
        <span style={{ color: '#F38BA8' }}>Deleted: {diffResult.total_deleted}</span>
        <span style={{ color: '#FAB387' }}>Modified: {diffResult.total_modified}</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {diffResult.entity_diffs.map((diff, idx) => (
          <div
            key={idx}
            style={{
              backgroundColor: '#181825',
              padding: '0.6rem 0.85rem',
              borderRadius: '6px',
              borderLeft:
                diff.change_type === 'ADDED'
                  ? '4px solid #A6E3A1'
                  : diff.change_type === 'DELETED'
                  ? '4px solid #F38BA8'
                  : '4px solid #FAB387',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: 700 }}>
              <span>{diff.entity_type}: {diff.title}</span>
              <span
                style={{
                  color:
                    diff.change_type === 'ADDED'
                      ? '#A6E3A1'
                      : diff.change_type === 'DELETED'
                      ? '#F38BA8'
                      : '#FAB387',
                }}
              >
                {diff.change_type}
              </span>
            </div>
            {diff.changes.map((c, cIdx) => (
              <div key={cIdx} style={{ fontSize: '0.7rem', color: '#A6ADC8', marginTop: '0.2rem' }}>
                Field <code>{c.field_name}</code>: <span style={{ color: '#F38BA8' }}>{String(c.old_value)}</span> →{' '}
                <span style={{ color: '#A6E3A1' }}>{String(c.new_value)}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
};
