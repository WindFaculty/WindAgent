import React from 'react';
import { EntityConflictDTO, FieldConflictDTO } from '@windagent/production-contracts';

export interface SemanticDiffViewerProps {
  entityConflicts: EntityConflictDTO[];
  selectedEntityId?: string;
  onSelectEntity?: (entityId: string) => void;
}

export const SemanticDiffViewer: React.FC<SemanticDiffViewerProps> = ({
  entityConflicts,
  selectedEntityId,
  onSelectEntity,
}) => {
  if (!entityConflicts || entityConflicts.length === 0) {
    return (
      <div style={{ padding: '16px', color: '#8c8c8c', textAlign: 'center' }}>
        No semantic differences found between local and remote revisions.
      </div>
    );
  }

  const getBadgeStyle = (classification: string) => {
    switch (classification) {
      case 'LOCAL_ONLY_CHANGE':
        return { backgroundColor: '#e6f7ff', color: '#096dd9', border: '1px solid #91d5ff' };
      case 'REMOTE_ONLY_CHANGE':
        return { backgroundColor: '#f6ffed', color: '#389e0d', border: '1px solid #b7eb8f' };
      case 'NON_OVERLAPPING_MERGEABLE':
        return { backgroundColor: '#f9f0ff', color: '#722ed1', border: '1px solid #d3ade6' };
      case 'OVERLAPPING_REQUIRES_REVIEW':
        return { backgroundColor: '#fff1f0', color: '#cf1322', border: '1px solid #ffa39e' };
      case 'ENTITY_DELETED':
        return { backgroundColor: '#fff2e8', color: '#d4380d', border: '1px solid #ffbb96' };
      default:
        return { backgroundColor: '#f5f5f5', color: '#595959', border: '1px solid #d9d9d9' };
    }
  };

  return (
    <div data-testid="semantic-diff-viewer" style={{ border: '1px solid #f0f0f0', borderRadius: '6px', overflow: 'hidden' }}>
      <div style={{ padding: '12px 16px', backgroundColor: '#fafafa', borderBottom: '1px solid #f0f0f0', fontWeight: 'bold' }}>
        Semantic Entity & Field Differences ({entityConflicts.length})
      </div>
      <div style={{ maxHeight: '350px', overflowY: 'auto' }}>
        {entityConflicts.map((ec) => {
          const isSelected = selectedEntityId === ec.entity_id;
          const badge = getBadgeStyle(ec.classification);

          return (
            <div
              key={ec.entity_id}
              onClick={() => onSelectEntity && onSelectEntity(ec.entity_id)}
              style={{
                padding: '12px 16px',
                borderBottom: '1px solid #f0f0f0',
                backgroundColor: isSelected ? '#e6f7ff' : '#ffffff',
                cursor: onSelectEntity ? 'pointer' : 'default',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontWeight: 600, fontSize: '14px' }}>
                  {ec.entity_type} [{ec.entity_id}]: {ec.title || 'Untitled'}
                </span>
                <span
                  style={{
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontSize: '12px',
                    fontWeight: 500,
                    ...badge,
                  }}
                >
                  {ec.classification}
                </span>
              </div>

              {ec.field_conflicts && ec.field_conflicts.length > 0 && (
                <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse', marginTop: '6px' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#fafafa', color: '#595959', textAlign: 'left' }}>
                      <th style={{ padding: '4px 8px' }}>Field</th>
                      <th style={{ padding: '4px 8px' }}>Base</th>
                      <th style={{ padding: '4px 8px', color: '#096dd9' }}>Your Edit (Local)</th>
                      <th style={{ padding: '4px 8px', color: '#389e0d' }}>Remote Server</th>
                      <th style={{ padding: '4px 8px', color: '#722ed1' }}>Merged Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ec.field_conflicts.map((fc: FieldConflictDTO, idx: number) => (
                      <tr
                        key={idx}
                        style={{
                          borderTop: '1px solid #f0f0f0',
                          backgroundColor: fc.is_overlapping ? '#fff1f0' : 'transparent',
                        }}
                      >
                        <td style={{ padding: '4px 8px', fontWeight: 500 }}>{fc.field_name}</td>
                        <td style={{ padding: '4px 8px', color: '#8c8c8c' }}>{String(fc.base_value ?? '—')}</td>
                        <td style={{ padding: '4px 8px', color: '#096dd9', fontWeight: 500 }}>{String(fc.local_value ?? '—')}</td>
                        <td style={{ padding: '4px 8px', color: '#389e0d', fontWeight: 500 }}>{String(fc.remote_value ?? '—')}</td>
                        <td style={{ padding: '4px 8px', color: '#722ed1', fontWeight: 500 }}>
                          {fc.is_overlapping ? '⚡ OVERLAP (REQUIRES SELECTION)' : String(fc.merged_value ?? '—')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
