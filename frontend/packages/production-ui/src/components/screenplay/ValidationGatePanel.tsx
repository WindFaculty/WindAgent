import React from 'react';
import { ScreenplayValidationReportDTO } from '@windagent/production-contracts';

interface ValidationGatePanelProps {
  report: ScreenplayValidationReportDTO | null;
  onSelectEntity?: (entityId: string) => void;
  onLockRevision: () => void;
}

export const ValidationGatePanel: React.FC<ValidationGatePanelProps> = ({ report, onSelectEntity, onLockRevision }) => {
  if (!report) {
    return <div style={{ padding: '1rem', color: '#6C7086', fontSize: '0.85rem' }}>No validation report loaded.</div>;
  }

  return (
    <div style={{ padding: '1rem', fontFamily: 'Inter, system-ui, sans-serif', color: '#CDD6F4' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', fontSize: '0.8rem', fontWeight: 600 }}>
          <span style={{ color: report.blocking_count > 0 ? '#F38BA8' : '#A6E3A1' }}>
            BLOCKING: {report.blocking_count}
          </span>
          <span style={{ color: '#FAB387' }}>WARNING: {report.warning_count}</span>
          <span style={{ color: '#89B4FA' }}>INFO: {report.info_count}</span>
        </div>

        <button
          onClick={onLockRevision}
          disabled={!report.is_lockable}
          style={{
            padding: '0.35rem 0.85rem',
            borderRadius: '6px',
            border: 'none',
            backgroundColor: report.is_lockable ? '#FAB387' : '#313244',
            color: report.is_lockable ? '#11111B' : '#585B70',
            fontWeight: 700,
            fontSize: '0.75rem',
            cursor: report.is_lockable ? 'pointer' : 'not-allowed',
          }}
        >
          🔒 Lock Revision Gate ({report.is_lockable ? 'PASS' : 'BLOCKED'})
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {report.issues.length === 0 ? (
          <div style={{ color: '#A6E3A1', fontSize: '0.8rem', fontWeight: 600 }}>
            ✓ No validation issues found! Screenplay is ready to be locked.
          </div>
        ) : (
          report.issues.map((issue, idx) => (
            <div
              key={idx}
              onClick={() => onSelectEntity && onSelectEntity(issue.entity_id)}
              style={{
                backgroundColor: '#181825',
                padding: '0.6rem 0.85rem',
                borderRadius: '6px',
                borderLeft: issue.severity === 'BLOCKING' ? '4px solid #F38BA8' : '4px solid #FAB387',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: 700 }}>
                <span style={{ color: issue.severity === 'BLOCKING' ? '#F38BA8' : '#FAB387' }}>
                  [{issue.severity}] {issue.code} ({issue.entity_type}: {issue.entity_id})
                </span>
              </div>
              <div style={{ fontSize: '0.8rem', marginTop: '0.2rem', color: '#F5E0DC' }}>{issue.message}</div>
              {issue.remediation_hint && (
                <div style={{ fontSize: '0.7rem', color: '#A6ADC8', marginTop: '0.25rem' }}>
                  💡 Hint: {issue.remediation_hint}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {report.asset_requirements.length > 0 && (
        <div style={{ marginTop: '1.25rem' }}>
          <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.8rem', color: '#CBA6F7', fontWeight: 700 }}>
            STAGE E ASSET REQUIREMENTS ({report.asset_requirements.length})
          </h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
            {report.asset_requirements.map((req) => (
              <span
                key={req.requirement_id}
                style={{
                  padding: '0.25rem 0.6rem',
                  borderRadius: '4px',
                  backgroundColor: '#313244',
                  color: '#89B4FA',
                  fontSize: '0.7rem',
                  fontWeight: 600,
                }}
              >
                {req.asset_type}: {req.display_name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
